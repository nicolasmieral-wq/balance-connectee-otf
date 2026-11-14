/*
  Pavé balance OTF : programme du XIAO ESP32-S3
  Généré le 2026-11-14 par le générateur du kit (github.com/nicolasmieral-wq/balance-connectee-otf).

  PROTOTYPE NON TESTÉ. Réservé aux essais : un lien automatique balance -> caisse
  doit être certifié pour la vente au poids. Ne pas utiliser pour vendre.

  Réglages choisis :
    clavier de la tablette : AZERTY (France)
    séparateur décimal     : ","
    poids tapé en          : kg, 3 décimales
    après la pesée         : rien
    balance                : 9600 bauds, 8N1 (Elicom S300FM : PROT1=08)
    mode Auto              : désactivé

  Arduino IDE : carte "XIAO_ESP32S3" (paquet esp32 d'Espressif),
  menu Outils > USB Mode : "USB-OTG (TinyUSB)".
*/
#include "USB.h"
#include "USBHIDKeyboard.h"

USBHIDKeyboard clavier;

// ---------------- Broches (circuit pave-balance v0.1) ----------------
const uint8_t LIGNES[4]   = {D0, D1, D2, D3};     // rangées, de l'arrière vers l'avant
const uint8_t COLONNES[4] = {D4, D5, D6, D10};    // colonnes, de gauche à droite
const uint8_t BROCHE_LED  = D9;
const uint8_t RX_A = D7;                          // MAX3232 R1OUT (RJ12 broche 5)
const uint8_t RX_B = D8;                          // MAX3232 R2OUT (RJ12 broche 4)

// ---------------- Réglages ----------------
const uint32_t VITESSE      = 9600;
const uint8_t  DECIMALES    = 3;          // 0 = grammes
const uint8_t  APRES_PESEE  = 0;          // 0 rien, 1 Entrée, 2 Tabulation
const bool     AUTO_PERMIS  = false;
const uint32_t FRAICHEUR_MS = 1500;       // une mesure plus vieille est ignorée
const uint32_t ATTENTE_STABLE_MS = 3000;  // délai max pour une pesée stable
const long     SEUIL_ZERO_G = 5;          // en dessous : plateau vide
const long     SEUIL_ECART_G = 5;         // mode Auto : écart pour une nouvelle pesée
const uint8_t  ANTI_REBOND_MS = 25;

// Codes clavier USB {modificateur, touche} pour 0..9, puis le séparateur
const uint8_t CODE_CHIFFRE[10][2] = {{0x02, 0x27}, {0x02, 0x1E}, {0x02, 0x1F}, {0x02, 0x20}, {0x02, 0x21}, {0x02, 0x22}, {0x02, 0x23}, {0x02, 0x24}, {0x02, 0x25}, {0x02, 0x26}};
const uint8_t CODE_SEPARATEUR[2] = {0x00, 0x10};
const uint8_t CODE_ENTREE = 0x28, CODE_EFFACER = 0x2A, CODE_TAB = 0x2B;

enum Action : uint8_t { RIEN, CHIFFRE, DOUBLE_ZERO, SEPARATEUR, EFFACER, ENTREE, TAB, PESER, AUTO };
struct Touche { Action action; uint8_t valeur; };

// Disposition des 16 touches, vue de face (rangée du haut = arrière du pavé)
const Touche TOUCHES[4][4] = {
  {{CHIFFRE, 1}, {CHIFFRE, 2}, {CHIFFRE, 3}, {EFFACER, 0}},
  {{CHIFFRE, 4}, {CHIFFRE, 5}, {CHIFFRE, 6}, {PESER, 0}},
  {{CHIFFRE, 7}, {CHIFFRE, 8}, {CHIFFRE, 9}, {ENTREE, 0}},
  {{CHIFFRE, 0}, {DOUBLE_ZERO, 0}, {SEPARATEUR, 0}, {AUTO, 0}}
};

// ---------------- Envoi des touches ----------------
void appuyer(uint8_t modificateur, uint8_t code) {
  KeyReport r = {modificateur, 0, {code, 0, 0, 0, 0, 0}};
  clavier.sendReport(&r);
  delay(12);
  KeyReport vide = {0, 0, {0, 0, 0, 0, 0, 0}};
  clavier.sendReport(&vide);
  delay(12);
}

void taperChiffre(uint8_t d) { appuyer(CODE_CHIFFRE[d][0], CODE_CHIFFRE[d][1]); }
void taperSeparateur() { appuyer(CODE_SEPARATEUR[0], CODE_SEPARATEUR[1]); }

// ---------------- Lecture de la balance ----------------
// Trame Elicom : 1 octet d'état, "+000.245", retour chariot (0x0D).
// État : 0x10 = stable, 0x08 = surcharge.
struct Mesure { long grammes; bool stable; bool surcharge; uint32_t quand; bool valide; };
Mesure derniere = {0, false, false, 0, false};

struct Lecteur { uint8_t t[16]; uint8_t n; };
Lecteur lecteurA = {{0}, 0}, lecteurB = {{0}, 0};

void traiterTrame(const uint8_t *t, uint8_t n) {
  if (n != 9) return;
  const uint8_t *v = t + 1;                       // "+000.245"
  if ((v[0] != '+' && v[0] != '-') || v[4] != '.') return;
  const uint8_t chiffres[6] = {1, 2, 3, 5, 6, 7};
  long g = 0;
  for (uint8_t i = 0; i < 6; i++) {
    uint8_t c = v[chiffres[i]];
    if (c < '0' || c > '9') return;
    g = g * 10 + (c - '0');
  }
  if (v[0] == '-') g = -g;
  derniere = {g, (t[0] & 0x10) != 0, (t[0] & 0x08) != 0, (uint32_t)millis(), true};
}

void lire(HardwareSerial &port, Lecteur &l) {
  while (port.available()) {
    uint8_t c = port.read();
    if (c == 0x0D) { traiterTrame(l.t, l.n); l.n = 0; }
    else if (c == 0x0A) { /* ignoré */ }
    else if (l.n < sizeof(l.t)) l.t[l.n++] = c;
    else l.n = 0;
  }
}

bool mesureFraiche() { return derniere.valide && millis() - derniere.quand < FRAICHEUR_MS; }

void lireBalance() { lire(Serial1, lecteurA); lire(Serial2, lecteurB); }

// ---------------- LED ----------------
bool modeAuto = false;
void clignoter(uint8_t fois) {
  for (uint8_t i = 0; i < fois; i++) {
    digitalWrite(BROCHE_LED, HIGH); delay(90);
    digitalWrite(BROCHE_LED, LOW);  delay(90);
  }
}
void majLed() {
  bool allumee = mesureFraiche();
  if (modeAuto) allumee = (millis() / 500) % 2;  // clignote lentement en mode Auto
  digitalWrite(BROCHE_LED, allumee ? HIGH : LOW);
}

// ---------------- Pesée ----------------
void taperPoids(long g) {
  if (DECIMALES == 0) {
    char b[12]; snprintf(b, sizeof(b), "%ld", g);
    for (char *p = b; *p; p++) taperChiffre(*p - '0');
  } else {
    long diviseur = DECIMALES == 3 ? 1 : 10;
    long valeur = (g + diviseur / 2) / diviseur;  // arrondi (2 décimales : au centième de kg)
    long entier = valeur / (DECIMALES == 3 ? 1000 : 100);
    long reste = valeur % (DECIMALES == 3 ? 1000 : 100);
    char b[12]; snprintf(b, sizeof(b), "%ld", entier);
    for (char *p = b; *p; p++) taperChiffre(*p - '0');
    taperSeparateur();
    char r[4]; snprintf(r, sizeof(r), DECIMALES == 3 ? "%03ld" : "%02ld", reste);
    for (char *p = r; *p; p++) taperChiffre(*p - '0');
  }
  if (APRES_PESEE == 1) appuyer(0, CODE_ENTREE);
  if (APRES_PESEE == 2) appuyer(0, CODE_TAB);
}

// Attend une mesure stable et valable ; renvoie false (et clignote) sinon.
bool peser(long &g) {
  uint32_t debut = millis();
  while (millis() - debut < ATTENTE_STABLE_MS) {
    lireBalance();
    if (mesureFraiche() && derniere.stable && !derniere.surcharge && derniere.grammes > 0) {
      g = derniere.grammes;
      return true;
    }
    delay(5);
  }
  if (!mesureFraiche()) clignoter(2);        // balance muette : 2 éclairs
  else if (derniere.surcharge) clignoter(4); // surcharge : 4 éclairs
  else clignoter(3);                         // instable ou négatif : 3 éclairs
  return false;
}

long dernierTape = 0;
void automatisme() {
  if (!modeAuto || !mesureFraiche() || !derniere.stable || derniere.surcharge) return;
  long g = derniere.grammes;
  if (g < SEUIL_ZERO_G) { dernierTape = 0; return; }        // plateau vidé
  if (labs(g - dernierTape) < SEUIL_ECART_G) return;        // déjà tapé
  taperPoids(g);
  dernierTape = g;
}

// ---------------- Clavier matriciel ----------------
bool etat[4][4], brut[4][4];
uint32_t change[4][4];

void action(const Touche &t) {
  switch (t.action) {
    case CHIFFRE:     taperChiffre(t.valeur); break;
    case DOUBLE_ZERO: taperChiffre(0); taperChiffre(0); break;
    case SEPARATEUR:  taperSeparateur(); break;
    case EFFACER:     appuyer(0, CODE_EFFACER); break;
    case ENTREE:      appuyer(0, CODE_ENTREE); break;
    case TAB:         appuyer(0, CODE_TAB); break;
    case PESER: { long g; if (peser(g)) { taperPoids(g); dernierTape = g; } break; }
    case AUTO:
      if (AUTO_PERMIS) { modeAuto = !modeAuto; dernierTape = mesureFraiche() ? derniere.grammes : 0; }
      else clignoter(1);
      break;
    default: break;
  }
}

void scanner() {
  for (uint8_t r = 0; r < 4; r++) {
    pinMode(LIGNES[r], OUTPUT);
    digitalWrite(LIGNES[r], LOW);
    delayMicroseconds(30);
    for (uint8_t c = 0; c < 4; c++) {
      bool appuye = digitalRead(COLONNES[c]) == LOW;
      if (appuye != brut[r][c]) { brut[r][c] = appuye; change[r][c] = millis(); }
      if (brut[r][c] != etat[r][c] && millis() - change[r][c] >= ANTI_REBOND_MS) {
        etat[r][c] = brut[r][c];
        if (etat[r][c]) action(TOUCHES[r][c]);
      }
    }
    pinMode(LIGNES[r], INPUT);   // rangée au repos : haute impédance
  }
}

void setup() {
  for (uint8_t r = 0; r < 4; r++) pinMode(LIGNES[r], INPUT);
  for (uint8_t c = 0; c < 4; c++) pinMode(COLONNES[c], INPUT_PULLUP);
  pinMode(BROCHE_LED, OUTPUT);
  Serial1.begin(VITESSE, SERIAL_8N1, RX_A, -1);   // réception seule : rien n'est envoyé à la balance
  Serial2.begin(VITESSE, SERIAL_8N1, RX_B, -1);
  USB.productName("Pave balance");
  clavier.begin();
  USB.begin();
  clignoter(3);                                   // démarrage
}

void loop() {
  lireBalance();
  scanner();
  automatisme();
  majLed();
  delay(2);
}

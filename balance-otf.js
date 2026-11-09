/* Balance Elicom S300FM -> caisse Ouvretaferme.
   Ajoute « Prendre le poids » dans la fenêtre d'un article vendu au kg.
   Ne clique jamais sur « Enregistrer ». Mode : window.__BALANCE_MODE = 'sim' ou 'ble'. */
(function (root) {
  'use strict';

  var CONFIG = {
    /* À renseigner après le relevé nRF Connect. Tant que c'est null, le premier
       service de la liste ci-dessous qui offre une notification est utilisé. */
    serviceUuid: null,
    characteristicUuid: null,
    /* Hypothèses courantes pour ces modules, non vérifiées sur le SH-B30-BLE. */
    servicesPossibles: [0xffe0, 0xfff0, '6e400001-b5a3-f393-e0a9-e50e24dcca9e', '49535343-fe7d-4ae5-8fa9-9fafd205e455'],
    ageMaxMs: 2500
  };
  var SEUIL_ZERO = 0.005;
  var SEUIL_ECART = 0.0045;

  /* ---------- Trames : P+000.245\r ---------- */
  function lireTrame(octets) {
    if (octets.length !== 9) return null;
    var texte = '';
    for (var i = 1; i < 9; i++) texte += String.fromCharCode(octets[i]);
    if (!/^[+-]\d{3}\.\d{3}$/.test(texte)) return null;
    return { kg: parseFloat(texte), stable: !!(octets[0] & 0x10), surcharge: !!(octets[0] & 0x08) };
  }

  function creerLecteur(horloge) {
    var tampon = [], derniere = null, recueA = 0;
    horloge = horloge || Date.now;
    return {
      /* Accepte des morceaux de trame ou plusieurs trames à la fois. */
      recevoir: function (octets) {
        for (var i = 0; i < octets.length; i++) {
          if (octets[i] === 0x0d) {
            var trame = lireTrame(tampon);
            tampon = [];
            if (trame) { derniere = trame; recueA = horloge(); }
          } else {
            tampon.push(octets[i]);
            if (tampon.length > 32) tampon = [];
          }
        }
      },
      oublier: function () { tampon = []; derniere = null; recueA = 0; },
      /* Seule la toute dernière trame compte : si elle n'est pas stable, on refuse. */
      mesure: function () {
        if (!derniere) return { ok: false, raison: 'Aucune mesure reçue' };
        if (horloge() - recueA > CONFIG.ageMaxMs) return { ok: false, raison: 'Mesure trop ancienne' };
        if (derniere.surcharge) return { ok: false, raison: 'Balance en surcharge', kg: derniere.kg };
        if (derniere.kg < 0) return { ok: false, raison: 'Poids négatif', kg: derniere.kg };
        if (!derniere.stable) return { ok: false, raison: 'Poids en mouvement', kg: derniere.kg };
        return { ok: true, kg: derniere.kg, valeur: derniere.kg.toFixed(3) };
      }
    };
  }

  function fabriquerTrame(kg, stable, surcharge) {
    var a = Math.abs(kg).toFixed(3);
    while (a.length < 7) a = '0' + a;
    var txt = (kg < 0 ? '-' : '+') + a, o = [0x40 | (stable ? 0x10 : 0) | (surcharge ? 0x08 : 0)];
    for (var i = 0; i < txt.length; i++) o.push(txt.charCodeAt(i));
    o.push(0x0d);
    return o;
  }

  /* ---------- Bluetooth ---------- */
  var FFE0 = '0000ffe0-0000-1000-8000-00805f9b34fb';

  function surIos() {
    return /iPad|iPhone|Bluefy/.test(navigator.userAgent) || (/Mac/.test(navigator.platform) && navigator.maxTouchPoints > 1);
  }

  /* La caisse ajoute des fonctions énumérables à Array et String, ce qui peut perturber Bluefy. */
  function masquerAjoutsPrototypes() {
    [Object.prototype, Array.prototype, String.prototype].forEach(function (p) {
      Object.keys(p).forEach(function (k) { Object.defineProperty(p, k, { enumerable: false }); });
    });
  }

  /* Bluefy rejette certaines recherches avec un simple code : on essaie les formes possibles. */
  async function chercherIos(bluetooth) {
    masquerAjoutsPrototypes();
    var essais = [
      { filters: [{ namePrefix: 'SH-B30' }], optionalServices: [FFE0] },
      { acceptAllDevices: true, optionalServices: [FFE0] },
      { filters: [{ services: [FFE0] }] },
      { acceptAllDevices: true }
    ], erreurs = [];
    for (var i = 0; i < essais.length; i++) {
      try {
        return await bluetooth.requestDevice(essais[i]);
      } catch (e) {
        if (e && e.name === 'NotFoundError') throw e;
        erreurs.push((i + 1) + '=' + (e && e.message ? e.message : String(e)));
      }
    }
    throw new Error('Essais ' + erreurs.join(', '));
  }

  async function connecterBle(bluetooth, lecteur, signaler, ios) {
    if (!bluetooth) throw new Error('Bluetooth indisponible dans ce navigateur');
    var liste = CONFIG.serviceUuid ? [CONFIG.serviceUuid] : CONFIG.servicesPossibles;
    /* Bluefy : recherche par nom et identifiant complet, sans « tous les appareils ». */
    var appareil = ios ? await chercherIos(bluetooth) : await bluetooth.requestDevice({ acceptAllDevices: true, optionalServices: liste });
    appareil.addEventListener('gattserverdisconnected', function () {
      lecteur.oublier();
      signaler('Balance déconnectée');
    });
    var serveur = await appareil.gatt.connect();
    var uuidService = ios ? FFE0 : CONFIG.serviceUuid;
    var services = uuidService ? [await serveur.getPrimaryService(uuidService)] : await serveur.getPrimaryServices();
    for (var s = 0; s < services.length; s++) {
      var carac = await services[s].getCharacteristics();
      for (var c = 0; c < carac.length; c++) {
        var ch = carac[c];
        if (CONFIG.characteristicUuid ? ch.uuid !== CONFIG.characteristicUuid : !ch.properties.notify) continue;
        ch.addEventListener('characteristicvaluechanged', function (e) {
          var v = e.target.value;
          lecteur.recevoir(new Uint8Array(v.buffer, v.byteOffset, v.byteLength));
        });
        await ch.startNotifications();
        return { service: services[s].uuid, caracteristique: ch.uuid, deconnecter: function () { appareil.gatt.disconnect(); } };
      }
    }
    appareil.gatt.disconnect();
    throw new Error('Aucune caractéristique de notification trouvée');
  }

  /* ---------- USB : câble DSD TECH SH-RJ12B (puce CP2102N), 9600 8N1 ---------- */
  var USB_CP210X = { vendorId: 0x10c4, productId: 0xea60 };

  async function reglerCp210x(usb, numero) {
    function cmd(request, value, data) {
      return usb.controlTransferOut({ requestType: 'vendor', recipient: 'interface', request: request, value: value, index: numero }, data);
    }
    await cmd(0x00, 0x0001);          /* active l'interface */
    await cmd(0x03, 0x0800);          /* 8 bits, sans parité, 1 bit d'arrêt */
    await cmd(0x1e, 0, new Uint8Array([0x80, 0x25, 0x00, 0x00]));   /* 9600 bauds */
    await cmd(0x07, 0x0303);          /* DTR et RTS actifs */
  }

  async function ouvrirUsb(usb, appareil, lecteur, signaler) {
    await appareil.open();
    if (!appareil.configuration) await appareil.selectConfiguration(1);
    var interf = appareil.configuration.interfaces[0], numero = interf.interfaceNumber;
    try {
      await appareil.claimInterface(numero);
    } catch (e) {
      throw new Error('Câble réservé par Android : USB direct impossible');
    }
    var entree = interf.alternate.endpoints.filter(function (p) { return p.direction === 'in' && p.type === 'bulk'; })[0];
    if (!entree) throw new Error('Câble USB non reconnu');
    await reglerCp210x(appareil, numero);
    var actif = true;
    function fin(message) {
      if (!actif) return;
      actif = false;
      lecteur.oublier();
      usb.removeEventListener('disconnect', surRetrait);
      signaler(message);
    }
    function surRetrait(e) { if (e.device === appareil) fin('Câble USB débranché'); }
    usb.addEventListener('disconnect', surRetrait);
    (async function () {
      try {
        while (actif) {
          var r = await appareil.transferIn(entree.endpointNumber, 64);
          if (r.status !== 'ok') throw new Error(r.status);
          if (r.data && r.data.byteLength) lecteur.recevoir(new Uint8Array(r.data.buffer, r.data.byteOffset, r.data.byteLength));
        }
      } catch (e) {
        fin('Liaison USB perdue');
      }
    })();
    return { deconnecter: function () { actif = false; lecteur.oublier(); usb.removeEventListener('disconnect', surRetrait); appareil.close().catch(function () {}); } };
  }

  async function connecterUsb(usb, lecteur, signaler) {
    if (!usb) throw new Error('USB indisponible dans ce navigateur');
    var appareil = await usb.requestDevice({ filters: [USB_CP210X] });
    return ouvrirUsb(usb, appareil, lecteur, signaler);
  }

  /* Reprend le câble déjà autorisé, pour éviter de le rechoisir à chaque lancement. */
  async function reconnecterUsb(usb, lecteur, signaler) {
    if (!usb || !usb.getDevices) return null;
    var liste = (await usb.getDevices()).filter(function (d) { return d.vendorId === USB_CP210X.vendorId && d.productId === USB_CP210X.productId; });
    return liste.length === 1 ? ouvrirUsb(usb, liste[0], lecteur, signaler) : null;
  }

  /* ---------- Caisse ---------- */
  function visibles(doc) {
    return Array.prototype.filter.call(doc.querySelectorAll('input[name^="number["]'), function (e) { return (e.closest('.merchant-field') || e).offsetParent !== null; });
  }

  /* Le texte propre d'un élément, sans celui du bouton ajouté dedans. */
  function texteDe(k) {
    return Array.prototype.map.call(k.childNodes, function (n) { return n.nodeType === 3 ? n.nodeValue : (n.hasAttribute && n.hasAttribute('data-balance') ? '' : n.textContent); }).join('').trim();
  }

  function trouverChamp(doc) {
    var champs = visibles(doc);
    if (champs.length !== 1) return null;
    var bloc = champs[0];
    for (var n = 0; n < 5 && bloc.parentElement; n++) {
      bloc = bloc.parentElement;
      var feuilles = Array.prototype.filter.call(bloc.querySelectorAll('*'), function (k) {
        if (k.hasAttribute('data-balance')) return false;
        var seulBouton = k.children.length === 1 && k.children[0].hasAttribute('data-balance');
        return (!k.children.length || seulBouton) && texteDe(k);
      });
      var textes = feuilles.map(texteDe);
      var i = textes.indexOf('Vendu');
      if (i < 0) continue;
      var fin = textes.findIndex(function (t, x) { return x > i && t.indexOf('€') >= 0; });
      var unites = textes.slice(i + 1, fin < 0 ? undefined : fin);
      return { champ: champs[0], etiquette: feuilles[i], auKilo: unites.indexOf('kg') >= 0 };
    }
    return null;
  }

  function ecrire(champ, valeur) {
    /* Le pavé tactile de la caisse limite à 2 décimales et ne recalcule pas le montant :
       on passe l'article en saisie clavier, comme avec l'icône clavier. */
    var article = champ.closest('.merchant'), lien = article && article.querySelector('.merchant-switch-keyboard-link');
    if (lien && article.classList.contains('merchant-switch-touch')) lien.click();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(champ, valeur);
    champ.dispatchEvent(new Event('input', { bubbles: true }));
    /* Sur écran tactile, la caisse masque le champ et affiche sa valeur dans ce bloc. */
    var zone = champ.closest('.merchant-field'), affichage = zone && zone.querySelector('.merchant-value');
    if (affichage) affichage.textContent = valeur.replace('.', ',');
    champ.blur();
  }

  function fr(kg) { return kg.toFixed(3).replace('.', ',') + ' kg'; }

  function creerElement(tag, style, texte) {
    var e = document.createElement(tag);
    e.style.cssText = style;
    if (texte) e.textContent = texte;
    return e;
  }

  function demarrer() {
    if (root.__balanceOtf) root.__balanceOtf.arreter();
    var mode = root.__BALANCE_MODE === 'sim' ? 'sim' : 'ble';
    var lecteur = creerLecteur(), liaison = null, sim = null, note = '', noteJusque = 0;

    /* Petit bandeau dans l'en-tête sombre de la caisse, entre le titre et les menus. */
    var barre = creerElement('div', 'position:fixed;top:12px;z-index:2147483000;background:#222;color:#fff;font:600 15px system-ui,sans-serif;padding:5px 4px 5px 10px;border-radius:8px;display:flex;align-items:center;gap:6px;max-width:calc(100vw - 184px);box-sizing:border-box;box-shadow:0 0 0 1px rgba(255,255,255,.25)');
    var etat = creerElement('div', 'line-height:1.15;min-width:0');
    var commandes = creerElement('div', 'display:flex;gap:2px;align-items:center;flex:none');
    var styleBtn = 'border:0;border-radius:6px;padding:4px 7px;font:600 12px system-ui,sans-serif;background:#fff;color:#222;cursor:pointer';
    var btnBle = null, panneauSim = null;
    /* Mode automatique : entre deux pesées, le poids doit changer ou repasser par zéro. */
    var auto = true, zeroVu = true, dernierKg = null, ouvert = null;
    try { auto = localStorage.getItem('balance-otf-auto') !== '0'; } catch (e) {}
    barre.appendChild(etat); barre.appendChild(commandes);
    document.body.appendChild(barre);

    function montantDe(champ) {
      var p = champ.form && champ.form.querySelector('input[name="price[' + champ.name.replace(/\D/g, '') + ']"]');
      return p ? parseFloat(p.value) : NaN;
    }

    function boutonEnregistrer(champ) {
      var b = champ.form ? Array.prototype.filter.call(champ.form.querySelectorAll('button'), function (x) { return x.textContent.trim() === 'Enregistrer'; }) : [];
      return b.length === 1 ? b[0] : null;
    }

    /* Appelé à chaque rafraîchissement : décide une seule fois par ouverture d'article. */
    function automatisme(cible, m) {
      if (m.ok && (m.kg < SEUIL_ZERO || (dernierKg !== null && Math.abs(m.kg - dernierKg) >= SEUIL_ECART))) zeroVu = true;
      if (!cible || !cible.auKilo) { ouvert = null; return; }
      if (ouvert !== cible.champ) {
        ouvert = cible.champ;
        ouvert.__balanceFait = cible.champ.value !== '';
        if (ouvert.__balanceFait && auto) noter('Correction : poids conservé');
      }
      if (!auto || ouvert.__balanceFait || cible.champ.value !== '') return;
      if (!m.ok || m.kg < SEUIL_ZERO) return;
      if (!zeroVu) return noter('Même poids : changez le produit');
      ouvert.__balanceFait = true;
      var champ = cible.champ, enreg = boutonEnregistrer(champ), poids = m.kg;
      if (!enreg) return noter('Enregistrez à la main');
      ecrire(champ, m.valeur);
      setTimeout(function () {
        if (!(montantDe(champ) > 0)) return noter('Montant non calculé : à vérifier');
        zeroVu = false;
        dernierKg = poids;
        enreg.click();
      }, 150);
    }

    function noter(t) { note = t; noteJusque = Date.now() + 4000; }

    function dire(t, duree) { note = t; noteJusque = Date.now() + (duree || 4000); rafraichir(); }

    if (mode === 'ble') {
      var relier = function (promesse) {
        promesse.then(function (l) {
          if (!l) return;
          if (liaison) liaison.deconnecter();
          liaison = l;
          dire('Connectée');
        }).catch(function (e) { dire('Erreur ' + (e && e.name ? e.name + ' : ' : '') + (e && e.message ? e.message : String(e)), 30000); });
      };
      var perdu = function (t) { liaison = null; dire(t); };
      btnBle = creerElement('button', styleBtn, 'Bluetooth');
      if (surIos()) {
        /* Comme la page d'exemple qui marche dans Bluefy : formulaire et appel immédiat au toucher. */
        var formBle = document.createElement('form');
        formBle.style.display = 'contents';
        btnBle.type = 'submit';
        formBle.onsubmit = function (ev) {
          ev.preventDefault();
          masquerAjoutsPrototypes();
          var demande = navigator.bluetooth.requestDevice({ acceptAllDevices: true, optionalServices: [FFE0] });
          relier(connecterBle({ requestDevice: function () { return demande; } }, lecteur, perdu, true));
        };
        formBle.appendChild(btnBle);
        commandes.appendChild(formBle);
      } else {
        btnBle.type = 'button';
        btnBle.onclick = function () { dire('Recherche du module…'); relier(connecterBle(navigator.bluetooth, lecteur, perdu, false)); };
        commandes.appendChild(btnBle);
      }
    } else {
      sim = { kg: 0.245, stable: true, surcharge: false, coupe: false };
      panneauSim = creerElement('div', 'position:fixed;right:12px;bottom:12px;z-index:2147483000;background:#222;color:#fff;font:14px system-ui,sans-serif;padding:8px;border-radius:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center');
      document.body.appendChild(panneauSim);
      var saisie = creerElement('input', 'width:80px;padding:7px;border:0;border-radius:6px;font:14px system-ui');
      saisie.type = 'number'; saisie.step = '0.001'; saisie.value = '0.245';
      saisie.oninput = function () { var v = parseFloat(saisie.value); sim.kg = isNaN(v) ? 0 : v; };
      panneauSim.appendChild(saisie);
      [['stable', 'Stable', true], ['surcharge', 'Surcharge', false], ['coupe', 'Coupée', false]].forEach(function (d) {
        var l = creerElement('label', 'font-size:13px;display:flex;align-items:center;gap:3px');
        var c = document.createElement('input');
        c.type = 'checkbox'; c.checked = d[2];
        c.onchange = function () { sim[d[0]] = c.checked; if (d[0] === 'coupe' && c.checked) lecteur.oublier(); };
        l.appendChild(c); l.appendChild(document.createTextNode(d[1]));
        panneauSim.appendChild(l);
      });
      /* Envoie la trame en deux morceaux, comme une notification Bluetooth peut le faire. */
      var tic = function () {
        if (sim.coupe) return;
        var o = fabriquerTrame(sim.kg, sim.stable, sim.surcharge), m = 1 + Math.floor(Math.random() * (o.length - 1));
        lecteur.recevoir(o.slice(0, m)); lecteur.recevoir(o.slice(m));
      };
      tic();
      sim.minuteur = setInterval(tic, 1000);
    }

    var btnAuto = creerElement('button', styleBtn, 'Auto');
    btnAuto.type = 'button';
    btnAuto.onclick = function () {
      auto = !auto;
      try { localStorage.setItem('balance-otf-auto', auto ? '1' : '0'); } catch (e) {}
      rafraichir();
    };
    commandes.appendChild(btnAuto);

    var btnFin = creerElement('button', 'border:0;background:none;color:#fff;font:700 18px/1 system-ui,sans-serif;padding:2px 6px;cursor:pointer', '×');
    btnFin.setAttribute('aria-label', 'Retirer');
    btnFin.type = 'button';
    btnFin.onclick = function () { root.__balanceOtf.arreter(); };
    commandes.appendChild(btnFin);

    /* Placé DANS l'étiquette « Vendu » pour ne pas décaler la grille de la fenêtre. */
    var bouton = creerElement('div', 'display:block;width:max-content;margin-top:4px;border:0;border-radius:7px;padding:6px 10px;font:600 14px system-ui,sans-serif;background:#2e7d32;color:#fff;cursor:pointer;line-height:1.2');
    bouton.setAttribute('role', 'button');
    bouton.setAttribute('data-balance', '1');
    bouton.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      var cible = trouverChamp(document), m = lecteur.mesure();
      if (!cible || !cible.auKilo) return dire('Champ ambigu : rien modifié');
      if (!m.ok) return dire(m.raison + ' : rien modifié');
      ecrire(cible.champ, m.valeur);
    });

    function rafraichir() {
      var m = lecteur.mesure();
      etat.textContent = Date.now() < noteJusque ? note : (m.ok ? fr(m.kg) : m.raison);
      etat.style.fontSize = (m.ok && Date.now() >= noteJusque) ? '17px' : '12px';
      barre.style.right = (window.innerWidth < 700 ? 88 : 450) + 'px';
      if (btnBle) btnBle.style.display = liaison ? 'none' : '';
      bouton.textContent = 'Poids';
      bouton.style.background = m.ok ? '#2e7d32' : '#888';
      btnAuto.style.background = auto ? '#2e7d32' : '#777';
      btnAuto.style.color = '#fff';
      var cible = trouverChamp(document);
      automatisme(cible, m);
      if (cible && cible.auKilo) {
        if (bouton.parentNode !== cible.etiquette) cible.etiquette.appendChild(bouton);
      } else if (bouton.parentNode) {
        bouton.parentNode.removeChild(bouton);
      }
    }

    var minuteurUi = setInterval(rafraichir, 250);
    rafraichir();
    root.__balanceOtf = { sim: sim,
      arreter: function () {
        clearInterval(minuteurUi);
        if (sim) clearInterval(sim.minuteur);
        if (liaison) liaison.deconnecter();
        if (bouton.parentNode) bouton.parentNode.removeChild(bouton);
        barre.parentNode.removeChild(barre);
        if (panneauSim) panneauSim.parentNode.removeChild(panneauSim);
        root.__balanceOtf = null;
      }
    };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { lireTrame: lireTrame, creerLecteur: creerLecteur, fabriquerTrame: fabriquerTrame, connecterBle: connecterBle, connecterUsb: connecterUsb, reconnecterUsb: reconnecterUsb, CONFIG: CONFIG };
  } else {
    demarrer();
  }
})(typeof window !== 'undefined' ? window : globalThis);

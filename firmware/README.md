# Programme du pavé balance (XIAO ESP32-S3)

> **Prototype non testé sur le matériel.** Essais uniquement, jamais pour vendre au poids.

- `pave_balance/pave_balance.ino` : programme avec les réglages d'origine (clavier AZERTY, virgule, kg à 3 décimales, Auto désactivé).
- `generer-firmware.js` : générateur utilisé par la page du kit ([`docs/kit/`](../docs/kit/index.html), en ligne sur https://nicolasmieral-wq.github.io/balance-connectee-otf/) pour produire un programme selon la tablette.

Le pavé se présente comme un clavier USB : il marche sur Android et iPad sans application.

## Charger le programme

1. Arduino IDE 2, paquet de cartes **esp32** d'Espressif (URL : `https://espressif.github.io/arduino-esp32/package_esp32_index.json`).
2. Carte **XIAO_ESP32S3**, menu **Outils → USB Mode → USB-OTG (TinyUSB)**.
3. Téléverser. Si le port n'apparaît pas : maintenir **B**, brancher, relâcher, téléverser, appuyer sur **R**.

## Vérifications faites

- Compilation syntaxique sur ordinateur avec des en-têtes simulés, conformes aux en-têtes réels d'arduino-esp32 (`USBHIDKeyboard::sendReport`, `KeyReport`, broches D0-D10 du XIAO).
- Simulation de la lecture des trames et de la frappe : 1,245 kg tapé `1,25` en 2 décimales, refus en cas d'instabilité, de surcharge, de poids négatif ou de balance muette ; mode Auto qui ignore un écart de 2 g et tape un nouvel ajout au panier.
- Pas encore compilé avec le vrai paquet esp32, ni essayé sur le XIAO.

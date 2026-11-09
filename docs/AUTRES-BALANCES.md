# Autres balances et protocoles

## Le format attendu

Le script comprend une trame de 10 octets, envoyée en continu :

```
P+000.245\r
```

| Octets | Rôle |
|---|---|
| 1 | Octet d'état : bit `0x10` = poids stable, bit `0x08` = surcharge |
| 2 à 9 | Poids en kilogrammes, signe compris : `+000.245` |
| 10 | Retour chariot `\r` (0x0D) |

Toute balance qui envoie exactement ce format en RS-232 devrait fonctionner avec le module SH-B30-BLE. Ne supposez pas que l'octet d'état est toujours `P` : seuls ses bits comptent.

## Elicom S300FM : protocoles connus

La notice et la documentation du protocole S300 décrivent plusieurs modes (`PROT1`). Seul le premier a été testé.

| `PROT1` | Description | État |
|---|---|---|
| `08.00` | Envoi continu, sans demande | ✅ Testé, c'est le mode utilisé |
| `07.00` | Lecture sur demande, en envoyant `0x05` ou `0xF1` | Non testé |
| `10.00` / `10.01` | Protocole de type Mettler : `S` = poids stable, `SI` = poids immédiat, fin de commande `CR LF`. Poids en grammes (`10.00`) ou en kilogrammes (`10.01`) | Non testé |
| `16.00` | Protocoles EWI, programmation des PLU et étiquettes | Non testé |

Les modes sur demande obligeraient le script à envoyer une commande à la balance. Il faudrait alors relier aussi la broche 4 de la balance (RXD) à la broche 3 du module.

## Ajouter une balance

Si votre balance envoie un autre format, ouvrez une demande sur ce dépôt en indiquant :

- la marque et le modèle ;
- les réglages de communication (vitesse, parité, mode d'envoi) ;
- quelques trames réelles copiées depuis un terminal, en précisant le poids posé et si la balance était stable.

C'est la fonction `lireTrame` de `balance-otf.js` qu'il faudrait compléter.

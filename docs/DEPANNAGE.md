# Dépannage

## Le favori ne fait rien

- Lancez-le depuis la **barre d'adresse** (taper son nom, toucher la suggestion), pas depuis la liste des favoris.
- Vérifiez qu'il commence par `javascript:` : Chrome efface parfois ce début quand on colle la ligne.
- Vérifiez que l'adresse du script s'ouvre dans le navigateur et affiche du code.

## Le bandeau montre une ancienne version

Le téléphone garde le script en mémoire. Le favori avec `?v='+Date.now()` évite ce problème. Sinon, ouvrez l'adresse du script, rechargez-la, puis rechargez la caisse.

## « Aucune mesure reçue »

Le Bluetooth est relié, mais aucun poids n'arrive.

1. La balance est-elle bien en `PROT1 = 08` et 9600 bauds ?
2. Les cavaliers du module sont-ils sur **Device** ?
3. Le fil TXD de la balance arrive-t-il sur la **broche 2** du DB9 ? Vérifiez au multimètre et avec un ordinateur (voir [Câblage](CABLAGE.md)).
4. Dans nRF Connect, des notifications arrivent-elles ? Si oui, le problème vient du téléphone ou du script ; sinon, du câble ou des réglages.

## Le Bluetooth ne trouve pas le module

- Le module est-il alimenté ?
- Est-il déjà connecté ailleurs (nRF Connect, un autre téléphone) ? Il n'accepte qu'une connexion à la fois.
- Le Bluetooth et la localisation sont-ils activés sur le téléphone ?

## « Poids en mouvement », « Balance en surcharge », « Poids négatif »

Attendez que la balance soit stable, retirez la surcharge, ou faites la tare.

## « Même poids : changez le produit »

Le poids n'a pas changé depuis la dernière pesée enregistrée. Changez de produit, ou soulevez le panier pour repasser par zéro. Deux produits de poids rigoureusement identique doivent être saisis avec le bouton **Poids**.

## « Correction : poids conservé »

L'article avait déjà un poids : le script n'y touche pas. Corrigez à la main ou touchez **Poids**.

## « Montant non calculé : à vérifier »

Le poids est écrit, mais la caisse n'a pas calculé le montant : rien n'est enregistré. Vérifiez la fenêtre et enregistrez à la main si tout est juste. Si ça se répète, la caisse a sans doute changé : signalez-le sur ce dépôt.

## « Champ ambigu : rien modifié »

Le script n'a pas reconnu le champ « Vendu ». Il préfère ne rien écrire. Saisissez le poids à la main.

## Un centime d'écart

Pour 0,155 kg à 3 €/kg, la fenêtre de la caisse a affiché 0,47 € et la ligne enregistrée 0,46 €. L'arrondi vient de la caisse, pas du script.

## Sur iPad

Avec Bluefy, le script se charge, mais la recherche Bluetooth est refusée avec le code 2. La page d'exemple Web Bluetooth de Google y trouve pourtant le module. La cause n'est pas encore trouvée : pour l'instant, utilisez Android.

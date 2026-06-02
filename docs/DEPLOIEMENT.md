# Où faire tourner l'observatoire ? (guide non technique)

L'outil doit s'exécuter **automatiquement à heures fixes** :

- Collecte Gmail → **lundi 7h**
- Collecte RSS → **tous les jours 8h**
- Synthèse hebdo → **vendredi 18h** (déposée dans le Drive, à valider avant publication)

Pour que ces rendez-vous soient tenus, il faut une machine **allumée à ces
heures-là**. Voici les options, de la plus simple à la plus robuste.

---

## Option 1 — Ton propre ordinateur 💻 *(pour démarrer / tester)*

**Pour qui :** valider que tout marche, sans rien payer.

- ✅ Gratuit, immédiat.
- ✅ Idéal pour les premiers essais et pour relire les synthèses.
- ⚠️ L'ordinateur doit être **allumé et connecté** aux heures programmées,
  sinon le rendez-vous est manqué (rattrapé au lancement suivant).

👉 Concrètement : tu installes l'outil une fois (script fourni `install.sh`),
puis tu peux soit lancer les scripts **à la main** quand tu veux, soit activer
la planification automatique.

## Option 2 — Un petit serveur cloud toujours allumé ☁️ *(recommandé à terme)* ⭐

**Pour qui :** « je veux que ça tourne tout seul sans y penser ».

- ✅ Allumé 24h/24 → tous les rendez-vous sont tenus, même PC éteint.
- ✅ ~4 à 6 € / mois (petit serveur « VPS » chez OVH, Scaleway, Hetzner…).
- ⚠️ Mise en route initiale = quelques commandes à copier-coller **une fois**
  (≈ 20 min). Je te les prépare clé en main ; tu peux les exécuter toi-même en
  suivant la procédure, ou les confier à une personne technique de ton entourage.

C'est l'option que je **recommande une fois les essais concluants** : fiable,
peu coûteuse, et tu n'as plus rien à gérer.

## Option 3 — Hébergement Google Cloud (avancé)

Possible (le tout étant déjà chez Google), mais la configuration est plus
technique que l'Option 2 sans bénéfice notable ici. **Non recommandé** pour un
usage non technique.

---

## Ma recommandation

1. **Maintenant :** Option 1 sur ton ordinateur, pour générer une première
   synthèse et vérifier que le résultat te convient.
2. **Ensuite :** Option 2 (petit serveur cloud) pour passer en pilote
   automatique. Préviens-moi quand tu y es, je te fournis le pas-à-pas exact
   pour le fournisseur choisi.

---

## Installation (commune aux options 1 et 2)

> Prérequis : **Python 3.11+** installé sur la machine.

```bash
# 1. Récupérer le code
git clone <url-du-depot> observatoire-business-sabaudo
cd observatoire-business-sabaudo

# 2. Installer (crée l'environnement + dépendances + fichier .env)
bash install.sh

# 3. Renseigner les secrets
#    - éditer .env  → coller la clé ANTHROPIC_API_KEY
#    - déposer config/credentials.json  (voir docs/SETUP_GOOGLE_OAUTH.md)

# 4. Premier test manuel
source .venv/bin/activate
python scripts/rss_collect.py        # collecte RSS
python scripts/gmail_collect.py      # collecte Gmail (ouvre l'autorisation Google la 1re fois)
python scripts/synthesize.py --upload  # synthèse + dépôt dans le Drive
```

La synthèse apparaît dans `02_Veille_traitée/Synthèses_hebdomadaires/` **et**
(avec `--upload`) dans le dossier Drive « Observatoire économique Sabaudo ».

## Activer la planification automatique

Une fois les tests concluants, sur la machine choisie :

```bash
# adapter les chemins en haut de crontab.txt si besoin, puis :
crontab crontab.txt
```

Les trois routines se déclencheront alors automatiquement aux horaires prévus.
Aucune synthèse n'est publiée automatiquement : elle est **déposée en brouillon**
dans le Drive, pour ta validation.

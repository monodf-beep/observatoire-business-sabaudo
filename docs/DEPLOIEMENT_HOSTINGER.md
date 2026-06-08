# Déployer sur ton VPS Hostinger (pas-à-pas, non technique)

Ton VPS est parfait : il est allumé en permanence, donc les collectes et la
synthèse se déclenchent toutes seules aux bonnes heures. Suis les étapes dans
l'ordre. Tu n'as **rien à coder**, juste à copier-coller.

> 🧩 Seul point un peu technique : l'autorisation Google (Partie B). On la fait
> en **mode manuel** directement sur le VPS — tu copies une URL, tu autorises
> dans ton navigateur, tu recolles l'URL de retour. C'est tout.

---

## Vue d'ensemble

```
A. Préparer le VPS        (terminal Hostinger — copier/coller)
B. Autoriser Google       (UNE fois, en mode manuel, directement sur le VPS)
D. Tester                 (une exécution manuelle)
E. Automatiser            (cron — et hop, ça tourne seul)
```

---

## Partie A — Préparer le VPS

### A1. Ouvrir le terminal du VPS

Le plus simple, sans rien installer : dans **hPanel Hostinger → VPS → ton
serveur → onglet « Terminal du navigateur »** (Browser terminal). Tu obtiens une
console noire où coller des commandes. *(Tu peux aussi utiliser SSH si tu sais
déjà le faire.)*

### A2. Régler le fuseau horaire (pour que 7h = 7h à Paris)

Par défaut un VPS est souvent à l'heure « UTC ». On le passe à l'heure française :

```bash
sudo timedatectl set-timezone Europe/Paris
date    # vérifie que l'heure affichée est la bonne
```

### A3. Installer les outils de base

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
python3 --version    # doit afficher 3.10 ou plus
```

### A4. Récupérer le code de l'observatoire

```bash
cd ~
git clone https://github.com/monodf-beep/observatoire-business-sabaudo.git
cd observatoire-business-sabaudo
git checkout claude/pensive-einstein-S5Fds
```

### A5. Installer l'outil

```bash
bash install.sh
```

### A6. Renseigner ta clé Anthropic

```bash
nano .env
```

Repère la ligne `ANTHROPIC_API_KEY=` et colle ta clé juste après le `=`.
Pour sauver dans `nano` : **Ctrl+O** puis **Entrée**, puis **Ctrl+X** pour quitter.

### A7. Déposer credentials.json sur le VPS

Tu dois d'abord avoir généré `credentials.json` en suivant
**[docs/SETUP_GOOGLE_OAUTH.md](SETUP_GOOGLE_OAUTH.md)**. Ensuite, sur le VPS :

```bash
nano config/credentials.json
```

Ouvre le `credentials.json` sur ton ordinateur avec un éditeur de texte,
**copie tout son contenu**, colle-le dans `nano`, puis sauve (Ctrl+O, Entrée, Ctrl+X).

---

## Partie B — Autoriser Google directement sur le VPS (mode manuel)

Pas besoin d'ordinateur ni de tunnel : le **mode manuel** fonctionne dans le
terminal du VPS. Le script affiche une URL, tu l'ouvres dans ton navigateur,
tu autorises, et tu recolles l'URL de redirection.

Sur le VPS :

```bash
cd ~/observatoire-business-sabaudo
source .venv/bin/activate
python scripts/authorize.py --manual
```

Le script demande l'autorisation **deux fois** (Gmail puis Drive). À chaque fois :

1. Le terminal affiche une longue **URL** → copie-la et ouvre-la dans ton
   navigateur (connecté à `franck.monod@culturasabauda.eu`).
2. Google affiche « Google n'a pas validé cette application » (normal en test) :
   **« Paramètres avancés » → « Accéder à Observatoire Sabaudo (non sécurisé) »**,
   coche les accès, **Continuer**.
3. Le navigateur affiche alors une page d'erreur **« localhost a refusé la
   connexion »** : **c'est NORMAL et attendu.** Regarde la barre d'adresse :
   l'URL contient `...?code=...`. **Copie l'URL complète.**
4. Reviens au terminal et **colle cette URL** à l'invite, puis Entrée.

À la fin, deux fichiers sont créés dans `config/` : `token.json` et
`token_drive.json`.

> Ces jetons se renouvellent ensuite **tout seuls** : tu ne referas plus jamais
> cette étape (sauf si tu changes les autorisations Google).

---

## Partie D — Tester sur le VPS

```bash
cd ~/observatoire-business-sabaudo
source .venv/bin/activate
python scripts/rss_collect.py          # collecte des flux
python scripts/gmail_collect.py        # collecte des emails
python scripts/synthesize.py --upload  # synthèse + dépôt dans le Drive
```

Si la synthèse apparaît dans ton dossier Drive « Observatoire économique
Sabaudo », **tout fonctionne** 🎉.

---

## Partie E — Automatiser (cron)

Active la planification (lundi 7h, tous les jours 8h, vendredi 15h) :

```bash
# adapter le chemin du projet dans crontab.txt si besoin :
nano crontab.txt    # vérifie la ligne PROJECT=... (doit pointer vers ton dossier)
```

Le `crontab.txt` du dépôt utilise `python3` système. Sur le VPS, on veut
l'environnement `.venv`. Remplace la ligne `PY=...` par :

```
PY=/root/observatoire-business-sabaudo/.venv/bin/python
```

*(adapte `/root/...` au chemin réel affiché par la commande `pwd`)*

Puis active :

```bash
crontab crontab.txt
crontab -l           # vérifie que les 3 lignes sont bien enregistrées
```

C'est fini : l'observatoire tourne désormais tout seul. Chaque vendredi soir,
une synthèse en **brouillon** est déposée dans le Drive pour ta validation.

---

## Aide-mémoire dépannage

| Souci | Que faire |
|-------|-----------|
| « command not found: python3 » | Refaire l'étape A3. |
| L'heure des tâches est décalée | Refaire A2 (`timedatectl set-timezone Europe/Paris`). |
| « invalid_grant » dans les logs | Les jetons ont expiré : refais Partie B + C. |
| Rien ne se déclenche | `crontab -l` pour vérifier ; consulter `logs/cron_*.log`. |
| Voir ce qui s'est passé | `tail -n 50 logs/synthesize_*.log` |

> Besoin d'aide en direct sur une étape ? Donne-moi le message exact affiché
> dans le terminal, je te débloque.

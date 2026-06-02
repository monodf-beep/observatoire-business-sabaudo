# Déployer sur ton VPS Hostinger (pas-à-pas, non technique)

Ton VPS est parfait : il est allumé en permanence, donc les collectes et la
synthèse se déclenchent toutes seules aux bonnes heures. Suis les étapes dans
l'ordre. Tu n'as **rien à coder**, juste à copier-coller.

> 🧩 Le seul point délicat : l'autorisation Google a besoin d'un navigateur
> **une seule fois**. Un VPS n'en a pas → on autorise sur **ton ordinateur**
> (Partie B), puis on copie les jetons sur le VPS (Partie C). C'est tout.

---

## Vue d'ensemble

```
A. Préparer le VPS        (terminal Hostinger — copier/coller)
B. Autoriser Google       (UNE fois, sur ton ordinateur, avec navigateur)
C. Copier les jetons      (de ton ordinateur vers le VPS)
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

## Partie B — Autoriser Google (sur TON ordinateur, une seule fois)

Cette étape ouvre une page Google pour valider l'accès. Elle se fait sur ta
machine (qui a un navigateur), pas sur le VPS.

> 💡 Si installer Python sur ton ordinateur te bloque, dis-le moi : je t'aide,
> ou on commence directement en faisant tourner l'outil sur ton ordinateur le
> temps de produire la première synthèse.

Sur ton ordinateur, dans le dossier du projet :

```bash
bash install.sh                 # si pas déjà fait
# place ton credentials.json dans config/  puis :
source .venv/bin/activate       # (Windows : .venv\Scripts\activate)
python scripts/authorize.py
```

Une page Google s'ouvre **deux fois** (Gmail puis Drive). À chaque fois :
choisis `franck.monod@culturasabauda.eu` → « Paramètres avancés » → « Accéder à
… (non sécurisé) » → coche et **Continuer**.

À la fin, deux fichiers sont créés dans `config/` :
`token.json` et `token_drive.json`.

---

## Partie C — Copier les jetons vers le VPS

Sur le VPS, recrée les deux fichiers avec `nano` (même méthode qu'en A7) :

```bash
nano config/token.json          # colle le contenu, Ctrl+O, Entrée, Ctrl+X
nano config/token_drive.json    # idem
```

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

Active la planification (lundi 7h, tous les jours 8h, vendredi 18h) :

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

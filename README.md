# Observatoire Économique Espace Sabaudo — Sprint 1

Outil de veille économique du territoire sabaudo (**Savoie, Piémont, Vallée d'Aoste, Nice**),
porté par [Cultura Sabauda](https://culturasabauda.eu).

Le Sprint 1 met en place trois routines automatisées : collecte d'emails de veille,
collecte de flux RSS, et synthèse hebdomadaire assistée par l'API Anthropic.
Aucune base de données : tout est stocké en fichiers **JSON** (veille brute) et
**Markdown** (synthèses), avec dépôt optionnel sur **Google Drive**.

## Architecture

```
observatoire-business-sabaudo/
├── config/
│   ├── credentials.json        # OAuth2 Gmail/Drive (À FOURNIR — non versionné)
│   ├── whitelist_gmail.txt     # expéditeurs surveillés (motif;territoire)
│   └── rss_feeds.txt           # flux RSS (url;territoire)
├── scripts/
│   ├── gmail_collect.py        # Script 1 — collecte Gmail   (cron lundi 7h)
│   ├── rss_collect.py          # Script 2 — collecte RSS     (cron quotidien 8h)
│   ├── synthesize.py           # Script 3 — synthèse hebdo   (cron vendredi 15h)
│   └── build_dashboard.py      # Tableau de bord visuel      (cron vendredi 15h15)
├── utils/
│   ├── drive_upload.py         # upload vers Google Drive
│   ├── logger.py               # logs horodatés
│   └── textutils.py            # nettoyage HTML -> texte
├── 01_Veille_brute/            # sorties JSON  (AAAA-MM-[territoire]/, non versionné)
├── 02_Veille_traitee/          # synthèses Markdown            (non versionné)
├── logs/                       # journaux horodatés            (non versionné)
├── .env                        # ANTHROPIC_API_KEY + DRIVE_FOLDER_ID (non versionné)
├── crontab.txt                 # configuration scheduler
└── requirements.txt
```

## Guides

- 🔑 **[docs/SETUP_GOOGLE_OAUTH.md](docs/SETUP_GOOGLE_OAUTH.md)** — donner les droits Gmail + Drive (pas-à-pas, non technique).
- 🚀 **[docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md)** — où faire tourner l'outil et comment l'installer.
- 🟣 **[docs/DEPLOIEMENT_HOSTINGER.md](docs/DEPLOIEMENT_HOSTINGER.md)** — déploiement clé en main sur un VPS Hostinger.

## Installation

```bash
bash install.sh                 # crée .venv, installe les dépendances, prépare .env
# puis : éditer .env (ANTHROPIC_API_KEY) et déposer config/credentials.json
```

Installation manuelle équivalente :

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
cp .env.example .env            # puis renseigner ANTHROPIC_API_KEY
```

Déposer le fichier OAuth2 Google dans `config/credentials.json`
(Google Cloud Console → API Gmail + Drive activées → identifiants OAuth « Application de bureau »).
Au premier lancement, une fenêtre d'autorisation OAuth s'ouvre et un jeton
(`config/token.json`) est créé pour les exécutions suivantes.

## Configuration

| Fichier | Rôle |
|---------|------|
| `config/whitelist_gmail.txt` | Expéditeurs à surveiller — `motif;territoire` (motif = email **ou** domaine) |
| `config/rss_feeds.txt`       | Flux RSS — `url;territoire` |
| `.env`                       | `ANTHROPIC_API_KEY`, `GMAIL_CREDENTIALS_PATH`, `DRIVE_FOLDER_ID` |

Territoires reconnus : `Savoie`, `Piemonte`, `Vallee-Aoste`, `Nice`, `Alcotra`.

## Utilisation

```bash
python scripts/gmail_collect.py            # collecte les emails récents de la whitelist
python scripts/rss_collect.py              # collecte les flux RSS
python scripts/synthesize.py               # synthèse de la semaine ISO courante
python scripts/synthesize.py --upload --brevo           # + upload Drive + brouillon Brevo
python scripts/push_brevo.py --check       # liste les expéditeurs et listes Brevo
python scripts/push_brevo.py --week 2026-W24            # brouillon Brevo d'une semaine
python utils/drive_upload.py fichier.md    # upload manuel vers Drive
```

### Sorties

- **Veille brute** : un JSON par élément dans `01_Veille_brute/AAAA-MM-[territoire]/`
  (déduplication par message-id pour Gmail, par URL pour RSS).
- **Synthèse** : `02_Veille_traitee/Syntheses_hebdomadaires/AAAA-WNN.md`.
  ⚠ **Aucun envoi automatique** — la synthèse est un brouillon à valider avant publication.
- **Brevo** (option `--brevo`) : la section newsletter de la synthèse est convertie
  en HTML et déposée comme **campagne en BROUILLON** dans Brevo (jamais envoyée).
  Configurer `BREVO_*` dans `.env` (voir `.env.example`) ; `push_brevo.py --check`
  affiche les expéditeurs et listes pour renseigner `BREVO_SENDER_EMAIL`/`BREVO_LIST_ID`.

## Planification (cron)

```bash
crontab crontab.txt     # après avoir adapté les chemins PROJECT et PY
```

- Collecte Gmail : **lundi 7h**
- Collecte RSS : **tous les jours 8h**
- Synthèse hebdomadaire : **vendredi 15h**

## Notes

- Le modèle de synthèse est `claude-sonnet-4-6` (surchargé via `ANTHROPIC_MODEL`).
- Tous les secrets (`.env`, `credentials.json`, `token*.json`) et les données
  collectées sont exclus du dépôt (voir `.gitignore`).
- Chaque routine écrit un journal horodaté dans `logs/`.
```

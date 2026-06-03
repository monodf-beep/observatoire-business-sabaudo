# Guide de continuité & portabilité — Observatoire Business Sabaudo

> Comment l'outil fonctionne, comment le faire tourner, le modifier, le sauvegarder
> et le **reprendre sans dépendre de Claude ni de personne en particulier**.
> Cultura Sabauda · contact : franck.monod@culturasabauda.eu

---

## 0. L'essentiel en 1 minute

- L'observatoire est un **ensemble de scripts Python** qui tournent **tout seuls**
  sur un serveur (VPS Hostinger), planifiés par `cron`.
- Il **collecte** (newsletters Gmail + flux RSS), **synthétise** une fois par
  semaine via l'**API Anthropic (Claude)**, et **dépose un brouillon de newsletter
  dans Brevo** + une synthèse dans Google Drive. **Rien n'est envoyé sans toi.**
- **Ça ne dépend pas de l'assistant Claude Code** (celui qui a écrit le code).
  Une fois installé, ça tourne sans lui. La seule brique « IA » est l'appel à
  l'**API Anthropic** lors de la synthèse — et elle est remplaçable (voir §8).
- **Tout le code est sur GitHub** (source de vérité). Les **secrets** (clés, mots
  de passe) sont **hors GitHub** : il faut en garder une **sauvegarde sécurisée**
  (voir §7 — c'est LE point critique de portabilité).

---

## 1. Où vit le projet (les 3 lieux)

| Lieu | Rôle | Repère |
|------|------|--------|
| **GitHub** | Le **code** (référence, historique, versions) | dépôt `monodf-beep/observatoire-business-sabaudo` |
| **VPS Hostinger** | L'**exécution** (les scripts tournent ici, en continu) | `152.239.112.112`, dossier `~/observatoire-business-sabaudo` |
| **Google Drive** | Les **livrables** (synthèses, sources, docs) | dossier « Observatoire économique Sabaudo » |

---

## 2. Les briques techniques

```
observatoire-business-sabaudo/
├── scripts/
│   ├── gmail_collect.py     # collecte les newsletters (lundi 7h)
│   ├── rss_collect.py       # collecte les flux RSS (tous les jours 8h)
│   ├── synthesize.py        # synthèse + brouillon Brevo (vendredi 18h)
│   ├── push_brevo.py        # crée le brouillon Brevo (appelé par synthesize)
│   └── demo_newsletter.py   # maquette de démonstration (manuel)
├── utils/
│   ├── google_auth.py       # connexion Google (OAuth2), mode --manual pour VPS
│   ├── drive_upload.py      # dépôt de fichiers sur Drive
│   ├── brevo.py             # appel API Brevo (création de brouillon)
│   ├── newsletter_variants.py # gabarit HTML « magazine » de la newsletter
│   ├── newsletter_template.py # gabarit HTML simple (secours)
│   ├── markdown_html.py     # conversion Markdown -> HTML
│   ├── sources.py           # domaine/source + règle « presse = radar »
│   ├── textutils.py         # nettoyage HTML -> texte
│   └── logger.py            # journaux horodatés
├── config/                  # LA configuration éditable (voir §5)
├── 01_Veille_brute/         # données collectées (JSON) — non versionné
├── 02_Veille_traitee/       # synthèses (.md + .json) — non versionné
├── logs/                    # journaux — non versionné
├── .env                     # SECRETS (clés API…) — non versionné (voir §7)
├── requirements.txt         # dépendances Python
├── install.sh               # installation automatique
└── crontab.txt              # planification (cron)
```

---

## 3. Le cycle hebdomadaire (automatique)

| Quand | Script | Ce qui se passe |
|-------|--------|-----------------|
| Tous les jours **8h** | `rss_collect.py` | collecte les flux RSS (5 territoires) |
| Lundi **7h** | `gmail_collect.py` | collecte les newsletters reçues |
| Vendredi **18h** | `synthesize.py --upload --brevo` | synthèse de la semaine → Drive + **brouillon Brevo** |

Entre-temps, la matière s'accumule en silence. Le vendredi, l'IA sélectionne et
éditorialise, puis dépose un **brouillon** (jamais d'envoi auto).

---

## 4. Comment l'utiliser au quotidien

Sur le VPS, dans `~/observatoire-business-sabaudo`, après `source .venv/bin/activate` :

```bash
python scripts/gmail_collect.py            # collecte Gmail (ponctuel)
python scripts/rss_collect.py              # collecte RSS (ponctuel)
python scripts/synthesize.py --upload --brevo          # synthèse semaine courante
python scripts/synthesize.py --week 2026-W24 --upload --brevo   # semaine précise
python scripts/push_brevo.py --week 2026-W24           # (re)créer le brouillon Brevo
python scripts/push_brevo.py --check                   # voir expéditeurs/listes Brevo
python scripts/demo_newsletter.py --brevo              # brouillon de démonstration
```

**Ton rôle (~10 min/semaine)** : ouvrir le brouillon dans Brevo, relire, ajuster,
envoyer quand tu veux.

---

## 5. La configuration (les fichiers à éditer)

Tout se règle dans `config/` — **édite, puis `git commit` + `git push`, puis
`git pull` sur le VPS** (ou édite directement sur le VPS).

| Fichier | À quoi ça sert |
|---------|----------------|
| `config/whitelist_gmail.txt` | Expéditeurs surveillés. Format `motif;territoire` (motif = email **ou** domaine). |
| `config/rss_feeds.txt` | Flux RSS. Format `url;territoire`. Inclut les recherches **Google News** par territoire. |
| `config/press_domains.txt` | Domaines de **presse** = utilisés comme **radar** uniquement : jamais crédités/liés dans la newsletter (pas de pub aux journaux). L'info est attribuée à l'**acteur** primaire. |

Territoires reconnus : `Savoie`, `Piemonte`, `Vallee-Aoste`, `Nice`, `Alcotra`
(sans accents ni espaces).

**Exemples de modifications courantes :**
- *Ajouter une source RSS* → une ligne `url;territoire` dans `rss_feeds.txt`.
- *Ajouter un expéditeur* → une ligne `email;territoire` dans `whitelist_gmail.txt`.
- *Ne plus créditer un journal* → ajouter son domaine dans `press_domains.txt`.
- *Changer un horaire* → éditer `crontab.txt` puis `crontab crontab.txt`.
- *Changer le design de la newsletter* → `utils/newsletter_variants.py`.

---

## 6. Les services externes utilisés

| Service | Pour quoi | Compte / accès |
|---------|-----------|----------------|
| **Google Cloud** (API Gmail + Drive) | lire les newsletters, déposer sur Drive | projet Google Cloud + identifiants OAuth « Application de bureau » |
| **API Anthropic** (Claude) | rédiger la synthèse hebdo | console.anthropic.com → clé API |
| **Brevo** | héberger le brouillon de newsletter | app.brevo.com → clé API + expéditeur validé + liste |
| **Hostinger** | le serveur (VPS) | panel Hostinger |
| **GitHub** | héberger le code | github.com |

---

## 7. Les SECRETS et leur sauvegarde ⚠️ (le point critique)

Ces éléments **ne sont pas sur GitHub** (c'est volontaire — ce sont des secrets).
**Garde-en une sauvegarde sécurisée** (gestionnaire de mots de passe, coffre-fort
numérique). Sans eux, impossible de redéployer ailleurs.

À sauvegarder :
1. **Le fichier `.env`** (sur le VPS) — contient toutes les clés. Variables clés :
   - `ANTHROPIC_API_KEY` — clé API Anthropic
   - `GMAIL_CREDENTIALS_PATH` — chemin du fichier d'identifiants Google
   - `DRIVE_FOLDER_ID` — id du dossier Drive racine
   - `DRIVE_VEILLE_BRUTE_SUBFOLDER`, `DRIVE_VEILLE_TRAITEE_SUBFOLDER`
   - `BREVO_API_KEY`, `BREVO_SENDER_NAME`, `BREVO_SENDER_EMAIL`, `BREVO_LIST_ID`
   - `BREVO_LOGO_URL`, `BREVO_PICTO_URL`
   - (optionnels) `ANTHROPIC_MODEL`, `GMAIL_LOOKBACK_DAYS`, `RSS_TIMEOUT`
2. **`config/credentials.json`** — identifiants OAuth Google (téléchargés depuis
   Google Cloud Console).
3. **`config/token.json`** — jeton d'accès Google (régénérable via OAuth, voir §9).

> 💡 Conseil : copie le contenu de `.env` et `credentials.json` dans une note
> sécurisée **dès aujourd'hui**. C'est la seule chose qui ne se récupère pas
> automatiquement depuis GitHub.

---

## 8. Dépendance à « Claude » : ce qui dépend / ne dépend pas

- **L'assistant Claude Code** (celui qui a écrit ce projet) **n'est PAS nécessaire**
  pour faire tourner l'outil. S'il disparaît, l'observatoire continue. Pour le
  faire *évoluer*, n'importe quel développeur Python peut reprendre le code (il est
  documenté, et ce guide explique tout).
- **L'API Anthropic (modèle Claude)** est utilisée **uniquement à l'étape de
  synthèse** (`synthesize.py`). Si tu veux changer de modèle : variable
  `ANTHROPIC_MODEL` dans `.env`. Si Anthropic devenait indisponible, **seule la
  synthèse** s'arrêterait (la collecte continue) ; il faudrait alors adapter la
  fonction `call_anthropic()` dans `scripts/synthesize.py` pour un autre
  fournisseur d'IA (OpenAI, Mistral…). Tout le reste (collecte, Brevo, mise en
  page) **ne contient aucune IA**.

---

## 9. Reprise sur sinistre (réinstaller de zéro)

Si le VPS est perdu, ou pour déménager sur un autre serveur :

```bash
# 1. Récupérer le code
git clone https://github.com/monodf-beep/observatoire-business-sabaudo.git
cd observatoire-business-sabaudo
git checkout claude/pensive-einstein-S5Fds   # (ou main une fois fusionné)

# 2. Installer
bash install.sh                  # crée .venv, installe les dépendances

# 3. Restaurer les secrets (depuis ta sauvegarde — §7)
#    - recréer le fichier .env
#    - déposer config/credentials.json

# 4. Autoriser Google (sur un serveur sans navigateur)
source .venv/bin/activate
python scripts/authorize.py --manual    # affiche une URL, tu colles le code retour
#    -> crée config/token.json

# 5. Planifier
crontab crontab.txt              # après avoir adapté PROJECT et PY dans le fichier

# 6. Tester
python scripts/rss_collect.py
python scripts/synthesize.py --upload --brevo
```

---

## 10. Sauvegarde des données

- **Le code** : sur GitHub (toujours récupérable).
- **Les synthèses** : déposées sur **Google Drive** (`02_Veille_traitee`) → sauvegardées de fait.
- **La veille brute** (`01_Veille_brute`) : seulement sur le VPS. Non critique
  (matière première), mais sauvegardable par simple copie du dossier si souhaité.

---

## 11. Coûts (ordres de grandeur)

- **API Anthropic** : quelques centimes par synthèse hebdomadaire (selon le volume
  collecté). À surveiller dans la console Anthropic.
- **Brevo** : l'offre gratuite suffit pour des brouillons et de petits envois ; un
  plan payant si l'audience grandit.
- **VPS Hostinger** : abonnement existant.
- **Google / GitHub** : gratuit pour cet usage.

---

## 12. En cas de problème (dépannage)

- **Un flux RSS en erreur** → normal, le script l'ignore et continue. Vérifier
  l'URL dans `config/rss_feeds.txt`.
- **Pas de brouillon Brevo** → vérifier `.env` (clés Brevo) et que la semaine
  contient de la matière (`python scripts/push_brevo.py --check`).
- **Erreur Google 401 / token** → relancer `python scripts/authorize.py --manual`.
- **Erreur Brevo « unrecognised IP »** → autoriser l'IP du VPS dans Brevo
  (Paramètres → Sécurité → Adresses IP autorisées).
- **Les journaux** sont dans `logs/` (un fichier par script et par jour).

---

*Ce document est versionné dans le dépôt (`docs/CONTINUITE_ET_PORTABILITE.md`) et
copié dans le Drive. En cas de doute, le **dépôt GitHub fait foi**.*

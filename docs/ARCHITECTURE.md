# Architecture — Observatoire « Business Sabaudo »

Veille économique automatisée sur l'espace sabaudo (Savoie, Piémont, Vallée d'Aoste,
Nice/Alpes-Maritimes, périmètre transfrontalier Alcotra). Deux produits :

- **La page publique « toute la veille »** — liste exhaustive, triée, par territoire
  (`culturasabauda.eu/observatoire`).
- **La newsletter** — sélection éditorialisée, déposée en **brouillon** Brevo (jamais
  envoyée automatiquement) + archivée sur Google Drive.

---

## 1. Vue d'ensemble

```
   SOURCES                COLLECTE (VPS)            TRI & RÉDACTION             SORTIES
┌───────────┐
│  Gmail    │──┐    ┌─ gmail_collect.py ─┐
│ (newsl.)  │  │    │  extrait articles  │
└───────────┘  │    │  + résout traceurs │
┌───────────┐  ├──► ├─ rss_collect.py ───┼─► 01_Veille_brute/ ─► triage.py ──┐
│ Flux RSS  │  │    │  (presse+officiel) │    (JSON/sujet,       (Haiku :     │
│           │  │    ├─ html_scrape.py ───┤     sur le VPS)       garder/jeter │
└───────────┘  │    │  (sites sans RSS)  │                       + titre net) │
┌───────────┐  │    └────────────────────┘                                   │
│ Sites web │──┘                                                             ▼
└───────────┘                                   ┌────────────────────────────────────┐
                                                │ build_dashboard.py                  │─► Page publique
                                                │  page veille + encart « synthèse »   │   (veille)
                                                └────────────────────────────────────┘
                                                ┌────────────────────────────────────┐
                                                │ synthesize.py (newsletter)          │─► Brevo (BROUILLON)
                                                │  Opus : rédige une + brèves          │─► Drive (archive + GDoc)
                                                │  Sonnet : lien officiel + og:image   │─► rebâtit la page veille
                                                │  Haiku vision : valide les photos    │
                                                │  Openverse : photos libres de droits │
                                                └────────────────────────────────────┘
```

---

## 2. Étapes du pipeline

| # | Script | Rôle | LLM | Cron |
|---|--------|------|-----|------|
| 1 | `scripts/gmail_collect.py` | Lit les newsletters Gmail, en extrait les **articles** (titre apparié au heading du corps), résout les liens traceurs ESP (cache disque) | — | Lundi 7h |
| 2 | `scripts/rss_collect.py` | Collecte les flux RSS (`config/rss_feeds.txt`) — presse régionale + sources officielles | — | Quotidien 8h |
| 3 | `scripts/html_scrape.py` | Scrape les sites sans RSS (`config/sources_a_scraper.txt`, type `html`) : titre + lien + image | — | Quotidien 8h15 |
| 4 | `scripts/triage.py` | **Juge** chaque sujet (pertinence économique pour le périmètre) et **réécrit un titre propre**. Mise en cache (`logs/triage_cache.json`) : chaque item jugé une seule fois | **Haiku 4.5** | Quotidien 8h30 |
| 5 | `scripts/build_dashboard.py` | Génère la **page publique** : board par territoire (newsletter > officiel > radar replié), encart « Synthèse de la semaine » | — (relit le cache de tri) | Mar/Jeu/Sam 9h |
| 6 | `scripts/synthesize.py` | Génère la **newsletter** : rédaction, photos, brouillon Brevo, archive Drive, puis rebâtit la page veille | Opus + Sonnet + Haiku vision | **Vendredi 15h** |

---

## 3. Les LLM (4, chacun à sa place)

| Rôle | Modèle | Fréquence | Pourquoi |
|------|--------|-----------|----------|
| **Rédaction éditoriale** (une, brèves, ton B2B) | **claude-opus-4-8** | 1 appel / semaine | Le plus capable — cœur qualitatif |
| **Tri pertinence + nettoyage des titres** | **claude-haiku-4-5** | ~400 sujets / sem., **caché** | Volume élevé, tâche simple → le moins cher |
| **Recherche lien officiel + og:image** | **claude-sonnet-4-6** | par brève radar (opt. `OFFICIAL_LINK_SEARCH`) | Recherche web fiable |
| **Validation des photos** (vision) | **claude-haiku-4-5** | par photo candidate, **caché** | Jugement visuel binaire |

Surcharge possible par `.env` : `ANTHROPIC_MODEL`, `TRIAGE_MODEL`, `OFFICIAL_SEARCH_MODEL`,
`IMAGE_JUDGE_MODEL`.

La **recherche de photos** (Openverse / Creative Commons) n'est **pas** un LLM : c'est une
API d'images libres de droits. Seul le *jugement* de pertinence est confié au LLM vision.

---

## 4. Choix des images (ordre de priorité)

1. **Photo de source** (RSS / email) si c'est une vraie photo — les **logos** sont écartés
   (`is_logo_image`, motif d'URL).
2. **og:image de l'article officiel** trouvé par la recherche web (Sonnet).
3. **Photo web libre de droits** (Openverse/CC) dérivée du titre + acteur, **validée par
   le LLM vision**.
4. **Carte de territoire** (visuel de marque) en dernier recours.

Réglages `.env` : `NEWSLETTER_SOURCE_IMAGES`, `NEWSLETTER_WEB_IMAGES`, `NEWSLETTER_IMAGE_JUDGE`.

---

## 5. Le VPS

`152.239.112.112` — projet sous `/root/observatoire-business-sabaudo`.

- **Cron** : exécute les 6 scripts ci-dessus (voir `crontab.txt`).
- **Page admin** : serveur Flask (`scripts/admin_server.py`), service systemd
  `observatoire-admin` sur `127.0.0.1:8099`, exposé en **HTTPS via Traefik** sous `/admin`
  (`deploy/traefik-observatoire-admin.yml`).
- **Stockage local** : veille brute (`01_Veille_brute/`), caches (tri, URLs résolues,
  recherche/jugement d'images), journaux (`logs/`).
- **Publication** : copie `index.html` dans le dossier web servi (`DASHBOARD_FTP_PROTO=local`).
- **N'envoie PAS la newsletter** : crée un **brouillon** Brevo via API ; l'envoi est **manuel**.

---

## 6. Page admin (`/admin`)

- **Pipeline visuel** (façon n8n) : l'état de chaque étape (ok / erreur / en cours), dérivé
  des journaux, jusqu'aux sorties (Page publique, Brevo, Drive).
- **2 boutons** (le tri IA est lancé automatiquement avant chaque sortie) :
  - **Générer la newsletter** → tri + rédaction Opus + photos + **brouillon Brevo** +
    **Drive** + republie la page veille.
  - **Rafraîchir la page veille** → tri + republie la page (sans toucher Brevo).
- Protégée par authentification HTTP Basic (`ADMIN_USER` / `ADMIN_PASS`), derrière HTTPS.

---

## 7. Google Drive — ce qui est mis à jour, et quand

À chaque **génération de newsletter** (`synthesize.py --upload` : bouton admin **ou** cron
du vendredi), dépose dans **`02_Veille_traitee/`** :

1. **L'archive Markdown** de la synthèse,
2. **Un Google Doc natif** mis en forme (« Business Sabaudo — Semaine du … »),
3. **Le `dashboard.html`** de la veille.

À noter :
- Le **« Rafraîchir la veille »** seul (et les builds Mar/Jeu/Sam) **ne touchent pas** au
  Drive — ils republient seulement la page publique.
- La **veille brute** (`01_Veille_brute/`) reste **sur le VPS**, pas sur le Drive.

---

## 8. Configuration (fichiers `config/`)

| Fichier | Contenu |
|---------|---------|
| `whitelist_gmail.txt` | Expéditeurs Gmail surveillés (motif ; territoire) |
| `newsletters.txt` | Registre des newsletters suivies (affiché au tableau de bord) |
| `rss_feeds.txt` | Flux RSS à collecter (url ; territoire) |
| `sources_a_scraper.txt` | Sources sans RSS (scraping HTML) |
| `press_domains.txt` | Domaines de **presse** (radar : gardés mais non liés) |
| `blocked_image_domains.txt` | CDN d'images à bannir (presse / agrégateurs) |
| `offtopic_keywords.txt` / `economic_keywords.txt` | Pré-filtre mots-clés (hors-sujet vs éco) |
| `perimeter_keywords.txt` / `broad_sources.txt` | Filtre géographique des sources larges (ex. EU-Startups) |
| `official_links.txt` | Annuaire des domaines officiels par acteur |
| `territory_images.txt` | Cartes de marque par territoire (repli image) |

---

## 9. Garde-fous

- **Tri & jugements en cache** : chaque sujet/photo n'est jugé qu'une fois → coût maîtrisé.
- **Fail-open** : sans clé API ou en cas d'erreur, le tri/jugement garde tout → la veille
  n'est jamais cassée.
- **Pré-filtres mots-clés** gratuits avant le LLM → moins d'appels.
- **Aucun envoi automatique** : la newsletter reste un brouillon validé manuellement.
- **Tests de régression** : `python tests/test_filters.py` (filtres, extraction, images, dates…).

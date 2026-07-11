# Plan d'actions — Écosystème Cultura Sabauda

Deux produits qui partagent la même plomberie (collecte → tri LLM → sortie
newsletter/page/CMS), mais des domaines distincts :

- **Observatoire Business Sabaudo** (ce repo) — veille économique → newsletter Brevo + page publique.
- **Agenda Cultura Sabauda** (repo à créer) — agrégateur d'événements culturels → WordPress (draft) + backoffice de validation.

Stratégie : **2 repos séparés**. Extraire une lib commune **`cultura-core`** plus tard,
quand les deux tournent et que les utils ne bougent plus (règle de trois). Voir §3.

---

## 1. Action plan — démarrer l'Agenda (Sprint 1)

**Séquence :** d'abord Claude Chrome (valider les flux + Application Password WP),
ensuite Claude Code (bootstrap du repo).

### 1a. Prompt Claude Chrome (prépa)

> J'ai besoin de vérifier des choses dans le navigateur pour un backoffice d'agenda culturel (sources RSS + WordPress). Fais ces 2 tâches et donne-moi un compte-rendu clair :
>
> **Tâche 1 — Valider les flux RSS.** Pour chacune de ces 5 URLs, ouvre-la et dis-moi : (a) est-ce un vrai flux RSS/Atom valide ? (b) combien d'entrées récentes ? (c) chaque entrée a-t-elle une **date d'événement** et une **image** ? Si l'URL est morte (404, pas un flux), **cherche la vraie URL du flux** sur le site de la source (« rss », « flux », « /feed », l'icône RSS, l'agenda) et donne-la-moi.
> - https://www.salonelibro.it/it/feed.xml (Piemonte — Salone del Libro Torino)
> - https://www.turismotorino.org/feed (Piemonte — Turismo Torino)
> - https://patrimoines.savoie.fr/agenda/rss (Savoie)
> - https://regione.vda.it/rss/eventi.xml (Vallée d'Aoste)
> - https://www.nicecotedazur.org/agenda/rss (Nice)
> Conclus par un tableau : source · URL finale qui marche · OK/à remplacer · a une date · a une image.
>
> **Tâche 2 — Application Password WordPress.** Connecte-toi au WordPress de culturasabauda.eu, va dans Utilisateurs → mon profil → Application Passwords, crée un mot de passe applicatif « agenda-backoffice », et donne-le-moi. Vérifie que l'API REST répond : ouvre https://culturasabauda.eu/wp-json/wp/v2/posts et confirme du JSON (pas 401/404).
>
> Important : ne publie rien, ne modifie aucun réglage à part créer l'Application Password.

### 1b. Prompt Claude Code (bootstrap)

> Crée le repo **agenda-backoffice** d'après le brief Sprint 1 (collé après). Suis le brief à la lettre SAUF ces 4 corrections critiques :
>
> **1. Robustesse API dans `evaluator.py` (CRITIQUE).** Ne JAMAIS rejeter un événement à cause d'une erreur API. Trois cas :
> - LLM OK → bifurcation (≥7 `evaluated`, 4-6 `published_sub`, <4 `rejected`).
> - LLM échoue (réseau, crédit/limite d'usage, JSON invalide) → **laisse `pending`** (réessai au prochain run), n'écris PAS `rejected`.
> - Si l'erreur évoque crédit/limite (« credit », « usage limit », « regain access », « rate limit ») → **`break`** la boucle + pose une alerte (point 2).
>
> **2. Copie `utils/usage.py`** depuis l'Observatoire (monodf-beep/observatoire-business-sabaudo, branche claude/pensive-einstein-S5Fds) et instrumente chaque `messages.create` avec `usage.record_message(model, message, label="évaluation")` ; en erreur `usage.note_api_error(exc)`. Ajoute au backoffice un encart « Coûts API » (`usage.summarize()`) + bannière rouge si `usage.get_alert()`.
>
> **3. Image à la une WordPress.** `_thumbnail_url` en meta NE définit PAS l'image à la une via REST. Fais : télécharge l'image → POST `/wp-json/wp/v2/media` → récupère `media_id` → `"featured_media": media_id` dans le post. Échec upload → post sans vignette (jamais bloquant).
>
> **4. Fichiers copiés = source unique.** `utils/logger.py`, `utils/sources.py`, `utils/usage.py`, `config/blocked_image_domains.txt`, `config/territory_images.txt` restent IDENTIQUES à l'original ; ajoute en tête `# SYNCED FROM observatoire-business-sabaudo — ne pas diverger (cultura-core)`.
>
> En plus : README (architecture + statuts + plan cultura-core), tests (`tests/test_eval.py` : bifurcation des scores + erreur API laisse `pending`). Branche, commits par étape, pas de `.env` poussé.
>
> Brief complet : [COLLER LE BRIEF]

---

## 2. Ce que l'OBSERVATOIRE peut emprunter à l'Agenda (analyse inverse)

Le design de l'Agenda a de bonnes idées que l'Observatoire n'a pas. Par priorité :

### 🥇 Score 0-10 + justification (au lieu de garder/jeter binaire) — PRIORITÉ HAUTE
- **Agenda** : chaque item reçoit `score` (0-10), `categorie`, `justification` (1 phrase), avec bifurcation 3 niveaux.
- **Observatoire aujourd'hui** : triage binaire keep/drop.
- **Gain** : (1) **classement** — la une = meilleur score, le radar = seuil bas ; (2) **transparence** — afficher « pourquoi c'est pertinent » (justification) ; (3) **seuils réglables** — newsletter = top-N, page = ≥ seuil.
- **Effort** : faible-moyen (adapter le prompt de `triage.py` + stocker score/justification dans le cache). **Rentable vite.**

### 🥈 SQLite comme socle de données (au lieu des JSON éparpillés) — PRIORITÉ HAUTE (mais refactor)
- **Agenda** : table `events_raw`, `url_source UNIQUE`, champ `statut`.
- **Observatoire** : `01_Veille_brute/*.json` + 3-4 caches JSON, dédup au build.
- **Gain** : dédup natif (UNIQUE), requêtes, statut par item, atomicité, fin de la prolifération de fichiers, historique interrogeable.
- **Effort** : moyen (migration du stockage). **À faire au moment de l'extraction `cultura-core`.**

### 🥉 Statut de cycle de vie par item — PRIORITÉ MOYENNE
- `pending → evaluated → in_newsletter / shown / rejected`. Va de pair avec SQLite. Permet « déjà passé en newsletter », « rejeté par la rédaction ».

### Validation éditoriale par item (backoffice) — PRIORITÉ MOYENNE (choix produit)
- **Agenda** : Franck valide chaque item (Publier / Rejeter) avant la homepage.
- **Observatoire** : tout est automatique ; pas de curation par item.
- **Gain** : contrôle éditorial réel (cf. le débat « validée par la rédaction »). Un écran « à valider » où tu coches les brèves qui montent en une/newsletter.
- **Effort** : moyen (écran admin + statut). À faire seulement si tu veux curer plutôt que rester full-auto.

### Rubrique de scoring transparente dans le prompt — PRIORITÉ MOYENNE
- La grille de l'Agenda (+3 savoir rare / +3 regard original / +3 local→universel / +1 bilingue) est excellente. L'Observatoire gagnerait une grille éco explicite (impact, proximité, nouveauté, source primaire) → scores cohérents + justification exploitable.

### (Optionnel) Publier dans WordPress
- Si culturasabauda.eu est WordPress : publier la veille/newsletter en **draft WP** (comme l'Agenda) plutôt qu'un `index.html` statique → cohérence + SEO. À discuter.

### ⛔ À NE PAS emprunter
- Le **schéma « événement »** structuré (date/lieu/billetterie) : inutile pour la veille éco.
- Le **bug de rejet sur erreur API** de l'Agenda : l'Observatoire l'évite déjà (fail-open) — ne pas régresser.

---

## 3. cultura-core — ce qui converge

Les emprunts ci-dessus (SQLite, score+justification, statut, backoffice de validation)
sont précisément les briques que les DEUX projets partageraient. Ils renforcent
l'argument d'extraire, plus tard, une lib commune `cultura-core` :

```
cultura-core (source unique)
 ├── logger, sources (images/url/domaine), usage (coûts + alerte crédit)
 ├── collecte RSS générique
 ├── "juge LLM avec cache" (harnais : batch, cache, fail-open, JSON)  ← + score/justification
 ├── stockage SQLite (dédup UNIQUE, statuts)
 └── client Brevo / publisher WordPress
        ▲                     ▲                      ▲
 observatoire-éco       agenda-events        3e produit (mince couche métier)
```

**Timing** : pas maintenant (utils encore mouvants). Après stabilisation des deux.

---

## 4. Prochaines actions

- [ ] **Observatoire** : reprise dès que le crédit API est régénéré (limite jusqu'au 01/07 00:00 UTC).
- [ ] **Observatoire — quick win** : passer le triage de binaire à **score 0-10 + justification**.
- [ ] **Agenda** : lancer prompt Chrome (§1a) puis prompt Claude Code (§1b).
- [ ] **Plus tard** : extraire `cultura-core` (SQLite + harnais LLM + usage + Brevo/WP).

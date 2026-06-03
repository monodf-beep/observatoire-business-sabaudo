# Observatoire Business Sabaudo — Feuille de route

> Document de cadrage — où on va, comment ça marche, ce qui reste à faire.
> Cultura Sabauda · culturasabauda.eu · contact : franck.monod@culturasabauda.eu
> Mis à jour le 2026-06-02.

---

## 1. À quoi sert l'observatoire

Un **assistant de veille économique automatique** sur le territoire sabaudo
historique : **Savoie, Piémont, Vallée d'Aoste, Nice / Alpes-Maritimes**, plus le
périmètre transfrontalier **Alcotra** France-Italie.

Il collecte tout seul l'actualité économique (newsletters + flux RSS), puis
rédige chaque semaine une **synthèse prête à relire**. Franck valide et publie.

---

## 2. Comment ça marche (le cycle hebdomadaire)

| Quand | Ce qui se passe automatiquement |
|-------|--------------------------------|
| **Tous les jours – 8h** | Collecte des flux RSS (sites, institutions, pépinières…) |
| **Lundi – 7h** | Collecte des newsletters reçues sur la boîte de veille |
| **Vendredi – 18h** | Rédaction de la synthèse de la semaine + dépôt dans le Drive |

Entre-temps, l'outil accumule la matière en silence. Tout tourne sur un serveur
allumé en permanence (VPS Hostinger) — aucune intervention nécessaire.

---

## 3. Ce que tu reçois

Chaque semaine, une synthèse structurée (format texte, dans le Drive) :

1. **5 signaux forts** — les actus marquantes, avec contexte, territoire et source.
2. **Le point par territoire** — Savoie, Piémont, Vallée d'Aoste, Nice, Alcotra.
3. **Un brouillon de newsletter « Business Sabaudo »** — objet, intro, brèves,
   signature, ton B2B, prêt à relire.

En plus, chaque vendredi, ce brouillon de newsletter est **déposé directement dans
Brevo en BROUILLON** (déjà mis en forme en HTML). Tu n'as plus qu'à l'ouvrir dans
Brevo, le relire/ajuster, et cliquer sur « Envoyer » quand tu le décides.

> ⚠️ L'outil **ne publie / n'envoie jamais tout seul**. Tu gardes la main : tu relis,
> tu ajustes, tu envoies où tu veux.

---

## 4. Où c'est rangé (ce dossier Drive)

```
📁 Observatoire économique Sabaudo
   ├── 📁 01_Veille_brute                  ← matière première archivée
   └── 📁 02_Veille_traitee
          └── 📁 Syntheses_hebdomadaires   ← les synthèses (une par semaine)
                 ├── 2026-W22 …
                 └── 2026-W23 …
```

Au quotidien, c'est **`02_Veille_traitee`** qui compte : les synthèses y arrivent.

---

## 5. Ton rôle (≈ 10 min / semaine)

1. Ouvrir la synthèse de la semaine.
2. La relire (signaux forts + territoires + newsletter).
3. Ajuster ce que tu veux.
4. Publier (newsletter, site, réseaux…).

---

## 6. État d'avancement

### ✅ Sprint 1 — le socle (en cours de finalisation)
- [x] Collecte automatique des flux RSS
- [x] Collecte automatique des newsletters (Gmail)
- [x] Synthèse hebdomadaire rédigée (5 signaux + territoires + newsletter)
- [x] Dépôt automatique dans le Drive
- [x] Brouillon de newsletter déposé automatiquement dans Brevo (jamais envoyé)
- [x] Déploiement sur le VPS + planification automatique
- [ ] Alimentation des sources réelles (newsletters + flux à surveiller)

### 🎯 Sprint 2 — Newsletter personnalisée (en cours)
- [x] Cadrage de la personnalisation (`docs/PERSONNALISATION.md`)
- [x] Rubrique éditoriale « Ponts & connexions » (dimension transfrontalière)
- [x] Outil de configuration Brevo (`scripts/brevo_setup.py` + guide) : attributs
  `LANGUE` / `TERRITOIRE` / `SECTEURS`, dossier et listes par langue
- [ ] Exécuter la configuration Brevo sur le VPS + renseigner les contacts
- [ ] Créer le formulaire d'inscription Brevo (langue + territoire + intérêts)
- [x] Étape 1 — variante de langue FR/IT (gabarit bilingue + traduction IA + un
  brouillon Brevo par langue) ; reste à brancher les listes FR/IT du `.env`
- [ ] Étape 2 — réordonnancement par territoire d'ancrage
- [ ] Étape 3 — centres d'intérêt (via page web, plus tard)

### 🔮 Pistes pour la suite (à décider ensemble, optionnel)
- **Lecture plus agréable** : synthèses en Google Doc plutôt qu'en fichier texte.
- **Envoi automatique** de la newsletter Brevo après validation.
- **Tableau de bord visuel** « Business Sabaudo » (page web : tendances, carte du
  territoire, évolution des signaux).
- **Statistiques** : nombre de signaux par territoire, dynamiques dans le temps.
- **Élargissement des sources** : presse économique, données publiques, réseaux.

---

## 7. Les briques techniques (pour mémoire)

- **Collecte** : deux routines Python (Gmail + RSS), archivage en fichiers JSON.
- **Synthèse** : appel à l'IA Claude (API Anthropic) sur la matière de la semaine.
- **Stockage** : Google Drive (pas de base de données — simplicité et robustesse).
- **Automatisation** : planificateur `cron` sur le VPS.
- **Code & documentation** : dépôt GitHub `observatoire-business-sabaudo`.

---

*Ce document évoluera au fil des sprints. Pour ajouter une source, changer un
horaire ou faire évoluer la synthèse : il suffit de le demander.*

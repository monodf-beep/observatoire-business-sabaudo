# Personnalisation de la newsletter « Business Sabaudo »

> Note de cadrage — comment rendre la newsletter pertinente pour chaque lecteur
> sans rédiger un email par personne, tout en gardant l'ADN transfrontalier de
> l'observatoire. Cultura Sabauda · franck.monod@culturasabauda.eu
> Mis à jour le 2026-06-03.

---

## 1. Le principe : personnaliser ≠ envoyer un mail par personne

Aucune newsletter sérieuse ne rédige un email individuel. La personnalisation
repose sur **deux briques** :

1. **Une base de contenu unique** (notre JSON hebdomadaire structuré : `une`,
   `signaux`, `articles`, chacun tagué par territoire) — déjà en place.
2. **Une variation du rendu** selon des **attributs du contact** (langue,
   territoire, secteur) stockés dans Brevo.

> 👉 On réutilise **une seule** matière éditoriale et on **fait varier sa mise en
> forme / son ordre**. C'est exactement ce que notre architecture permet déjà :
> le pipeline produit un JSON propre que l'on peut décliner.

---

## 2. La règle d'or : réordonner, jamais exclure

Le danger n°1 de la personnalisation, c'est la **bulle de filtre** : à force de
ne montrer au lecteur de Cuneo que du Cuneo, on détruit la valeur même de
l'observatoire — le **regard transfrontalier**.

> **Règle d'or** : la personnalisation **met en avant et réordonne**, elle ne
> **filtre pas** et n'**exclut jamais**. Le modèle est *« chez moi d'abord, mais
> relié à »*, pas *« seulement chez moi »*.

La priorité reste de **montrer tout l'espace sabaudo** (Vallée d'Aoste, Piémont,
Nice, Savoie) à chaque lecteur — c'est la mission. La personnalisation ne fait
que choisir **quel territoire ouvre** la lecture.

---

## 3. Les trois axes de personnalisation (du plus simple au plus coûteux)

| Axe | Attribut contact (Brevo) | Coût | Valeur | Quand |
|-----|--------------------------|------|--------|-------|
| **Langue** FR / IT | `LANGUE` | Faible | Élevée (incontournable) | Étape 1 |
| **Territoire d'ancrage** | `TERRITOIRE` | Moyen | Élevée | Étape 2 |
| **Centres d'intérêt / secteur** | `SECTEURS` | Élevé | Moyenne au début | Étape 3 |

- **Langue** : le seul axe qui *tranche* (deux versions distinctes). Voir aussi
  `BONNES_PRATIQUES_NEWSLETTER.md §8`.
- **Territoire** : sert à **l'ordre de lecture**, pas au tri. Les quatre
  territoires restent toujours présents.
- **Secteur** : le plus coûteux car il faut **taguer chaque brève par secteur**
  (deeptech, industrie, tourisme, agroalimentaire, finance, recherche…). À
  réserver pour plus tard, idéalement via la page web (voir §5, modèle C).

---

## 4. La structure éditoriale en 4 strates

Une seule strate est personnalisée ; les trois autres sont communes à tous —
c'est ce qui protège l'esprit transfrontalier.

1. **« À la une » / Signal de la semaine** — *commun à tous*. La plus forte
   actualité, choisie pour sa portée (souvent transfrontalière).
2. **« Chez vous »** — *seule strate réordonnée*. Le territoire d'ancrage du
   lecteur remonte en tête.
3. **« Dans l'espace sabaudo »** — les trois autres territoires, **toujours
   présents**.
4. **« Ponts & connexions »** — *commun à tous*. La rubrique qui matérialise la
   mission : une entreprise valdôtaine qui exporte en France, un projet
   Nice–Turin, un partenariat Savoie–Genève, une PME qui attaque le marché
   italien… Grenoble, Lyon, Genève, la Suisse, la France, l'international y ont
   droit de cité **dès qu'il existe un lien concret** avec le territoire.

> La rubrique « Ponts & connexions » ne demande **aucune** mécanique de ciblage :
> elle est **purement éditoriale** et répond directement au besoin de ne pas
> rendre l'espace sabaudo trop exclusif. **Elle est implémentée dès maintenant**
> (Étape 0), avant toute personnalisation technique.

---

## 5. Comment faire techniquement — trois modèles, ce que font les autres

| | Modèle | Principe | Avantages | Limites |
|-|--------|----------|-----------|---------|
| **A** | **N campagnes / N segments** | À partir d'**un** JSON, on génère 2 (langues) × 4 (territoires) variantes HTML et on dépose autant de **brouillons Brevo** ciblant autant de **segments**. | Simple, robuste, **stats par segment**, aucun besoin de page web. | Plusieurs brouillons à relire (mais le contenu reste le même). |
| **B** | **Contenu conditionnel** | **Une seule** campagne ; Brevo affiche/masque des blocs selon l'attribut du contact. | Un seul envoi à gérer. | Moteur conditionnel Brevo **limité et fragile** à maintenir. |
| **C** | **Mail générique + page web « hub »** | Le mail est un teaser identique ; un lien *« Voir l'édition Savoie »* mène à une **page web** qui filtre/réordonne. | Mail léger, **idéal pour les centres d'intérêt** et les stats de clic. | Suppose d'**héberger une page** (pas encore le cas — voir « tableau de bord » dans la feuille de route). |

**Ce que font les newsletters comparables** : éditions régionales de la presse
(une trame nationale + un bloc régional), sections thématiques type Substack
(modèle C), segmentation par centres d'intérêt façon Mailchimp/Brevo (groupes →
modèle A ou B). Le bilingue, lui, se fait quasi toujours en **deux versions par
langue** (modèle A).

**Recommandation** : démarrer en **modèle A** (réaliste sans page web, stats
propres), puis basculer les **centres d'intérêt** vers le **modèle C** quand le
tableau de bord web existera. Le modèle B n'est pas recommandé ici.

---

## 6. Est-ce qu'on a fait du bon travail ? — Oui

Avoir séparé **un JSON structuré** (contenu) d'**un gabarit** (rendu), avec un
**tag territoire** sur chaque brève, est *exactement* la bonne fondation : c'est
ce qui rend la personnalisation possible sans réécrire le contenu. Il reste à
ajouter, dans l'ordre :

1. ✅ **Rubrique « Ponts & connexions »** (schéma JSON + prompt + gabarit) — *fait
   à l'Étape 0, éditorial pur.*
2. ✅ **Attributs contacts** dans Brevo (`LANGUE`, `TERRITOIRE`, `SECTEURS`) +
   dossier/listes par langue — *outillé : `scripts/brevo_setup.py`, voir
   `docs/SETUP_BREVO_PERSONNALISATION.md`. Reste à exécuter sur le VPS et à
   renseigner les contacts.*
3. ✅ **Logique de variantes (langue)** : gabarit bilingue (`newsletter_variants`),
   traduction automatique du contenu (`utils/translate.py`) et **un brouillon Brevo
   par langue** (`push_brevo.py`, via `BREVO_LIST_ID_FR` / `BREVO_LIST_ID_IT`).
4. ✅ **Réordonnancement par territoire** (Étape 2) : rubrique « Chez vous » en
   tête + « Dans l'espace sabaudo » pour les autres, sans rien masquer. Édition
   produite si `BREVO_LIST_ID_<LANG>_<TERRITOIRE>` est défini.
5. ⬜ **Tag secteur** / page web pour les centres d'intérêt (Étape 3).

---

## 7. Feuille de route progressive

- **Étape 0 — éditorial (faite)** : rubrique « Ponts & connexions ». Règle le
  besoin transfrontalier sans aucun ciblage.
- **Prérequis Brevo (outillé)** : attributs `LANGUE` / `TERRITOIRE` / `SECTEURS`
  + listes par langue — `scripts/brevo_setup.py` (guide :
  `docs/SETUP_BREVO_PERSONNALISATION.md`).
- **Étape 1 — langue FR/IT (FAITE, code)** : deux versions via l'attribut `LANGUE`
  (modèle A). Gabarit bilingue + traduction IA + un brouillon Brevo par langue.
  *Reste : créer les listes FR/IT dans Brevo et renseigner `BREVO_LIST_ID_FR/_IT`.*
- **Étape 2 — territoire d'ancrage (FAITE, code)** : « Chez vous » en tête, les
  autres territoires conservés. Édition produite par territoire via
  `BREVO_LIST_ID_<LANG>_<TERRITOIRE>`. *Reste : créer les listes/segments de
  territoire dans Brevo et renseigner ces variables si on active cet axe.*
- **Étape 3 — centres d'intérêt** : via la page web « hub » (modèle C), quand le
  tableau de bord existera.

---

*Document de référence — évolue avec le projet. Le modèle technique cible
(A / B / C) pour les axes territoire et intérêt reste à arbitrer ; le présent
document recommande A pour démarrer.*

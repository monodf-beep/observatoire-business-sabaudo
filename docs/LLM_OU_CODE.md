# LLM ou code ? — règle de décision (commune aux projets)

> **Portée** : commun à l'écosystème (Observatoire, Agrégateur, Shopping Guide),
> voué à `cultura-core`. Pour **chaque** traitement qu'on ajoute, on se pose la
> question : **agent LLM, ou code déterministe ?** Par défaut → **code**.

## La règle

**Code déterministe** quand la tâche est :
- réglée par une **règle claire** (liste, format, seuil, calcul) ;
- sur des **données structurées** ;
- **à fort volume** / répétée (chaque événement, chaque jour) ;
- où l'on exige **fiabilité + coût nul + reproductibilité**.

**Agent LLM** seulement quand la tâche exige **irréductiblement** :
- de la **compréhension du langage** (texte libre, email, page web) ;
- du **jugement éditorial** (pertinence, angle, qualité) ;
- de la **génération** (rédiger, résumer, reformuler) ;
- un **appariement sémantique** ambigu que les heuristiques ratent.

**Hybride (le plus souvent le bon choix)** : **code d'abord** pour filtrer/grouper
à coût nul, **LLM seulement sur le résidu** ambigu. Ça borne la facture et garde le
système fonctionnel même quand le quota LLM est épuisé.

## Trois questions à se poser
1. Une **règle simple** donne-t-elle le bon résultat dans >90 % des cas ? → **code**.
2. La tâche se fait-elle sur **du langage / du jugement** ? → **LLM** (ou hybride).
3. Le volume × coût LLM est-il justifié, ou un **pré-filtre code** réduit-il l'appel ? → **hybride**.

## Application au pipeline de l'agrégateur

| Étape / tâche | LLM ou code | Pourquoi |
|---|---|---|
| Parsing RSS, extraction image, nettoyage HTML | **code** | format connu, déterministe |
| Dédup par `url_source` exacte | **code** | comparaison exacte |
| **Dédup multi-sources** (même_story + territoire + dates) | **code** | heuristique fiable, à fort volume, gratuit |
| **Choix/fusion de la meilleure source** | **code** | tiers curés + score de richesse = formule |
| Pré-filtre géographique (hors-périmètre évident) | **code** | liste de lieux connue → évite des appels LLM |
| Extraction d'événements depuis une **newsletter** | **LLM** | texte libre → structuré |
| **Évaluation éditoriale** (score, escalier, catégorie) | **LLM** | jugement éditorial |
| **Enrichissement** (chercher la source officielle, lire la page) | **LLM agent** (+ code pour fetch/og:image) | recherche web + lecture + jugement |
| **Rédaction** d'article | **LLM** | génération |
| Publication WordPress, changements de statut, compteurs, UX | **code** | actions déterministes |

## Cas limites / fallback
- **Dédup** : 99 % en code (heuristique). LLM **uniquement** pour confirmer une paire
  douteuse — optionnel, désactivable, jamais sur tout le volume.
- **Géo** : pré-filtre code (liste) ; le jugement fin reste dans l'évaluation LLM.
- Toujours préférer **dégrader proprement sans LLM** (quota épuisé) plutôt que bloquer.

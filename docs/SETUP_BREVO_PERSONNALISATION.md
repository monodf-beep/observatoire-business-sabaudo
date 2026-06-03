# Configurer Brevo pour la personnalisation

> Guide pas-à-pas (non technique) pour préparer Brevo à la newsletter
> personnalisée. À lire avec `docs/PERSONNALISATION.md` (la stratégie).
> Cultura Sabauda · franck.monod@culturasabauda.eu

---

## 1. Ce qu'on met en place et pourquoi

La personnalisation repose sur des **attributs de contact** : des étiquettes
posées sur chaque abonné, que Brevo utilise pour décider **quoi** lui envoyer et
**dans quel ordre**.

| Attribut | Rôle | Valeurs |
|----------|------|---------|
| `LANGUE` | Langue d'envoi | `FR` / `IT` |
| `TERRITOIRE` | Territoire d'ancrage (remonte en tête de sa lecture) | `Savoie` / `Piemonte` / `Vallee-Aoste` / `Nice` |
| `SECTEURS` | Centres d'intérêt (mots-clés libres) | ex. `deeptech,industrie,tourisme` |

> Ces trois attributs sont la **fondation commune** : ils servent quel que soit
> le modèle d'envoi retenu (segments, contenu conditionnel ou page web). On peut
> donc les créer **maintenant**, sans figer le choix du modèle.

On crée aussi un **dossier** « Business Sabaudo » et, dedans, deux **listes** :
`Business Sabaudo — FR` et `Business Sabaudo — IT` (point de départ pour la
langue, voir `PERSONNALISATION.md §7 Étape 1`).

---

## 2. La méthode automatique (recommandée)

Sur le serveur où tourne l'observatoire (le VPS, là où se trouve la clé Brevo
dans `.env`) :

```bash
# 1. Voir l'état actuel du compte (ne crée rien)
python scripts/brevo_setup.py --check

# 2. Simuler : montre ce qui SERAIT créé, sans rien écrire
python scripts/brevo_setup.py --dry-run

# 3. Appliquer (idempotent : ne recrée jamais l'existant, ne supprime rien)
python scripts/brevo_setup.py

# Variante : ne configurer que les attributs, sans créer de listes
python scripts/brevo_setup.py --no-lists
```

Le script est **sûr** : il ne fait que **créer ce qui manque** et ne supprime
jamais rien. On peut le relancer autant de fois qu'on veut.

> ⚠ **À lancer depuis le VPS.** Si le compte Brevo applique une **liste d'IP
> autorisées** (*Sécurité → Adresses IP autorisées*), seuls les appels venant
> d'une IP autorisée passent (sinon : `HTTP 401 unrecognised IP`). Le VPS a une
> IP stable à autoriser une fois. Les environnements de session (Claude Code web)
> ont au contraire une **IP de sortie qui change à chaque requête** : on ne peut
> donc pas y faire la config Brevo via l'allowlist. Vérifier l'IP autorisée :
> <https://app.brevo.com/security/authorised_ips>.

Après création des listes, le script affiche leurs **id** : reporter ces id dans
le `.env` (voir §4).

---

## 3. La méthode manuelle (si on préfère l'interface Brevo)

1. **Attributs** : *Contacts → Paramètres → Attributs de contact → Ajouter un
   attribut*. Créer `LANGUE`, `TERRITOIRE`, `SECTEURS`, tous en type **Texte**.
2. **Dossier + listes** : *Contacts → Listes → Ajouter un dossier* « Business
   Sabaudo », puis y créer les listes `Business Sabaudo — FR` et
   `Business Sabaudo — IT`.
3. **Renseigner les contacts** : à l'import CSV, ajouter les colonnes `LANGUE`,
   `TERRITOIRE`, `SECTEURS` et les remplir (`FR`, `Savoie`, etc.).

---

## 4. Variables d'environnement (.env)

```dotenv
BREVO_API_KEY=...            # déjà en place
BREVO_LIST_ID=2             # liste par défaut (envoi FR actuel)
# Étape 1 (langue) — à renseigner avec les id affichés par brevo_setup.py :
# BREVO_LIST_ID_FR=...
# BREVO_LIST_ID_IT=...
```

> La logique d'envoi qui exploite `LANGUE` / `TERRITOIRE` (génération d'une
> variante par segment) sera branchée aux **Étapes 1 et 2** de la feuille de
> route. Cette configuration Brevo en est le **prérequis**.

---

## 5. Remplir les attributs : par où commencer

- **Le plus simple** : un import CSV avec les colonnes `LANGUE` / `TERRITOIRE`.
- **Par défaut** : tout le monde en `FR`. Basculer en `IT` les contacts
  italophones quand le lectorat existe.
- **Territoire** : déduit de l'adresse ou de l'organisation du contact. En
  l'absence d'info, laisser vide → le lecteur reçoit l'édition générale
  (tous les territoires, sans réordonnancement).

---

## 5 bis. Ciblage par segments dynamiques (recommandé)

Plutôt que de trier les contacts dans des listes à la main, on **cible des
segments** : des filtres dynamiques sur `LANGUE` et `TERRITOIRE`. Un contact qui
remplit le formulaire se range **tout seul** dans le bon segment.

> ⚠ **Règle anti-doublon** : l'édition « générale » d'une langue doit EXCLURE les
> territoires qui ont leur propre édition, sinon un lecteur niçois reçoit deux
> emails. Les définitions ci-dessous intègrent ces exclusions.

Segments à créer (Contacts → Segments) — exemple de démarrage (FR + Nice +
Savoie, IT + Piémont) :

| Segment | Définition (conditions ET) | Variable `.env` |
|---------|----------------------------|-----------------|
| `Business Sabaudo — FR` (général) | `LANGUE = FR` **ET** `TERRITOIRE ≠ Nice` **ET** `TERRITOIRE ≠ Savoie` | `BREVO_SEGMENT_ID_FR` |
| `Business Sabaudo — IT` (général) | `LANGUE = IT` **ET** `TERRITOIRE ≠ Piemonte` | `BREVO_SEGMENT_ID_IT` |
| `Business Sabaudo — FR — Nice` | `LANGUE = FR` **ET** `TERRITOIRE = Nice` | `BREVO_SEGMENT_ID_FR_NICE` |
| `Business Sabaudo — FR — Savoie` | `LANGUE = FR` **ET** `TERRITOIRE = Savoie` | `BREVO_SEGMENT_ID_FR_SAVOIE` |
| `Business Sabaudo — IT — Piemonte` | `LANGUE = IT` **ET** `TERRITOIRE = Piemonte` | `BREVO_SEGMENT_ID_IT_PIEMONTE` |

> ⚠ Les valeurs de `TERRITOIRE` dans les segments doivent être EXACTEMENT celles
> de l'attribut Catégorie : **Savoie, Piemonte, Vallee-Aoste, Nice** (clés sans
> accent, identiques à celles du code). Une valeur accentuée (« Piémont ») ne
> matcherait aucun contact.

Renseigner les **id de segment** (affichés par `brevo_setup.py --check`) dans le
`.env`. Le segment est **prioritaire** sur la liste de même portée ; les listes
restent un repli.

> Pour activer un nouveau territoire plus tard : créer le segment territorial
> `LANGUE = X ET TERRITOIRE = Y`, **et** ajouter `ET TERRITOIRE ≠ Y` au segment
> général de la même langue.

---

## 6. Le formulaire d'inscription

Pour que **les nouveaux abonnés arrivent déjà étiquetés** (et qu'on n'ait pas à
deviner leur langue/territoire après coup), le formulaire d'inscription doit
collecter les attributs dès le départ.

> ⚠ Un formulaire Brevo se construit dans l'**éditeur de formulaires**
> (*Contacts → Formulaires → Créer un formulaire*). Il **n'est pas créable par
> script** (l'API Brevo n'expose pas cette opération de façon fiable). Voici la
> spécification exacte à reproduire.

**Champs du formulaire :**

| Champ | Type | Lié à l'attribut | Obligatoire |
|-------|------|------------------|-------------|
| Email | email | (email de contact) | ✅ |
| Langue préférée | liste déroulante / boutons radio : `FR`, `IT` | `LANGUE` | ✅ |
| Territoire | liste déroulante : `Savoie`, `Piemonte`, `Vallee-Aoste`, `Nice`, `Hors zone` | `TERRITOIRE` | optionnel |
| Centres d'intérêt | cases à cocher (deeptech, industrie, tourisme, agroalimentaire, finance, recherche…) | `SECTEURS` | optionnel |

**Réglages :**
- **Double opt-in** activé (l'abonné confirme par email → liste saine, meilleure
  délivrabilité ; voir `BONNES_PRATIQUES_NEWSLETTER.md §10`).
- **Case de consentement RGPD** explicite.
- **Liste cible** : rattacher l'inscrit à la liste correspondant à sa langue
  (`Business Sabaudo — FR` ou `IT`). Si Brevo ne permet pas le routage
  conditionnel sur un seul formulaire, créer **deux formulaires** (un par langue)
  ou rattacher tout le monde à une liste maître et router ensuite par segment sur
  l'attribut `LANGUE`.
- **Page de confirmation** + email de bienvenue (facultatif mais recommandé).

> Si `TERRITOIRE` est laissé vide, l'abonné reçoit l'**édition générale** (tous
> les territoires, sans réordonnancement) — aucun blocage.

---

## 7. Vérifier

```bash
python scripts/brevo_setup.py --check
```

La ligne *« manquants pour la perso »* doit afficher **aucun ✅**.

---

*Guide de référence — évolue avec le projet. Voir aussi
`docs/PERSONNALISATION.md` (stratégie) et `docs/BONNES_PRATIQUES_NEWSLETTER.md`.*

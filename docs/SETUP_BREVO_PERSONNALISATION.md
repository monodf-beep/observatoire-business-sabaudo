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

## 6. Vérifier

```bash
python scripts/brevo_setup.py --check
```

La ligne *« manquants pour la perso »* doit afficher **aucun ✅**.

---

*Guide de référence — évolue avec le projet. Voir aussi
`docs/PERSONNALISATION.md` (stratégie) et `docs/BONNES_PRATIQUES_NEWSLETTER.md`.*

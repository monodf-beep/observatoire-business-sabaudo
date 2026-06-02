# Donner les droits Google (Gmail + Drive) — guide pas-à-pas

Ce guide explique comment générer le fichier **`credentials.json`** qui autorise
l'observatoire à : lire les emails de veille (Gmail) et déposer les synthèses
dans le Drive. **Aucune compétence technique requise** : il suffit de suivre les
écrans dans l'ordre. Compte à utiliser : **franck.monod@culturasabauda.eu**.

> ⏱️ Durée : ~15 minutes, une seule fois.
> 🔒 Le fichier obtenu est un **secret** : ne jamais l'envoyer par email ni le
> mettre sur GitHub (il est déjà exclu automatiquement).

---

## Étape 1 — Ouvrir la console Google Cloud

1. Va sur **https://console.cloud.google.com/** et connecte-toi avec
   `franck.monod@culturasabauda.eu`.
2. En haut, clique sur le sélecteur de projet → **« Nouveau projet »**.
3. Nom du projet : `Observatoire Sabaudo` → **Créer**.
4. Attends quelques secondes, puis sélectionne ce projet (sélecteur en haut).

## Étape 2 — Activer les deux API nécessaires

1. Menu ☰ (en haut à gauche) → **« API et services » → « Bibliothèque »**.
2. Cherche **« Gmail API »** → clique dessus → bouton **« Activer »**.
3. Reviens à la Bibliothèque, cherche **« Google Drive API »** → **« Activer »**.

## Étape 3 — Configurer l'écran de consentement

1. Menu ☰ → **« API et services » → « Écran de consentement OAuth »**.
2. Type d'utilisateur : **Externe** → **Créer**.
3. Remplis le minimum demandé :
   - Nom de l'application : `Observatoire Sabaudo`
   - E-mail d'assistance : `franck.monod@culturasabauda.eu`
   - Coordonnées du développeur : `franck.monod@culturasabauda.eu`
   - **Enregistrer et continuer**.
4. Écran « Niveaux d'accès / Scopes » : tu peux **passer** (Enregistrer et continuer)
   — les scopes seront demandés automatiquement au premier lancement.
5. Écran « Utilisateurs test » → **« + Add users »** → ajoute
   `franck.monod@culturasabauda.eu` → **Enregistrer et continuer**.

> ℹ️ Tant que l'application reste en mode « test », c'est parfait : seuls les
> comptes ajoutés ici peuvent l'utiliser. Pas besoin de publication.

## Étape 4 — Créer les identifiants (le fameux credentials.json)

1. Menu ☰ → **« API et services » → « Identifiants »**.
2. Bouton **« + Créer des identifiants » → « ID client OAuth »**.
3. Type d'application : **« Application de bureau »**.
4. Nom : `Observatoire poste local` → **Créer**.
5. Une fenêtre s'affiche → bouton **« Télécharger le JSON »**.
6. **Renomme le fichier téléchargé en `credentials.json`.**

## Étape 5 — Déposer le fichier dans l'outil

Place `credentials.json` dans le dossier **`config/`** de l'observatoire
(sur la machine où l'outil tournera — voir `docs/DEPLOIEMENT.md`).

## Étape 6 — Première autorisation (une seule fois)

Au tout premier lancement d'un script, une page Google s'ouvre dans le
navigateur :

1. Choisis le compte `franck.monod@culturasabauda.eu`.
2. Google affiche **« Google n'a pas validé cette application »** (normal en mode test) :
   clique sur **« Paramètres avancés » → « Accéder à Observatoire Sabaudo (non sécurisé) »**.
3. Coche les autorisations demandées (lecture Gmail, gestion des fichiers Drive créés
   par l'app) → **Continuer**.

Un fichier `token.json` (et `token_drive.json` pour le Drive) est alors créé
automatiquement. **Les lancements suivants ne demanderont plus rien** — c'est ce
qui permet à la planification automatique (cron) de fonctionner seule.

---

## Ce que ces droits permettent (et ne permettent pas)

| Autorisation demandée | Ce que ça permet | Limite |
|-----------------------|------------------|--------|
| `gmail.readonly`      | **Lire** les emails de la whitelist | Aucune modification/suppression possible |
| `drive.file`          | **Créer / mettre à jour** les fichiers déposés par l'outil | L'outil ne voit **pas** tes autres fichiers Drive |

C'est volontairement le strict minimum : l'outil ne peut ni supprimer tes
emails, ni fouiller dans le reste de ton Drive.

---

## Dépannage

| Message | Solution |
|---------|----------|
| « Accès bloqué : Observatoire Sabaudo n'a pas terminé la procédure de validation » | Vérifie que ton compte est bien dans **Utilisateurs test** (Étape 3.5). |
| « redirect_uri_mismatch » | Le type d'application n'est pas « Application de bureau » — refais l'Étape 4 avec le bon type. |
| « invalid_grant » au lancement suivant | Le `token.json` a expiré/révoqué : supprime `config/token.json` (et `token_drive.json`) et relance pour réautoriser. |
| « insufficient authentication scopes » | Supprime les fichiers `token*.json` et relance : les nouveaux scopes seront redemandés. |

> Le dossier Drive cible est déjà renseigné dans `.env`
> (`DRIVE_FOLDER_ID=1OWmS4oC7rw2BGQtInnuM2_8kE0wkXv53`). Comme tu es propriétaire
> de ce dossier, le scope `drive.file` suffit pour y déposer — **inutile de
> partager le dossier**.

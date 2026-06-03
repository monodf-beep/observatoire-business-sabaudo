# Gestion des secrets (clés API, identifiants)

> Comment stocker la clé Brevo, la clé Anthropic et les identifiants Google de
> façon sûre. Solution **recommandée pour ce projet** (un VPS unique), + une
> option « coffre-fort » si on veut monter d'un cran.
> Cultura Sabauda · franck.monod@culturasabauda.eu

---

## 1. Les secrets du projet

| Secret | Où | Rôle |
|--------|-----|------|
| `ANTHROPIC_API_KEY` | `.env` | Rédaction de la synthèse (IA) |
| `BREVO_API_KEY` | `.env` | Dépôt des brouillons + config personnalisation |
| `config/credentials.json`, `config/token*.json` | fichiers | OAuth Google (Gmail + Drive) |

**Règle absolue** : aucun de ces éléments n'est versionné. Ils sont tous dans
`.gitignore` — à ne jamais retirer.

---

## 2. Recommandé : « coffre-fort niveau 0 » (un VPS)

Pour un seul serveur, le standard sûr et sans surcouche :

1. **Fichier `.env` sur le VPS**, jamais ailleurs, jamais commité.
2. **Permissions verrouillées** (lecture par le seul propriétaire) :
   ```bash
   chmod 600 .env config/credentials.json config/token*.json
   ```
   `install.sh` applique désormais ce verrouillage automatiquement.
3. **Source de vérité = un gestionnaire de mots de passe** (Bitwarden, 1Password,
   KeePass…). On y conserve une copie de chaque clé. Le `.env` du VPS n'est qu'une
   *copie de travail* ; si le serveur est perdu, les clés restent dans le coffre.
4. **Sauvegarde** : ne jamais sauvegarder le `.env` en clair dans un dossier
   synchronisé non chiffré (Drive, Dropbox…). La copie de référence vit dans le
   gestionnaire de mots de passe.

> Pour un projet de cette taille, c'est **suffisant et robuste**. Inutile de
> déployer une infrastructure de secrets dédiée.

---

## 3. Rotation des clés

Régénérer une clé (et mettre à jour le `.env` + le gestionnaire de mots de passe) :
- **immédiatement** si une clé a pu être exposée (collée dans un chat, un email,
  une capture d'écran, un commit) ;
- périodiquement (ex. tous les 6-12 mois) par hygiène.

Régénération :
- **Brevo** : *Paramètres → Clés API SMTP & API → régénérer*.
- **Anthropic** : console Anthropic → API keys → révoquer / recréer.

---

## 4. Option « niveau 1 » : un vrai coffre-fort avec injection

Si on veut **ne plus avoir de clé en clair sur le disque** : le secret vit dans
un coffre et est **injecté en variable d'environnement** au lancement.

- **Infisical** (open source, offre gratuite ou auto-hébergé) ou **Doppler**
  (SaaS, offre gratuite). Le cron devient par ex. :
  ```bash
  doppler run -- python scripts/synthesize.py --upload --brevo
  ```
- **Bitwarden Secrets Manager** (CLI `bws`) si Bitwarden est déjà utilisé.

> À envisager seulement si le besoin grandit (plusieurs serveurs, plusieurs
> personnes, audit). Pour l'instant, le niveau 0 reste recommandé.

---

## 5. Cas particulier : la clé Brevo et l'allowlist d'IP

Si le compte Brevo restreint les **adresses IP autorisées**, la clé ne fonctionne
que depuis une IP listée. Le **VPS** (IP stable) est l'endroit naturel pour la
clé Brevo. Les environnements de session (Claude Code web) ont une IP de sortie
**changeante** : on n'y configure donc pas Brevo via l'allowlist. Voir
`docs/SETUP_BREVO_PERSONNALISATION.md §2`.

---

*Document de référence — évolue avec le projet.*

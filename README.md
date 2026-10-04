# 📅 Suivi d'emploi du temps — B2 INFO Martinique

Programme qui surveille ton emploi du temps Hyperplanning et te prévient sur Discord :

- **en DM** quand un cours est ajouté, modifié, annulé ou reporté (avec un **PDF détaillé** s'il y a plus de 5 changements urgents/importants d'un coup, sauf si ce ne sont que des changements de salle) ;
- **dans un salon de logs** à chaque passage : heure, ce qui a été détecté (enseignant, salle, ancien → nouveau), ou « aucun changement ».

Il tourne gratuitement sur **GitHub Actions**, toutes les 2 h de 5h à 21h (heure de Martinique). Rien à installer sur ton PC.

| Degré | Signification |
|---|---|
| 🔴 A · URGENT | cours dans la semaine en cours (lundi → samedi ; le dimanche, c'est la semaine qui commence le lendemain) |
| 🟠 B · IMPORTANT | cours dans l'une des 2 semaines suivantes, même si ça déborde sur le mois d'après |
| 🟡 C · MOYEN | plus tard, mais dans le mois en cours |
| ⚪ D · FAIBLE | tout le reste |

Pour un cours **déplacé**, c'est le créneau le plus proche (ancien ou nouveau) qui compte : un cours de demain repoussé au mois prochain reste urgent.

---

## Installation (≈ 15 min, une seule fois)

### 1. Créer le bot Discord

1. Va sur <https://discord.com/developers/applications> → **New Application** → nomme-la (ex. « EDT Bot »).
2. Menu **Bot** → **Reset Token** → copie le jeton et garde-le de côté (c'est `DISCORD_BOT_TOKEN`). Aucun « Privileged Gateway Intent » n'est nécessaire.
3. Menu **OAuth2 → URL Generator** : coche le scope **bot**, puis les permissions **View Channels**, **Send Messages**, **Attach Files**. Ouvre l'URL générée et ajoute le bot à ton serveur (un serveur perso suffit).

### 2. Préparer Discord

1. Crée un salon texte pour les logs, par ex. `#edt-logs` (tu peux le mettre en sourdine : seuls les DM doivent te notifier).
2. Active le mode développeur : **Paramètres utilisateur → Avancés → Mode développeur**.
3. Clic droit sur le salon → **Copier l'identifiant du salon** (`DISCORD_LOG_CHANNEL_ID`).
4. Clic droit sur ton pseudo → **Copier l'identifiant de l'utilisateur** (`DISCORD_USER_ID`).
5. Clic droit sur le serveur → **Paramètres de confidentialité** → active **Messages privés**, sinon le bot ne pourra pas t'écrire.

### 3. Mettre le code sur GitHub

1. Sur GitHub : **New repository** → nom `edt-bot` → **Public** → *Create repository*.
2. Clique **uploading an existing file**, puis glisse **tout le contenu** du dossier décompressé (y compris le dossier `.github`) → **Commit changes**.
   > Si le dossier `.github` n'a pas été envoyé (il est parfois masqué) : **Add file → Create new file**, nomme-le `.github/workflows/edt.yml` et colle le contenu du fichier.

> **Pourquoi public ?** Sur un compte gratuit, les tâches planifiées des dépôts privés ne sont pas fiables, alors qu'elles sont illimitées en public. Seul le **code** est visible : ton lien ICS et ton jeton Discord sont dans les secrets (chiffrés), l'EDT est gardé dans le cache GitHub (non public), et le programme n'écrit jamais le contenu de ton EDT dans les journaux d'exécution.

### 4. Ajouter les 4 secrets

Dans le dépôt : **Settings → Secrets and variables → Actions → New repository secret**, une fois pour chaque ligne :

| Nom | Valeur |
|---|---|
| `ICS_URL` | ton lien d'export Hyperplanning (`https://edt.univ-antilles.fr/hp/Telechargements/ical/Edt_TRANQUILLE.ics?...`) |
| `DISCORD_BOT_TOKEN` | le jeton du bot (étape 1) |
| `DISCORD_USER_ID` | ton identifiant Discord |
| `DISCORD_LOG_CHANNEL_ID` | l'identifiant du salon de logs |

### 5. Vérifier et démarrer

Onglet **Actions** (accepte l'activation des workflows si GitHub le demande) → **Suivi EDT** → **Run workflow** :

1. mode **setup** → tu dois recevoir un DM de test et un message dans le salon de logs. Si une étape échoue, le journal de l'exécution dit quoi corriger.
2. mode **demo** *(facultatif)* → un exemple de notification + PDF fabriqué à partir de ton vrai EDT (changements fictifs, rien n'est enregistré).
3. mode **run** → première exécution : l'EDT actuel est enregistré comme référence, sans alerte. Ensuite, c'est automatique.

### 6. Couper l'ancien système

Une fois le premier vrai passage réussi :

- **désactive l'ancienne tâche planifiée dans Claude**, sinon tu seras prévenu deux fois ;
- facultatif : les e-mails de Google Agenda ne servent plus. Tu peux couper les notifications du calendrier « HYP - TRANQUILLE… » dans les paramètres de Google Agenda, ou créer un filtre Gmail `from:calendar-notification@google.com TRANQUILLE` → *Supprimer*.

---

## Au quotidien

- **Aucun changement** → pas de DM, juste une ligne dans le salon de logs. Pour ne plus avoir ces lignes : **Settings → Secrets and variables → Actions → Variables → New repository variable** `LOG_QUIET_RUNS` = `false`.
- **Site de l'université en panne** → l'erreur est notée dans les logs ; au bout de 3 échecs de suite (≈ 6 h) tu reçois un DM, puis un autre quand ça refonctionne.
- **EDT soudain presque vide** (souvent un bug côté Hyperplanning) → ignoré pendant 2 passages pour éviter une avalanche de fausses annulations, puis accepté s'il persiste.
- **Discord en panne** → le changement n'est pas marqué comme envoyé : il sera renvoyé au passage suivant. GitHub t'envoie aussi un e-mail en cas d'échec.
- **Nouvelle année scolaire** → remplace simplement le secret `ICS_URL` par le nouveau lien.
- GitHub peut décaler un passage planifié de quelques minutes quand ses serveurs sont chargés : c'est normal.

## Pour développer

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q                                  # 44 tests
ICS_URL=mon_edt.ics python -m edt_bot run --dry-run  # affiche les messages au lieu de les envoyer
```

| Fichier | Rôle |
|---|---|
| `edt_bot/ics.py` | téléchargement et lecture de l'ICS Hyperplanning |
| `edt_bot/diff.py` | détection des changements (gère les « Annulation : … » qu'Hyperplanning crée avec un nouvel identifiant) |
| `edt_bot/priority.py` | degrés A/B/C/D |
| `edt_bot/formatting.py` | textes des DM et des logs |
| `edt_bot/report.py` | rapport PDF |
| `edt_bot/discord_api.py` | envoi des messages Discord |
| `edt_bot/__main__.py` | déroulé d'une exécution, modes `setup` et `demo` |
| `.github/workflows/edt.yml` | planification sur GitHub Actions |

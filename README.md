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

### Actions disponibles

1. mode **setup** → tu dois recevoir un DM de test et un message dans le salon de logs. Si une étape échoue, le journal de l'exécution dit quoi corriger.
2. mode **demo** *(facultatif)* → un exemple de notification + PDF fabriqué à partir de ton vrai EDT (changements fictifs, rien n'est enregistré).
3. mode **run** → première exécution : l'EDT actuel est enregistré comme référence, sans alerte. Ensuite, c'est automatique.

## Au quotidien

- **Aucun changement** → pas de DM, juste une ligne dans le salon de logs. Pour ne plus avoir ces lignes : **Settings → Secrets and variables → Actions → Variables → New repository variable** `LOG_QUIET_RUNS` = `false`.
- **Site de l'université en panne** → l'erreur est notée dans les logs ; au bout de 3 échecs de suite (≈ 6 h) tu reçois un DM, puis un autre quand ça refonctionne.
- **EDT soudain presque vide** (souvent un bug côté Hyperplanning) → ignoré pendant 2 passages pour éviter une avalanche de fausses annulations, puis accepté s'il persiste.
- **Discord en panne** → le changement n'est pas marqué comme envoyé : il sera renvoyé au passage suivant. GitHub t'envoie aussi un e-mail en cas d'échec.
- **Nouvelle année scolaire** → remplace simplement le secret `ICS_URL` par le nouveau lien.
- GitHub peut décaler un passage planifié de quelques minutes quand ses serveurs sont chargés : c'est normal.


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

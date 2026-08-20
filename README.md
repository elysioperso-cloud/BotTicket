# Bot Discord — Système de tickets

Bot discord.py (Python 3.10+) avec système de tickets complet et configuration externe via `config.json`.

## ⚠️ Adaptation par rapport à la demande

Discord ne permet pas d'avoir simultanément `/ticket <salon>` (commande directe) et
`/ticket add <membre>` (sous-commande) sur la même commande de premier niveau. Le
bot utilise donc un **groupe de commandes** `/ticket` avec deux sous-commandes :

- `/ticket panel salon:<#salon>` → envoie le panneau d'ouverture de tickets (équivalent du `/ticket [salon]` demandé)
- `/ticket add membre:<@membre>` → ajoute un membre au ticket en cours (identique à la demande)

## 1. Installation

```bash
pip install -r requirements.txt
```

## 2. Configuration (`config.json`)

| Clé | Description |
|---|---|
| `token` | Token du bot Discord |
| `guild_id` | ID du serveur (permet une synchro instantanée des slash commands) |
| `ticket_category_id` | Catégorie où les tickets sont créés (par défaut `1540000643140427776`) |
| `transcript_channel_id` | Salon où les transcripts TXT sont envoyés (par défaut `1540003617673576479`) |
| `support_role_ids` | Liste des IDs de rôles Support autorisés |
| `emojis` | Tous les emojis utilisés dans les embeds/boutons (personnalisables sans toucher au code) |

Remplacez les valeurs d'exemple par les vraies valeurs de votre serveur.

## 3. Portail développeur Discord

- Activez l'intent **Server Members Intent** (Privileged Gateway Intents).
- Invitez le bot avec les scopes `bot` + `applications.commands`.
- Le bot doit avoir les permissions : `Gérer les salons`, `Gérer les permissions`, `Épingler les messages`, `Gérer les messages`, `Joindre des fichiers`.

## 4. Lancement

```bash
python bot.py
```

## 5. Fonctionnement

### `/ticket panel salon:<#salon>` (Administrateur uniquement)
Envoie l'embed **Support Ticket** avec 3 boutons :
- 🟢 **Ouvrir un ticket**
- ⬛ **Rapport de bug**
- ⬛ **Contestation de sanction**

Chaque bouton crée un salon privé dans la catégorie configurée, visible uniquement par
le créateur, les rôles Support et le bot. Un embed de bienvenue (épinglé) est envoyé
avec 4 boutons de gestion :

- 🔵 **Claim** → annonce publiquement « {user} a claim ce ticket ». Réservé au Support/Admin/`kick_members`.
- ⬛ **Close** → verrouille l'écriture pour l'ouvreur et masque le salon pour `@everyone`. Autorisé pour le Support/Admin/`kick_members` **ou** l'auteur du ticket.
- 🟢 **Réouvrir** → restaure l'accès en écriture. Même règle que Close.
- 🔴 **Supprimer** → génère un transcript `.txt` horodaté (auteur + contenu de chaque message) envoyé dans le salon transcript, puis supprime le salon. Réservé au Support/Admin/`kick_members`.

Toute tentative non autorisée renvoie un message éphémère citant les rôles Support (@mention) autorisés.

### `/ticket add membre:<@membre>`
Utilisable uniquement dans un salon de ticket, par l'auteur du ticket ou un membre Support/Admin.
Ajoute le membre avec accès en lecture/écriture au salon.

## 6. Persistance

- Les vues (boutons) sont **persistantes** : elles continuent de fonctionner après un redémarrage du bot, y compris sur les tickets déjà ouverts.
- Les tickets ouverts (auteur, type, claim, statut) sont stockés dans `data/tickets.json`.

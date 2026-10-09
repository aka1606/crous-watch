# crous-watch

Petit script Python qui surveille les logements CROUS disponibles autour d'Avignon et m'envoie un mail dès qu'une nouvelle offre apparaît.

Je l'ai écrit pendant ma recherche de logement étudiant : les studios partent en quelques heures, et rafraîchir le site à la main n'était pas tenable.

## Fonctionnement

- Interroge toutes les 5 minutes l'API de [trouverunlogement.lescrous.fr](https://trouverunlogement.lescrous.fr) sur une zone géographique donnée
- Compare avec les logements déjà vus (stockés dans `seen.json`)
- Envoie un récapitulatif par mail (Gmail, mot de passe d'application) quand un logement apparaît ou change

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Tout passe par des variables d'environnement (un fichier `.env`, ignoré par Git, peut les contenir) :

| Variable | Rôle | Valeur par défaut |
|---|---|---|
| `GMAIL_USER` | adresse Gmail d'envoi | — |
| `GMAIL_APP_PASSWORD` | mot de passe d'application Gmail | — |
| `MAIL_TO` | destinataire | `GMAIL_USER` |
| `CROUS_BOUNDS` | zone surveillée (`lon1_lat1_lon2_lat2`) | Avignon |
| `CROUS_LOCATION_NAME` | nom affiché dans les logs | `Avignon (84000)` |
| `CROUS_INTERVAL` | intervalle en secondes | `300` |

## Lancement

```bash
python3 crous_watch_v2.py          # surveillance en continu
python3 crous_watch_v2.py --once   # un seul passage
```

# Network Monitor — Système de Monitoring Réseau Distribué

> Architecture Client–Serveur TCP · Dashboard Temps Réel · Python 3.9+

---

## Table des matières

1. Vue d'ensemble
2. Structure des fichiers
3. Prérequis
4. Exécution des tests
5. Protocole TCP
6. Health Score
7. Détection d'anomalies
8. Protection anti-flood
9. Configuration
10. Isolation des sessions

---

## Vue d'ensemble

Ce projet implémente un système de **monitoring réseau distribué** en Python pur (bibliothèque standard uniquement). Chaque agent déployé sur une machine collecte des métriques CPU et RAM et les transmet en temps réel à un serveur central via des sockets TCP. Le serveur agrège les données, détecte les anomalies et les affiche dans un tableau de bord graphique Tkinter.

```
Agent 1 ──┐
Agent 2 ──┤──TCP -> Serveur Collecteur (server.py) -> Dashboard Tkinter (dashboard.py)
Agent N ──┘              |
                    shared_state.py
```

---

## Structure des fichiers

| Fichier           | Rôle                                                                |
|-------------------|---------------------------------------------------------------------|
| `projet.py`       | Configuration centrale (ports, seuils, timings)                     |
| `shared_state.py` | État partagé entre serveur et dashboard (agents, historique, flood) |
| `main.py`         | Lance serveur TCP + dashboard dans le même processus                |
| `agent.py`        | Client TCP — collecte et envoie les métriques CPU/RAM               |
| `dashboard.py`    | Interface graphique Tkinter                                         |
| `server.py`       | Serveur TCP standalone                                              |

### Scripts de test

| Fichier                          | Scénario testé                                |
|----------------------------------|-----------------------------------------------|
| `test_1_utilisateur.py`          | Cycle de vie complet d'un seul agent          |
| `test_plusieurs_utilisateurs.py` | 5 agents simultanés                           |
| `test_attaques.py`               | Flood (option 1) + fausses données (option 2) |
| `test_arret_brutal.py`           | Déconnexion sans BYE, détection de timeout    |

---

## Prérequis

- **Python 3.9+** (testé sous Windows 10, macOS 12, Ubuntu 20.04)
- **tkinter** — inclus dans la distribution standard Python
- **psutil** — optionnel ; des valeurs simulées réalistes sont utilisées en son absence. Sur Linux, peut nécessiter une installation séparée :

```bash
pip install psutil
```

---

## Exécution des tests

Chaque script de test est **autonome** : il démarre le serveur, le dashboard et les agents automatiquement. Il suffit d'ouvrir le fichier dans VS Code et d'appuyer sur **Run** (ou d'exécuter dans un terminal externe).

Les sorties s'affichent dans les terminaux VS Code. Le dashboard graphique Tkinter s'ouvre automatiquement dans une fenêtre séparée.

```bash
# 1 agent
python test_1_utilisateur.py

# 5 agents simultanés
python test_plusieurs_utilisateurs.py

# Simulation d'attaque (flood ou fausses données)
python test_attaques.py

# Déconnexion brutale sans BYE
python test_arret_brutal.py
```

> **Note :** chaque exécution de test choisit automatiquement un port TCP libre via `port_libre()`. Deux tests lancés simultanément sont parfaitement isolés.

### Problème rencontré — lancement en plusieurs étapes

Au départ, le lancement nécessitait d'ouvrir trois terminaux séparés manuellement (`dashboard.py`, puis `main.py`, puis le script de test). Cela rendait l'exécution lourde et propice aux erreurs d'ordre de démarrage. Ce problème a été corrigé : désormais, un seul Run sur le script de test suffit pour tout démarrer automatiquement.

---

## Protocole TCP (texte · UTF-8)

Chaque message est une **ligne terminée par `\n`**.

### Messages Client → Serveur

| Message  | Format                                             | Description                                    |
|----------|----------------------------------------------------|------------------------------------------------|
| `HELLO`  | `HELLO <agent_id> <hostname>`                      | Enregistrement de l'agent                      |
| `REPORT` | `REPORT <agent_id> <timestamp> <cpu_pct> <ram_mb>` | Envoi d'une mesure périodique                  |
| `BYE`    | `BYE <agent_id>`                                   | Déconnexion propre                             |

**Contraintes de validation :**
- `agent_id` : sans espaces
- `cpu_pct` : flottant dans `[0.0, 100.0]`
- `ram_mb` : flottant dans `[0.0, 1 000 000]`
- `timestamp` : epoch Unix (float)

### Réponses Serveur → Client

| Réponse          | Signification                                            |
|------------------|----------------------------------------------------------|
| `OK`             | Commande acceptée et traitée                             |
| `ERROR <raison>` | Refus : format, valeur hors plage, flood, agent inconnu… |

---

## Health Score

Chaque agent reçoit un **score entre 0 et 100** recalculé à chaque REPORT.

| Condition                           | Pénalité                     |
|-------------------------------------|------------------------------|
| CPU > 50 %                          | −0,5 pt par % excédentaire   |
| RAM > 60 % (estimée)                | −0,3 pt par % excédentaire   |
| Statut `inactif` (timeout)          | −40 pts                      |
| Statut `suspect` (flood / anomalie) | −70 pts                      |
| Données nulles (cpu=0, ram=0)       | −50 pts                      |
| Agent banni (flood)                 | 0 pts fixe                   |
| Agent déconnecté (BYE)              | `None` — exclu du classement |

| Score      | Label    | Couleur dashboard |
|------------|----------|-------------------|
| ≥ 75       | OK       | Vert              |
| 40–74      | WARNING  | Jaune             |
| 0–39       | CRITICAL | Rouge             |
| déconnecté | —        | Gris              |

---

## Détection d'anomalies

Le serveur maintient un **historique glissant** des `HISTORY_SIZE` (10) dernières mesures par agent. Une anomalie est levée si :

- **CPU SPIKE** : `cpu_actuel > moyenne_glissante_cpu + 20 %`
- **RAM SURGE** : `ram_actuelle > moyenne_glissante_ram + 15 MB`

La détection nécessite au minimum **3 mesures historiques** pour éviter les faux positifs au démarrage. En cas d'anomalie, l'agent passe en statut `suspect` et l'événement est journalisé avec horodatage.

---

## Protection anti-flood

Un compteur glissant par agent mesure le nombre de `REPORT` dans une fenêtre de **5 secondes**.

| Paramètre                                 | Valeur par défaut |
|-------------------------------------------|-------------------|
| Fenêtre de mesure (`FLOOD_WINDOW`)        | 5 s               |
| Seuil de flood (`FLOOD_MAX`)              | 20 REPORTs        |
| Durée du ban (`FLOOD_BAN_TIME`)           | 30 s              |

En cas de dépassement :
1. L'agent est banni pour 30 secondes
2. Son statut passe à `suspect`, health score = 0
3. Tout REPORT pendant le ban reçoit `ERROR banned flood`

---

## Configuration (`projet.py`)

Tous les paramètres sont centralisés dans `projet.py` et peuvent être surchargés via variables d'environnement.

```python
PORT = int(os.environ.get("MONITOR_PORT", 9999))   # port dynamique
T    = 5        # intervalle entre REPORTs (secondes)
TIMEOUT_AGENT   = 3 * T       # délai avant statut inactif
FLOOD_MAX       = 20          # REPORTs max par fenêtre
FLOOD_WINDOW    = 5           # fenêtre anti-flood (secondes)
FLOOD_BAN_TIME  = 30          # durée du ban (secondes)
ANOMALY_CPU_DELTA = 20.0      # seuil spike CPU (%)
ANOMALY_RAM_DELTA = 15.0      # seuil surge RAM (MB)
HISTORY_SIZE    = 10          # taille fenêtre glissante
```

---

## Isolation des sessions

Chaque script de test appelle `port_libre()` au démarrage, qui demande au système d'exploitation un port TCP disponible. Ce port est transmis via `MONITOR_PORT` :

```python
PORT = int(os.environ.get("MONITOR_PORT", 9999))
```

Deux tests lancés simultanément utilisent des ports différents et sont **complètement isolés**.

---

*Projet Téléinformatique — INSAT · Université de Carthage · 2025-2026*  
*Cherif Lina · Baha Eddine Zouabi · Farah Feriel*


#  projet.py — Configuration centrale du projet

import os

# --- Réseau ---
HOST      = "0.0.0.0"        # Le serveur écoute sur toutes les interfaces
SERVER_IP = "127.0.0.1"      # Adresse que les clients utilisent pour se connecter

# Port dynamique : chaque instance utilise un port différent
# On lit la variable d'environnement MONITOR_PORT, sinon 9999 par défaut
PORT = int(os.environ.get("MONITOR_PORT", 9999))

# --- Timing ---
T             = 5             # Intervalle entre chaque REPORT (en secondes)
TIMEOUT_AGENT = 3 * T        # Agent inactif si aucun REPORT reçu pendant 3×T secondes

# --- Seuils d'alerte fixes ---
CPU_ALERT_THRESHOLD = 80.0   # Alerte si CPU > 80 %
RAM_ALERT_THRESHOLD = 90.0   # Alerte si RAM > 90 %

# --- Détection d'anomalies dynamique ---
ANOMALY_CPU_DELTA = 20.0     # Spike CPU : si cpu > moyenne_historique + 20 → alerte
ANOMALY_RAM_DELTA = 15.0     # Montée RAM : si ram > moyenne_historique + 15 → warning
HISTORY_SIZE      = 10       # Nombre de mesures conservées pour le calcul de moyenne glissante

# --- Protection anti-flood ---
FLOOD_WINDOW   = 5           # Fenêtre en secondes pour compter les REPORT
FLOOD_MAX      = 20          # Nombre max de REPORT autorisés dans la fenêtre
FLOOD_BAN_TIME = 30          # Durée de bannissement en secondes après détection flood

# --- Validation des données ---
CPU_MIN, CPU_MAX = 0.0, 100.0
RAM_MIN          = 0.0
RAM_MAX_MB       = 1_000_000  # 1 To de RAM max (valeur extrême = suspect)

# --- Health Score ---
SCORE_CPU_PENALTY  = 0.5     # Points retirés par % de CPU au-dessus de 50 %
SCORE_RAM_PENALTY  = 0.3     # Points retirés par % de RAM au-dessus de 60 %
SCORE_INACTIVE_MAL = 40      # Malus si agent inactif
SCORE_SUSPECT_MAL  = 70      # Malus si agent suspect (flood/anomalie détectée)

# --- Export CSV ---
CSV_FILE = "stats_export.csv"

# --- Affichage serveur ---
STATS_INTERVAL = T            # Stats globales toutes les T secondes

# --- Encodage ---
ENCODING    = "utf-8"
BUFFER_SIZE = 4096            # Augmenté pour les messages longs / flood

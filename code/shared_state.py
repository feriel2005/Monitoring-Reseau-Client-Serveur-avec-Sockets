
#  Contient : agents, historique CPU/RAM, journal d'événements, compteurs flood, bannissements
import threading
from collections import deque

import projet

#  Dictionnaire principal des agents
#  Clé : agent_id (str)
#  Valeur : dict avec les champs suivants :
#    hostname    – nom de la machine
#    cpu         – dernière valeur CPU (%)
#    ram         – dernière valeur RAM (MB)
#    last_seen   – timestamp du dernier REPORT reçu
#    addr        – IP source du client
#    status      – "actif" | "inactif" | "déconnecté" | "suspect"
#    latence     – délai entre timestamp envoyé et réception (ms)
#    health      – score de santé 0-100
#    anomaly     – dernière anomalie détectée (str ou None)
agents = {}

#  Historique glissant CPU/RAM par agent
histo = {}            # { agent_id: deque(maxlen=HISTORY_SIZE) }

#  Journal d'événements (log) — liste de str horodatées
event_log = deque(maxlen=200)

#  Anti-flood
compteur_flood = {}   # { agent_id: deque() }
bannis         = {}   # { agent_id: ban_expiry_timestamp }

#  Verrou unique pour tous les accès
agents_lock = threading.Lock()


def add_event(msg: str):
    """Ajoute une entrée horodatée dans le journal."""
    import time
    event_log.appendleft(f"[{time.strftime('%H:%M:%S')}] {msg}")

def get_history(agent_id: str):
    """Retourne (ou crée) la deque d'historique d'un agent."""
    if agent_id not in histo:
        histo[agent_id] = deque(maxlen=projet.HISTORY_SIZE)
    return histo[agent_id]

def compute_health(agent_id: str) -> int:
    """
    Calcule un score de santé entre 0 et 100 pour un agent.
    Les agents déconnectés retournent None (exclus du classement).
    Pénalités :
      - CPU > 50 % → -0.5 pt par % excédentaire
      - RAM > 60 % → -0.3 pt par % excédentaire
      - Inactif     → -40 pts
      - Suspect     → -70 pts
    """
    if agent_id not in agents:
        return 0

    infos = agents[agent_id]

    # Agents déconnectés : exclus du classement (score None)
    if infos["status"] == "déconnecté":
        return None

    # Agent banni → score nul
    if is_banned(agent_id):
        return 0

    note = 100.0

    # Données suspectes (tout à zéro)
    if infos["cpu"] <= 0.01 and infos["ram"] <= 0.01:
        note -= 50

    # Pénalité CPU
    if infos["cpu"] > 50:
        note -= (infos["cpu"] - 50) * projet.SCORE_CPU_PENALTY

    # Pénalité RAM
    h = list(get_history(agent_id))
    if h:
        vals_ram   = [r for (_, _, r) in h]
        pic_ram    = max(vals_ram) if vals_ram else infos["ram"]
        ram_totale = max(pic_ram * 1.2, 4096)
        pct_ram    = (infos["ram"] / ram_totale) * 100
        if pct_ram > 60:
            note -= (pct_ram - 60) * projet.SCORE_RAM_PENALTY

    # Malus statut
    if infos["status"] == "suspect":
        note -= projet.SCORE_SUSPECT_MAL
    elif infos["status"] == "inactif":
        note -= projet.SCORE_INACTIVE_MAL

    return max(0, min(100, int(note)))


def detect_anomaly(agent_id: str, cpu: float, ram: float):
    """
    Détection dynamique d'anomalies :
      - Spike CPU : cpu > moyenne_glissante + ANOMALY_CPU_DELTA
      - Montée RAM : ram > moyenne_glissante + ANOMALY_RAM_DELTA
    Retourne une chaîne décrivant l'anomalie, ou None.
    """
    h = list(get_history(agent_id))
    if len(h) < 3:
        return None

    cpus    = [c for (_, c, _) in h]
    rams    = [r for (_, _, r) in h]
    moy_cpu = sum(cpus) / len(cpus)
    moy_ram = sum(rams) / len(rams)

    alertes = []
    if cpu > moy_cpu + projet.ANOMALY_CPU_DELTA:
        alertes.append(f"CPU SPIKE ({cpu:.1f}% vs moy {moy_cpu:.1f}%)")
    if ram > moy_ram + projet.ANOMALY_RAM_DELTA:
        alertes.append(f"RAM SURGE ({ram:.0f}MB vs moy {moy_ram:.0f}MB)")

    return " | ".join(alertes) if alertes else None


def check_flood(agent_id: str) -> bool:
    """
    Vérifie si l'agent dépasse le seuil de REPORT dans la fenêtre glissante.
    Retourne True si flood détecté.
    """
    import time
    maintenant = time.time()

    if agent_id not in compteur_flood:
        compteur_flood[agent_id] = deque()

    dq = compteur_flood[agent_id]
    dq.append(maintenant)

    while dq and dq[0] < maintenant - projet.FLOOD_WINDOW:
        dq.popleft()

    if len(dq) > projet.FLOOD_MAX:
        bannis[agent_id] = maintenant + projet.FLOOD_BAN_TIME
        add_event(f"🚨 FLOOD détecté : {agent_id} ({len(dq)} REPORT/{projet.FLOOD_WINDOW}s) → banni {projet.FLOOD_BAN_TIME}s")
        return True

    return False


def is_banned(agent_id: str) -> bool:
    """Retourne True si l'agent est actuellement banni."""
    import time
    if agent_id in bannis:
        if time.time() < bannis[agent_id]:
            return True
        else:
            del bannis[agent_id]
    return False

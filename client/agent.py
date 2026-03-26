# ============================================================
#  agent.py — Client TCP de monitoring
# ============================================================

import socket
import threading
import time
import sys
import os #pour construire les chemins de fichiers
import argparse #pour lire les arguments de la ligne de commande 

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")) #?
import config

try:
    import psutil #bibliotheque qui extrait des info relatives au systeme tels que (CPU, RAM,...)  PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False #on utilisera une méthode alternative pour lire le CPU/RAM


# ============================================================
#  Lecture CPU et RAM
# ============================================================
def lire_cpu():
    if PSUTIL_AVAILABLE:
        return psutil.cpu_percent(interval=0.5)
    with open("/proc/stat") as f:
        line = f.readline()
    vals = list(map(int, line.split()[1:]))
    idle = vals[3]
    total = sum(vals)
    time.sleep(0.5)
    with open("/proc/stat") as f:
        line = f.readline()
    vals2 = list(map(int, line.split()[1:]))
    idle2 = vals2[3]
    total2 = sum(vals2)
    return round(100.0 * (1 - (idle2 - idle) / (total2 - total)), 1)


def lire_ram():
    if PSUTIL_AVAILABLE:
        return round(psutil.virtual_memory().used / 1024 / 1024, 1)
    with open("/proc/meminfo") as f:
        lines = f.readlines()
    mem = {}
    for line in lines:
        parts = line.split()
        mem[parts[0].rstrip(":")] = int(parts[1])
    used_kb = mem["MemTotal"] - mem["MemAvailable"]
    return round(used_kb / 1024, 1)


# ============================================================
#  Fonction principale de l'agent
# ============================================================
def run_agent(agent_id):
    hostname = socket.gethostname()
    print(f"[*] Agent '{agent_id}' démarré sur {hostname}")
    print(f"[*] Connexion vers {config.SERVER_IP}:{config.PORT}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((config.SERVER_IP, config.PORT))
        print(f"[✓] Connecté au serveur")

        hello_msg = f"HELLO {agent_id} {hostname}\n"
        sock.sendall(hello_msg.encode(config.ENCODING))

        reponse = sock.recv(config.BUFFER_SIZE).decode(config.ENCODING).strip()
        print(f"[←] Serveur : {reponse}")

        if reponse != "OK":
            print(f"[!] Enregistrement refusé : {reponse}")
            return

        print(f"[*] Envoi de rapports toutes les {config.T}s. Ctrl+C pour arrêter.\n")

        while True:
            time.sleep(config.T)

            cpu = lire_cpu()
            ram = lire_ram()
            ts  = time.time()

            report_msg = f"REPORT {agent_id} {ts} {cpu} {ram}\n"
            sock.sendall(report_msg.encode(config.ENCODING))
            print(f"[→] REPORT envoyé — CPU: {cpu}% | RAM: {ram} MB")

            reponse = sock.recv(config.BUFFER_SIZE).decode(config.ENCODING).strip()
            if reponse != "OK":
                print(f"[!] Erreur serveur : {reponse}")

    except ConnectionRefusedError:
        print(f"[!] Impossible de se connecter : serveur injoignable sur {config.SERVER_IP}:{config.PORT}")

    except KeyboardInterrupt:
        print(f"\n[*] Arrêt demandé, envoi du BYE...")
        try:
            bye_msg = f"BYE {agent_id}\n"
            sock.sendall(bye_msg.encode(config.ENCODING))
            reponse = sock.recv(config.BUFFER_SIZE).decode(config.ENCODING).strip()
            print(f"[←] Serveur : {reponse}")
        except Exception:
            pass

    except Exception as e:
        print(f"[!] Erreur inattendue : {e}")

    finally:
        sock.close()
        print(f"[*] Agent '{agent_id}' arrêté.")


# ============================================================
#  Point d'entrée
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent de monitoring réseau")
    parser.add_argument("--id", required=True, help="Identifiant unique de l'agent (ex: agent1)")
    args = parser.parse_args()

    if " " in args.id:
        print("[!] Erreur : l'identifiant ne doit pas contenir d'espaces")
        sys.exit(1)

    run_agent(args.id)

# ============================================================
#  server.py — Serveur TCP de monitoring multi-clients
# ============================================================

import socket
import threading
import time
import sys
import os

# Import config projet
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import projet

# Import état partagé
from shared_state import agents, agents_lock


# ============================================================
#  Gestion d'un client
# ============================================================
def handle_client(conn, addr):
    agent_id = None
    print(f"[+] Nouvelle connexion : {addr}")

    try:
        while True:
            data = conn.recv(projet.BUFFER_SIZE)
            if not data:
                break

            message = data.decode(projet.ENCODING).strip()
            print(f"[←] {addr} : {message}")

            parts = message.split()
            if not parts:
                conn.sendall(b"ERROR message vide\n")
                continue

            commande = parts[0].upper()

            # HELLO
            if commande == "HELLO":
                if len(parts) != 3:
                    conn.sendall(b"ERROR format: HELLO <agent_id> <hostname>\n")
                    continue

                agent_id = parts[1]
                hostname = parts[2]

                with agents_lock:
                    agents[agent_id] = {
                        "hostname": hostname,
                        "cpu": 0.0,
                        "ram": 0.0,
                        "last_seen": time.time(),
                        "addr": str(addr[0]),
                        "status": "actif"
                    }

                conn.sendall(b"OK\n")
                print(f"[✓] Agent enregistré : {agent_id}")

            # REPORT
            elif commande == "REPORT":
                if len(parts) != 5:
                    conn.sendall(b"ERROR format REPORT\n")
                    continue

                try:
                    aid = parts[1]
                    cpu = float(parts[3])
                    ram = float(parts[4])
                except:
                    conn.sendall(b"ERROR valeurs invalides\n")
                    continue

                with agents_lock:
                    if aid in agents:
                        agents[aid]["cpu"] = cpu
                        agents[aid]["ram"] = ram
                        agents[aid]["last_seen"] = time.time()
                        agents[aid]["status"] = "actif"
                    else:
                        conn.sendall(b"ERROR agent inconnu\n")
                        continue

                conn.sendall(b"OK\n")

            # BYE
            elif commande == "BYE":
                aid = parts[1]
                with agents_lock:
                    if aid in agents:
                        agents[aid]["status"] = "déconnecté"

                conn.sendall(b"OK\n")
                break

            else:
                conn.sendall(b"ERROR commande inconnue\n")

    except Exception as e:
        print(f"[!] Erreur {addr}: {e}")

    finally:
        if agent_id:
            with agents_lock:
                if agent_id in agents:
                    agents[agent_id]["status"] = "déconnecté"
        conn.close()


# ============================================================
#  Vérification des agents inactifs
# ============================================================
def check_inactivity():
    while True:
        time.sleep(projet.STATS_INTERVAL)
        now = time.time()

        with agents_lock:
            for aid, info in agents.items():
                if now - info["last_seen"] > projet.TIMEOUT_AGENT:
                    info["status"] = "inactif"


# ============================================================
#  Serveur principal
# ============================================================
def main():
    print(f"🖥️ Serveur démarré sur {projet.HOST}:{projet.PORT}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((projet.HOST, projet.PORT))
    sock.listen(10)

    threading.Thread(target=check_inactivity, daemon=True).start()

    try:
        while True:
            conn, addr = sock.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

    except KeyboardInterrupt:
        print("Arrêt serveur")

    finally:
        sock.close()


if __name__ == "__main__":
    main()

#  Lance serveur + dashboard dans le MÊME processus
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

def start_server():
    import socket
    import time
    import csv
    import projet
    from shared_state import (
        agents, agents_lock, get_history, compute_health,
        detect_anomaly, check_flood, is_banned, add_event
    )

    def handle_client(conn, addr):
        agent_id = None
        add_event(f"Connexion : {addr}")
        try:
            buffer = ""
            while True:
                data = conn.recv(projet.BUFFER_SIZE)
                if not data:
                    break
                buffer += data.decode(projet.ENCODING)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    message = line.strip()
                    if not message:
                        continue
                    parts    = message.split()
                    commande = parts[0].upper()

                    if commande == "HELLO":
                        if len(parts) != 3:
                            conn.sendall(b"ERROR format HELLO\n"); continue
                        agent_id, hostname = parts[1], parts[2]
                        with agents_lock:
                            agents[agent_id] = {
                                "hostname": hostname, "cpu": 0.0, "ram": 0.0,
                                "last_seen": time.time(), "addr": str(addr[0]),
                                "status": "actif", "latence": 0.0,
                                "health": 100, "anomaly": None,
                            }
                        conn.sendall(b"OK\n")
                        add_event(f"Agent enregistré : {agent_id} ({hostname})")
                        print(f"[✓] Agent enregistré : {agent_id}")

                    elif commande == "REPORT":
                        if len(parts) != 5:
                            conn.sendall(b"ERROR format REPORT\n"); continue
                        aid = parts[1]
                        if is_banned(aid):
                            conn.sendall(b"ERROR banned flood\n"); continue
                        try:
                            ts_agent = float(parts[2])
                            cpu      = float(parts[3])
                            ram      = float(parts[4])
                        except ValueError:
                            conn.sendall(b"ERROR valeurs invalides\n"); continue
                        if not (0 <= cpu <= 100):
                            conn.sendall(b"ERROR cpu hors plage\n"); continue
                        if ram < 0:
                            conn.sendall(b"ERROR ram invalide\n"); continue
                        if check_flood(aid):
                            with agents_lock:
                                if aid in agents:
                                    agents[aid]["status"] = "suspect"
                                    agents[aid]["health"] = 0
                            conn.sendall(b"ERROR flood detected\n")
                            continue
                        now     = time.time()
                        latence = max(0, round((now - ts_agent) * 1000, 1))
                        with agents_lock:
                            if aid not in agents:
                                conn.sendall(b"ERROR agent inconnu\n")
                                continue
                            get_history(aid).append((now, cpu, ram))
                            anomaly = detect_anomaly(aid, cpu, ram)
                            if anomaly:
                                add_event(f"🔴 ANOMALIE {aid} : {anomaly}")
                            agents[aid].update({
                                "cpu": cpu, "ram": ram, "last_seen": now,
                                "latence": latence, "anomaly": anomaly,
                                "status": "suspect" if anomaly else "actif",
                                "health": compute_health(aid),
                            })
                        conn.sendall(b"OK\n")
                        print(f"  [{agent_id}] CPU:{cpu}% RAM:{ram}MB lat:{latence}ms")

                    elif commande == "BYE":
                        aid = parts[1] if len(parts) > 1 else agent_id
                        with agents_lock:
                            if aid in agents:
                                agents[aid]["status"] = "déconnecté"
                                agents[aid]["health"] = None   # exclure du classement
                        conn.sendall(b"OK\n")
                        add_event(f"BYE : {aid}")
                        break
                    else:
                        conn.sendall(b"ERROR commande inconnue\n")
        except Exception as e:
            print(f"[!] Erreur client {addr}: {e}")
        finally:
            if agent_id:
                with agents_lock:
                    if agent_id in agents:
                        agents[agent_id]["status"] = "déconnecté"
                        agents[agent_id]["health"] = None   # exclure du classement
            conn.close()

    def check_inactivity():
        while True:
            time.sleep(projet.STATS_INTERVAL)
            now = time.time()
            with agents_lock:
                for aid, info in agents.items():
                    if info["status"] not in ("déconnecté",) and \
                       now - info["last_seen"] > projet.TIMEOUT_AGENT:
                        if info["status"] != "inactif":
                            add_event(f"⏱ Inactif : {aid}")
                        info["status"] = "inactif"

    def export_csv():
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), projet.CSV_FILE)
        while True:
            time.sleep(projet.STATS_INTERVAL)
            with agents_lock:
                snapshot = {aid: dict(info) for aid, info in agents.items()}
            try:
                besoin_entete = not os.path.isfile(csv_path) or os.path.getsize(csv_path) == 0
                with open(csv_path, "a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    if besoin_entete:
                        w.writerow(["timestamp","agent_id","hostname","cpu","ram","latence","health","status"])
                    ts = time.strftime("%Y-%m-%d %H:%M:%S")
                    for aid, info in snapshot.items():
                        health_val = info.get("health")
                        w.writerow([ts, aid, info["hostname"],
                                    f"{info['cpu']:.1f}", f"{info['ram']:.0f}",
                                    f"{info.get('latence',0):.1f}",
                                    health_val if health_val is not None else "—",
                                    info["status"]])
            except Exception as e:
                print(f"[!] CSV erreur : {e}")

    import socket as sock_mod
    srv = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
    srv.setsockopt(sock_mod.SOL_SOCKET, sock_mod.SO_REUSEADDR, 1)
    srv.bind((projet.HOST, projet.PORT))
    srv.listen(50)
    print(f"🖥️  Serveur démarré sur {projet.HOST}:{projet.PORT}")
    add_event(f"Serveur démarré (port {projet.PORT})")

    threading.Thread(target=check_inactivity, daemon=True).start()
    threading.Thread(target=export_csv,       daemon=True).start()

    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


t = threading.Thread(target=start_server, daemon=True)
t.start()

import time
time.sleep(1)

print("🖥️  Lancement du dashboard serveur ...")
from dashboard import Dashboard
app = Dashboard()
app.mainloop()

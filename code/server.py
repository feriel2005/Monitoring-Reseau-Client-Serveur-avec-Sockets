# Serveur TCP de monitoring multi-clients
import socket
import threading
import time
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__)) #permet dimporter projet.py 
import projet

from shared_state import (
    agents, agents_lock,
    get_history, compute_health, detect_anomaly,
    check_flood, is_banned, add_event, event_log
)#importe les éléments de shared_state pour gérer l'état global du serveur

#  Gestion d'un client
def handle_client(conn, addr): 
    agent_id = None
    print(f"[+] Nouvelle connexion : {addr}")
    add_event(f"Connexion entrante : {addr}")

    try:
        buffer = ""
        while True:
            data = conn.recv(projet.BUFFER_SIZE) #attend des données du client si connexion fermée on sort de la boucle
            if not data:
                break

            buffer += data.decode(projet.ENCODING) #ajoute les données reçues au buffer en les décodant de bytes à str

            # Traiter chaque ligne complète (protocole ligne par ligne)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)#sépare la première ligne complète du reste du buffer
                message = line.strip()
                if not message:
                    continue

                print(f"[←] {addr} : {message}")
                parts    = message.split()
                commande = parts[0].upper() #extrait la commande (HELLO, REPORT, BYE) en majuscules pour comparaison

                #  HELLO <agent_id> <hostname>

                if commande == "HELLO":
                    if len(parts) != 3:
                        conn.sendall(b"ERROR format: HELLO <agent_id> <hostname>\n")
                        continue

                    agent_id = parts[1]
                    hostname = parts[2]

                    with agents_lock:
                        agents[agent_id] = {
                            "hostname": hostname,
                            "cpu":      0.0,
                            "ram":      0.0,
                            "last_seen": time.time(),
                            "addr":     str(addr[0]),
                            "status":   "actif",
                            "latence":  0.0,
                            "health":   100,
                            "anomaly":  None,
                        }#enregistre le nouvel agent dans l'état global avec les infos fournies et des valeurs par défaut pour les stats

                    conn.sendall(b"OK\n")
                    add_event(f"Agent enregistré : {agent_id} ({hostname})")
                    print(f"[✓] Agent enregistré : {agent_id}")
 
                #  REPORT <agent_id> <timestamp> <cpu_pct> <ram_mb>
                
                elif commande == "REPORT":
                    if len(parts) != 5:
                        conn.sendall(b"ERROR format: REPORT <id> <ts> <cpu> <ram>\n")
                        continue

                    aid = parts[1]

                    # Vérification ban flood
                    if is_banned(aid):
                        conn.sendall(b"ERROR banned flood\n")
                        continue

                    # Validation des valeurs
                    try:
                        ts_agent = float(parts[2])
                        cpu      = float(parts[3])
                        ram      = float(parts[4])
                    except ValueError:
                        conn.sendall(b"ERROR valeurs invalides\n")
                        add_event(f"⚠️  Valeurs invalides de {aid}")
                        continue

                    # Validation plages
                    if not (projet.CPU_MIN <= cpu <= projet.CPU_MAX):
                        conn.sendall(b"ERROR cpu hors plage [0-100]\n")
                        add_event(f"⚠️  CPU hors plage de {aid} : {cpu}")
                        continue

                    if not (projet.RAM_MIN <= ram <= projet.RAM_MAX_MB):
                        conn.sendall(b"ERROR ram hors plage\n")
                        add_event(f"⚠️  RAM hors plage de {aid} : {ram}")
                        continue

                    # Détection flood
                    if check_flood(aid):
                        if aid in agents:
                            with agents_lock:#si flood détecté, on marque l'agent comme suspect dans l'état global
                                agents[aid]["status"] = "suspect"
                        conn.sendall(b"ERROR flood detected\n")
                        continue

                    now= time.time()
                    latence = round((now - ts_agent) * 1000, 1) #calcule la latence en ms entre le timestamp du client et le serveur

                    # Valeur de latence anormalement élevée ?
                    if latence < 0:
                        latence = 0.0  # horloge désynchronisée
                    if latence > 10_000:
                        add_event(f"⚠️  Latence critique pour {aid} : {latence:.0f} ms")

                    with agents_lock:#met à jour les infos de l'agent dans l'état global
                        if aid not in agents:
                            conn.sendall(b"ERROR agent inconnu\n")
                            continue

                        # Mise à jour historique avant détection
                        get_history(aid).append((now, cpu, ram))

                        # Détection d'anomalie dynamique
                        anomaly = detect_anomaly(aid, cpu, ram)
                        if anomaly:
                            add_event(f"🔴 ANOMALIE {aid} : {anomaly}")
                            print(f"[!] Anomalie {aid} : {anomaly}")

                        agents[aid]["cpu"] = cpu
                        agents[aid]["ram"] = ram
                        agents[aid]["last_seen"] = now
                        agents[aid]["latence"] = latence
                        agents[aid]["anomaly"] = anomaly
                        agents[aid]["status"] = "suspect" if anomaly else "actif"
                        agents[aid]["health"] = compute_health(aid)

                    conn.sendall(b"OK\n")
                    print(f"[→] REPORT {aid} — CPU:{cpu}% RAM:{ram}MB lat:{latence}ms")
 
                #  BYE <agent_id>
                elif commande == "BYE":
                    if len(parts) < 2:
                        conn.sendall(b"ERROR format: BYE <agent_id>\n")
                        continue

                    aid = parts[1]
                    with agents_lock:
                        if aid in agents:
                            agents[aid]["status"] = "déconnecté"

                    conn.sendall(b"OK\n")
                    add_event(f"Agent déconnecté proprement : {aid}")
                    break

                else:
                    conn.sendall(b"ERROR commande inconnue\n")
                    add_event(f"Commande inconnue de {addr} : {commande}")

    except Exception as e: #attrape toute exception inattendue pour éviter de faire planter le serveur et log l'erreur
        print(f"[!] Erreur {addr}: {e}")
        add_event(f"Erreur client {addr} : {e}")

    finally: #assure la fermeture de la connexion et la mise à jour de l'état de l'agent même en cas d'erreur
        if agent_id:
            with agents_lock:
                if agent_id in agents:
                    agents[agent_id]["status"] = "déconnecté"
        conn.close()
        add_event(f"Connexion fermée : {addr}")

#  Vérification des agents inactifs
def check_inactivity():
    while True:
        time.sleep(projet.STATS_INTERVAL) #vérifie l'inactivité des agents toutes les T secondes
        now = time.time()

        with agents_lock:
            for aid, info in agents.items():
                if info["status"] not in ("déconnecté",) and \
                   now - info["last_seen"] > projet.TIMEOUT_AGENT:
                    if info["status"] != "inactif":
                        add_event(f"⏱️  Agent inactif : {aid}")
                    info["status"] = "inactif"
                    info["health"] = compute_health(aid)

#  Affichage périodique des stats globales dans la console
def print_stats():
    while True:
        time.sleep(projet.STATS_INTERVAL)

        with agents_lock:
            en_ligne = [i for i in agents.values() if i["status"] == "actif"]
            nb_total  = len(agents)

        if en_ligne:
            moy_cpu = sum(a["cpu"] for a in en_ligne) / len(en_ligne)
            moy_ram = sum(a["ram"] for a in en_ligne) / len(en_ligne)
            print(f"\n📊 Stats — Actifs: {len(en_ligne)}/{nb_total} | "
                  f"CPU moy: {moy_cpu:.1f}% | RAM moy: {moy_ram:.0f} MB")
        else:
            print(f"\n📊 Stats — Aucun agent actif ({nb_total} connus)")

#  Export CSV automatique périodique
# chemin absolu pour éviter les problèmes selon d'où on lance le script
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), projet.CSV_FILE)

def export_csv():
    """Écrit les stats courantes dans stats_export.csv toutes les T secondes."""
    while True:
        time.sleep(projet.STATS_INTERVAL)

        with agents_lock:
            snapshot = {aid: dict(info) for aid, info in agents.items()}

        # on vérifie si le fichier existe ET a déjà du contenu AVANT de l'ouvrir
        # (ouvrir en mode "a" crée le fichier s'il n'existe pas -> fausse la vérification)
        besoin_entete = not os.path.isfile(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
        try:
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f) #crée un objet writer pour écrire dans le fichier CSV
                if besoin_entete:
                    writer.writerow(["timestamp", "agent_id", "hostname",
                                     "cpu", "ram", "latence", "health", "status"])
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                for aid, info in snapshot.items():
                    writer.writerow([ts, aid, info["hostname"],
                                     f"{info['cpu']:.1f}", f"{info['ram']:.0f}",
                                     f"{info.get('latence', 0):.1f}",
                                     info.get("health", 100),
                                     info["status"]])
        except Exception as e:
            print(f"[!] Export CSV erreur : {e}")

#  Serveur principal
def main():
    print(f"🖥️  Serveur démarré sur {projet.HOST}:{projet.PORT}")
    print(f"    Anti-flood : {projet.FLOOD_MAX} REPORT/{projet.FLOOD_WINDOW}s")
    print(f"    Export CSV : {CSV_PATH}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #crée un socket TCP pour écouter les connexions entrantes
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)#permet de réutiliser l'adresse et le port immédiatement après un redémarrage du serveur
    sock.bind((projet.HOST, projet.PORT))#lie le socket à l'adresse et au port spécifiés dans projet.py
    sock.listen(50)   # file d'attente plus grande pour les tests flood

    threading.Thread(target=check_inactivity,daemon=True).start() #lance le thread de vérification d'inactivité des agents en arrière-plan
    threading.Thread(target=print_stats,daemon=True).start() #lance le thread d'affichage périodique des stats globales dans la console en arrière-plan
    threading.Thread(target=export_csv,daemon=True).start() #lance le thread d'export périodique des stats dans un fichier CSV en arrière-plan

    add_event("Serveur démarré")
    try:
        while True:
            conn, addr = sock.accept() #attend une connexion entrante et accepte la connexion, renvoyant un nouveau socket pour communiquer avec le client et l'adresse du client
            threading.Thread(target=handle_client,
                             args=(conn, addr), daemon=True).start()

    except KeyboardInterrupt: #permet d'arrêter le serveur avec Ctrl+c
        print("\n[*] Arrêt serveur")

    finally:
        sock.close()

if __name__ == "__main__":
    main()

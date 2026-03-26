# ============================================================
#  server.py — Serveur TCP de monitoring multi-clients
# ============================================================

import socket
import threading
import time
import sys+
import os

# Permettre l'import de projet.py depuis le dossier parent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import projet

# ============================================================
#  Stockage partagé des agents (accès depuis plusieurs threads)
# ============================================================
agents = {}          # { agent_id: { hostname, cpu, ram, last_seen } }
agents_lock = threading.Lock()  # Verrou pour éviter les conflits entre threads


# ============================================================
#  Gestion d'un client (tourne dans son propre thread)
# ============================================================
def handle_client(conn, addr):
    agent_id = None
    print(f"[+] Nouvelle connexion : {addr}")

    try:
        while True:
            data = conn.recv(projet.BUFFER_SIZE)
            if not data:
                break  # Le client s'est déconnecté

            message = data.decode(projet.ENCODING).strip()
            print(f"[←] {addr} : {message}")

            parts = message.split()
            if not parts:
                conn.sendall(b"ERROR message vide\n")
                continue

            commande = parts[0].upper()

            # --- HELLO <agent_id> <hostname> ---
            if commande == "HELLO":
                if len(parts) != 3:
                    conn.sendall(b"ERROR format: HELLO <agent_id> <hostname>\n")
                    continue
                agent_id = parts[1]
                hostname = parts[2]

                # Vérification : pas d'espaces dans agent_id (déjà garanti par split)
                with agents_lock:
                    agents[agent_id] = {
                        "hostname":  hostname,
                        "cpu":       0.0,
                        "ram":       0.0,
                        "last_seen": time.time(),
                        "addr":      str(addr)
                    }

                conn.sendall(b"OK\n")
                print(f"[✓] Agent enregistré : {agent_id} ({hostname})")

            # --- REPORT <agent_id> <timestamp> <cpu_pct> <ram_mb> ---
            elif commande == "REPORT":
                if len(parts) != 5:
                    conn.sendall(b"ERROR format: REPORT <agent_id> <timestamp> <cpu_pct> <ram_mb>\n")
                    continue

                rep_agent_id = parts[1]

                try:
                    timestamp = float(parts[2])
                    cpu_pct   = float(parts[3])
                    ram_mb    = float(parts[4])
                except ValueError:
                    conn.sendall(b"ERROR valeurs numeriques invalides\n")
                    continue

                # Validation des valeurs
                if not (0 <= cpu_pct <= 100):
                    conn.sendall(b"ERROR cpu_pct doit etre entre 0 et 100\n")
                    continue
                if ram_mb < 0:
                    conn.sendall(b"ERROR ram_mb doit etre >= 0\n")
                    continue

                with agents_lock:
                    if rep_agent_id in agents:
                        agents[rep_agent_id]["cpu"]       = cpu_pct
                        agents[rep_agent_id]["ram"]       = ram_mb
                        agents[rep_agent_id]["last_seen"] = time.time()
                    else:
                        conn.sendall(b"ERROR agent non enregistre, envoie HELLO d'abord\n")
                        continue

                conn.sendall(b"OK\n")

                # Alerte CPU
                if cpu_pct > projet.CPU_ALERT_THRESHOLD:
                    print(f"[⚠️  ALERTE] {rep_agent_id} : CPU élevé → {cpu_pct}%")

            # --- BYE <agent_id> ---
            elif commande == "BYE":
                if len(parts) != 2:
                    conn.sendall(b"ERROR format: BYE <agent_id>\n")
                    continue

                bye_agent_id = parts[1]
                with agents_lock:
                    if bye_agent_id in agents:
                        del agents[bye_agent_id]
                        print(f"[-] Agent déconnecté proprement : {bye_agent_id}")

                conn.sendall(b"OK\n")
                break  # Fermer la connexion

            else:
                conn.sendall(f"ERROR commande inconnue: {commande}\n".encode(projet.ENCODING))

    except ConnectionResetError:
        print(f"[!] Connexion perdue brutalement : {addr}")
    except Exception as e:
        print(f"[!] Erreur inattendue avec {addr} : {e}")
    finally:
        # Nettoyage : retirer l'agent si pas déjà fait (déconnexion brutale)
        if agent_id:
            with agents_lock:
                if agent_id in agents:
                    del agents[agent_id]
                    print(f"[-] Agent retiré (déconnexion) : {agent_id}")
        conn.close()


# ============================================================
#  Thread qui affiche les stats globales toutes les T secondes
# ============================================================
def afficher_stats():
    while True:
        time.sleep(projet.STATS_INTERVAL)
        now = time.time()

       ''' with agents_lock:
            # Retirer les agents inactifs (aucun REPORT depuis 3×T secondes)
            inactifs = [
                aid for aid, info in agents.items()
                if now - info["last_seen"] > projet.TIMEOUT_AGENT
            ]
            for aid in inactifs:
                print(f"[⏱️] Agent timeout (inactif) : {aid}")
                del agents[aid]
'''
            actifs = list(agents.values())
        #faire tableau de stats globales
        nb = len(actifs)
        if nb == 0:
            print(f"\n{'='*45}")
            print(f"  📊 Stats — Aucun agent connecté")
            print(f"{'='*45}\n")
        else:
            moy_cpu = sum(a["cpu"] for a in actifs) / nb
            moy_ram = sum(a["ram"] for a in actifs) / nb
            print(f"\n{'='*45}")
            print(f"  📊 Stats globales ({nb} agent(s) actif(s))")
            print(f"  CPU moyen  : {moy_cpu:.1f}%")
            print(f"  RAM moyenne: {moy_ram:.1f} MB")
            print(f"{'='*45}")
            for aid, info in agents.items():
                print(f"  • {aid} ({info['hostname']}) — CPU: {info['cpu']}% | RAM: {info['ram']} MB")
            print()


# ============================================================
#  Point d'entrée principal
# ============================================================
def main():
    print(f"🖥️  Serveur de monitoring démarré sur {projet.HOST}:{projet.PORT}")
    print(f"   Intervalle stats : {projet.STATS_INTERVAL}s | Timeout agent : {projet.TIMEOUT_AGENT}s")
    print(f"   En attente de connexions...\n")

    # Lancer le thread d'affichage des stats
    stats_thread = threading.Thread(target=afficher_stats, daemon=True)
    stats_thread.start()

    # Créer le socket serveur
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Réutiliser le port
    server_sock.bind((projet.HOST, projet.PORT))
    server_sock.listen(10)  # Jusqu'à 10 connexions en attente

    try:
        while True:
            conn, addr = server_sock.accept()
            # Chaque client dans son propre thread
            client_thread = threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True
            )
            client_thread.start()

    except KeyboardInterrupt:
        print("\n[!] Arrêt du serveur (Ctrl+C)")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
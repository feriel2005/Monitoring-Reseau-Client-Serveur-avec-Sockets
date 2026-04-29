# Simulateur d'attaque flood + fausses données
# Chaque exécution choisit un port libre → dashboard isolé
# Il suffit de faire RUN sur ce fichier

import socket
import time
import sys
import os
import subprocess
import random

sys.path.insert(0, os.path.dirname(__file__))

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PYTHON  = sys.executable


def port_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] [ATTACKER] {msg}")


# ── Le port est déterminé une fois pour toute la session ──────────────────────
# Si un serveur tourne déjà sur le port par défaut on le réutilise,
# sinon on en choisit un nouveau et on lance un serveur frais.

import projet  # chargé après os.environ potentiellement défini plus bas


def serveur_actif(port: int) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return True
    except Exception:
        return False


def connect(attacker_id: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", port))
    hello = f"HELLO {attacker_id} fake-machine\n"
    sock.sendall(hello.encode("utf-8"))
    resp = sock.recv(4096).decode("utf-8").strip()
    log(f"HELLO → {resp}")
    return sock


def attack_flood(attacker_id: str, port: int, count: int = 300):
    log(f"Démarrage FLOOD : {count} REPORT rapides...")
    try:
        sock = connect(attacker_id, port)
    except Exception as e:
        log(f"Connexion échouée : {e}"); return

    sent = refused = 0
    start = time.time()
    for i in range(count):
        try:
            ts  = time.time()
            cpu = round(random.uniform(0, 100), 1)
            ram = round(random.uniform(100, 8192), 1)
            msg = f"REPORT {attacker_id} {ts} {cpu} {ram}\n"
            sock.sendall(msg.encode("utf-8"))
            resp = sock.recv(4096).decode("utf-8").strip()
            if resp == "OK":
                sent += 1
            else:
                refused += 1
                if "banned" in resp:
                    log("Banni ! Flood stoppé.")
                    break
            time.sleep(0.005)
        except Exception as e:
            log(f"Erreur : {e}"); break

    elapsed = time.time() - start
    log(f"Flood terminé : {sent} acceptés, {refused} refusés en {elapsed:.2f}s")
    sock.close()


def attack_fake(attacker_id: str, port: int):
    fakes = [
        (999.9, 999999), (-5.0, 2048), (50.0, -100),
        (101.0, 4096),   ("abc", "xyz"), (0.0, 0.0),
    ]
    log("Démarrage envoi FAUSSES DONNÉES...")
    try:
        sock = connect(attacker_id, port)
    except Exception as e:
        log(f"Connexion échouée : {e}"); return

    for cpu, ram in fakes:
        ts  = time.time()
        msg = f"REPORT {attacker_id} {ts} {cpu} {ram}\n"
        sock.sendall(msg.encode("utf-8"))
        resp = sock.recv(4096).decode("utf-8").strip()
        log(f"Envoyé cpu={cpu} ram={ram} → {resp}")
        time.sleep(0.2)

    sock.close()
    log("Attaque fake terminée.")


if __name__ == "__main__":
    print("=" * 45)
    print("  NETWORK MONITOR — Simulateur d'attaque")
    print("=" * 45)

    # Choisir le port : nouveau port + nouveau serveur à chaque run
    port = port_libre()
    os.environ["MONITOR_PORT"] = str(port)
    # Recharger projet pour que SERVER_IP/PORT soient à jour dans ce process
    import importlib
    importlib.reload(projet)

    log(f"Lancement d'un serveur frais sur le port {port}...")
    commande = f'"{PYTHON}" "{os.path.join(DOSSIER, "main.py")}"'
    subprocess.Popen(
        f'start "SERVEUR + DASHBOARD (port {port})" cmd /k "SET MONITOR_PORT={port} && {commande}"',
        shell=True, cwd=DOSSIER
    )
    log("Attente 4s que le serveur démarre...")
    time.sleep(4)

    print("\nChoisir le mode :")
    print("  1 → Flood (spam REPORT)")
    print("  2 → Fake  (fausses données)")
    print("  3 → Les deux")
    choix = input("\nTon choix (1/2/3) [défaut=3] : ").strip() or "3"

    if choix in ("1", "3"):
        attack_flood("attacker_flood", port, count=300)

    if choix in ("2", "3"):
        attack_fake("attacker_fake", port)

    print("\n✅ Simulation terminée. Regarde le dashboard !")
    input("Appuie sur Entrée pour fermer...")

# Test : arrêt brutal d'un client (sans envoyer BYE)
# Chaque exécution choisit un port libre → dashboard isolé
# Il suffit de faire RUN sur ce fichier

import socket
import time
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PYTHON  = sys.executable


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def port_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def serveur_actif(port: int) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return True
    except Exception:
        return False


def ouvrir_cmd(titre, script, args="", port=9999):
    cmd = f'"{PYTHON}" "{os.path.join(DOSSIER, script)}" {args}'
    subprocess.Popen(
        f'start "{titre}" cmd /k "SET MONITOR_PORT={port} && {cmd}"',
        shell=True, cwd=DOSSIER
    )


# Choisir un port libre et lancer un serveur frais
port = port_libre()
os.environ["MONITOR_PORT"] = str(port)

import projet
import importlib
importlib.reload(projet)

log(f"Lancement d'un serveur frais sur le port {port}...")
ouvrir_cmd("SERVEUR + DASHBOARD", "main.py", port=port)
log("Attente 4s...")
time.sleep(4)

print()
print("=" * 50)
print("  TEST — Arrêt brutal d'un client (sans BYE)")
print("=" * 50)
print()

log("Connexion de brutus_agent...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("127.0.0.1", port))

sock.sendall(f"HELLO brutus_agent TEST-MACHINE\n".encode("utf-8"))
rep = sock.recv(4096).decode().strip()
log(f"HELLO → {rep}")

for i in range(2):
    time.sleep(1)
    ts = time.time()
    sock.sendall(f"REPORT brutus_agent {ts} 30.0 2048\n".encode("utf-8"))
    rep = sock.recv(4096).decode().strip()
    log(f"REPORT {i+1} → {rep}")

log("Fermeture brutale du socket (sans BYE)...")
sock.close()

log("Socket fermé. Le serveur devrait détecter la déconnexion dans les prochaines secondes.")
log(f"Après {projet.TIMEOUT_AGENT}s sans REPORT, l'agent passera 'inactif' dans le dashboard.")
print()
log("✅ Test terminé — vérifie dans le dashboard que brutus_agent est marqué déconnecté/inactif")
print()
input("Appuie sur Entrée pour fermer...")

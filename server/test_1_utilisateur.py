# Lance main.py + 1 agent automatiquement
# Chaque exécution choisit un port libre → dashboard isolé
# Il suffit de faire RUN sur ce fichier !

import subprocess
import sys
import time
import os
import socket

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PYTHON  = sys.executable


def port_libre() -> int:
    """Trouve un port TCP libre sur la machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def ouvrir_cmd(titre, script, args="", port=9999):
    """Ouvre un cmd Windows avec le script lancé dans son propre env (port injecté)."""
    commande = f'"{PYTHON}" "{os.path.join(DOSSIER, script)}" {args}'
    # SET MONITOR_PORT avant de lancer le script pour que projet.py récupère le bon port
    full = f'start "{titre}" cmd /k "SET MONITOR_PORT={port} && {commande}"'
    subprocess.Popen(full, shell=True, cwd=DOSSIER)


print("=" * 45)
print(" NETWORK MONITOR — Test 1 agent")
print("=" * 45)

port = port_libre()
print(f"\n   Port choisi automatiquement : {port}")

print("\n[1] Lancement serveur + dashboard (main.py)...")
ouvrir_cmd("SERVEUR + DASHBOARD", "main.py", port=port)

print("      Attente 3s que le serveur démarre...")
time.sleep(3)

print("[2/2] Lancement agent1...")
ouvrir_cmd("AGENT — agent1", "agent.py", f"--id agent1", port=port)

print("\n✅ Tout est lancé !")
print(f"   → Dashboard sur le port {port}. agent1 apparaît dans 5s.")

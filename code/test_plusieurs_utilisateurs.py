# Lance main.py + 5 agents automatiquement
# Chaque exécution choisit un port libre → dashboard isolé
# Il suffit de faire RUN sur ce fichier !

import subprocess
import sys
import time
import os
import socket

DOSSIER   = os.path.dirname(os.path.abspath(__file__))
PYTHON    = sys.executable
NB_AGENTS = 5


def port_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def ouvrir_cmd(titre, script, args="", port=9999):
    commande = f'"{PYTHON}" "{os.path.join(DOSSIER, script)}" {args}'
    full = f'start "{titre}" cmd /k "SET MONITOR_PORT={port} && {commande}"'
    subprocess.Popen(full, shell=True, cwd=DOSSIER)


print("=" * 45)
print(f"  NETWORK MONITOR — {NB_AGENTS} agents")
print("=" * 45)

port = port_libre()
print(f"\n   Port choisi automatiquement : {port}")

print("\n[1] Lancement serveur + dashboard (main.py)...")
ouvrir_cmd("SERVEUR + DASHBOARD", "main.py", port=port)

print("    Attente 3s que le serveur démarre...")
time.sleep(3)

print(f"[2] Lancement de {NB_AGENTS} agents...")
for i in range(1, NB_AGENTS + 1):
    ouvrir_cmd(f"AGENT — agent{i}", "agent.py", f"--id agent{i}", port=port)
    print(f"    ✓ agent{i} lancé")
    time.sleep(1)

print("\n✅ Tout est lancé !")
print(f"   → {NB_AGENTS} agents actifs dans le dashboard (port {port}) dans quelques secondes.")

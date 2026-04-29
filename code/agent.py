#Client TCP
import socket
import time
import sys #pour modifier les chemins et quitter avec sys.exit()
import os #pour construire les chemins de fichiers
import argparse #pour lire les arguments de la ligne de commande 
import uuid #génère des UUID uniques

sys.path.insert(0, os.path.dirname(__file__)) #ajoute le dossier courant au chemin Python pour que import projet trouve le fichier projet.py
import projet

try:
    import psutil # lit les stats CPU et RAM
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False #on simulera des val réalistes sur windows

#Journal local : events et erreurs de l'agent
def log(msg: str):# affiche message avec heure acutelle
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

# Lecture CPU et RAM
def lire_cpu():
    if PSUTIL_AVAILABLE:
        return psutil.cpu_percent(interval=0.5)
    import random    #val simulées réalistes
    return round(random.uniform(5.0, 45.0), 1)
def lire_ram():
    if PSUTIL_AVAILABLE:
        return round(psutil.virtual_memory().used / 1024 / 1024, 1)#en MB
    import random
    return round(random.uniform(2000, 6000), 1)

#  Fonction agent
def run_agent(agent_id: str):
    hostname = socket.gethostname() #pour info dans le dashboard
    log(f"Agent '{agent_id}' démarré sur {hostname}")
    log(f"UUID session : {uuid.uuid4()}")
    log(f"Connexion vers {projet.SERVER_IP}:{projet.PORT}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #crée un socket TCP avec AF_INET = IPv4, SOCK_STREAM = TCP

    try:
        sock.connect((projet.SERVER_IP, projet.PORT))
        log("✓ Connecté au serveur")
        
        # Enregistrement
        hello_msg = f"HELLO {agent_id} {hostname}\n" 
        sock.sendall(hello_msg.encode(projet.ENCODING)) #Envoie le HELLO au serveur encodé en bytes UTF-8

        reponse = sock.recv(projet.BUFFER_SIZE).decode(projet.ENCODING).strip() #attend la réponse du serveur OK ou ERROR

        log(f"← Serveur : {reponse}")

        if reponse != "OK":
            log(f"Enregistrement refusé : {reponse}")
            return

        log(f"Envoi de rapports toutes les {projet.T}s. Ctrl+C pour arrêter.")

        while True: #'agent envoie des rapports indéfiniment jusqu'à Ctrl+C
            time.sleep(projet.T)

            cpu = lire_cpu()
            ram = lire_ram()
            ts  = time.time()

            # Validation locale avant envoi
            if not (projet.CPU_MIN <= cpu <= projet.CPU_MAX):
                log(f"⚠ CPU hors plage ({cpu}) — REPORT non envoyé")
                continue
            if ram < projet.RAM_MIN:
                log(f"⚠ RAM invalide ({ram}) — REPORT non envoyé")
                continue

            report_msg = f"REPORT {agent_id} {ts} {cpu} {ram}\n"
            sock.sendall(report_msg.encode(projet.ENCODING)) #envoie le REPORT au serveur
            log(f"→ REPORT envoyé — CPU: {cpu}% | RAM: {ram} MB")

            reponse = sock.recv(projet.BUFFER_SIZE).decode(projet.ENCODING).strip()
            if reponse == "OK":
                pass  # tout va bien
            elif "banned" in reponse:
                log("🚨 Serveur : banni pour flood — attente avant reconnexion")
                time.sleep(projet.FLOOD_BAN_TIME)
            else:
                log(f"⚠ Erreur serveur : {reponse}")

    except ConnectionRefusedError: 
        log(f"Impossible de se connecter : serveur injoignable sur "
            f"{projet.SERVER_IP}:{projet.PORT}")

    except KeyboardInterrupt: #attrape Ctrl+C
        log("Arrêt demandé — envoi du BYE...")
        try:
            bye_msg = f"BYE {agent_id}\n"
            sock.sendall(bye_msg.encode(projet.ENCODING))
            reponse = sock.recv(projet.BUFFER_SIZE).decode(projet.ENCODING).strip()
            log(f"← Serveur : {reponse}")
        except Exception: #le serveur déjà mort au moment du BYE
            pass

    except Exception as e:
        log(f"Erreur inattendue : {e}")

    finally:
        sock.close() #ferme le socket dans tous les cas
        log(f"Agent '{agent_id}' arrêté.")

#  Point d'entrée
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent de monitoring réseau") #crée le parseur d'arguments pour la ligne de commande
    parser.add_argument(
        "--id",
        default=f"agent_{uuid.uuid4().hex[:6]}",   # UUID court auto si non fourni
        help="Identifiant unique de l'agent (ex: agent1). Auto-généré si absent."
    )   
    args = parser.parse_args() # lit les arguments passés en ligne de commande

    if " " in args.id:
        print("[!] Erreur : l'identifiant ne doit pas contenir d'espaces")
        sys.exit(1)

    run_agent(args.id) #lance l'agent avec l'identifiant fourni ou auto-généré

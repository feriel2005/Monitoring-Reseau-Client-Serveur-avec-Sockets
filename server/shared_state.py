# ============================================================
#  shared_state.py — Données partagées entre serveur et UI
# ============================================================

import threading

# Dictionnaire global des agents
agents = {}

# Verrou pour accès thread-safe
agents_lock = threading.Lock()

#  Interface "Terminal Hacker" temps réel

import tkinter as tk
from tkinter import ttk, messagebox
import time
import csv
import os
from collections import deque

from shared_state import agents, agents_lock, event_log
import projet

# Palette "terminal hacker"
BG       = "#0d0d0d"
FG       = "#00ff41"
FG2      = "#00cc33"
FG_WARN  = "#ffcc00"
FG_CRIT  = "#ff3333"
FG_OK    = "#00ff41"
FG_INFO  = "#00aaff"
FONT_M   = ("Courier New", 10)
FONT_B   = ("Courier New", 10, "bold")
FONT_T   = ("Courier New", 13, "bold")
FONT_S   = ("Courier New", 9)

GRAPH_W  = 420
GRAPH_H  = 120
GRAPH_PT = 40


def color_for_status(status: str) -> str:
    return {
        "actif":       FG_OK,
        "suspect":     FG_WARN,
        "inactif":     FG_CRIT,
        "déconnecté":  "#888888",
    }.get(status, FG)


def color_for_score(score) -> str:
    if score is None:
        return "#888888"
    if score >= 75:
        return FG_OK
    elif score >= 40:
        return FG_WARN
    return FG_CRIT


def label_score(score) -> str:
    if score is None:
        return "—"
    if score >= 75:
        return "OK"
    elif score >= 40:
        return "WARNING"
    return "CRITICAL"


class MiniGraph(tk.Canvas):
    def __init__(self, parent, label: str, color: str, max_val: float = 100, **kw):
        super().__init__(parent, width=GRAPH_W, height=GRAPH_H,
                         bg=BG, highlightthickness=2,
                         highlightbackground="#005500", **kw)
        self.label    = label
        self.color    = color
        self.max_val  = max_val   # hint de départ, recalculé dynamiquement
        self.data     = deque([0.0] * GRAPH_PT, maxlen=GRAPH_PT)

    def push(self, val: float):
        self.data.append(val)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = GRAPH_W, GRAPH_H
        pts  = list(self.data)
        n    = len(pts)

        # ── Echelle dynamique : le plafond est toujours >= max des données ──
        data_max = max(pts) if pts else 0
        # Pour CPU on garde 100 comme plafond minimum ; pour RAM on s'adapte
        effective_max = max(self.max_val, data_max * 1.10, 1)  # +10 % de marge

        # ── Grille : 5 lignes horizontales équidistantes avec labels ─────────
        NB_LINES = 5
        for i in range(1, NB_LINES + 1):
            frac      = i / (NB_LINES + 1)          # 1/6 … 5/6
            y         = h - int(h * frac)
            threshold = effective_max * frac
            # ligne de grille
            self.create_line(0, y, w, y, fill="#004400", dash=(3, 5))
            # label de seuil (coin gauche, légèrement au-dessus de la ligne)
            if threshold >= 1000:
                lbl = f"{threshold/1000:.1f}k"
            else:
                lbl = f"{threshold:.0f}"
            self.create_text(3, y - 1, anchor="sw", text=lbl,
                             fill="#006600", font=("Courier New", 7))

        # ── Bordure interne nette ─────────────────────────────────────────────
        self.create_rectangle(0, 0, w - 1, h - 1,
                              outline="#005500", width=1)

        # ── Courbe ───────────────────────────────────────────────────────────
        if n > 1:
            coords = []
            for i, v in enumerate(pts):
                x = int(w * i / (n - 1))
                y = h - int(h * v / effective_max)
                y = max(1, min(h - 1, y))           # clamp dans le canvas
                coords += [x, y]
            self.create_line(*coords, fill=self.color, width=2, smooth=True)

        # ── Label titre + valeur courante ─────────────────────────────────────
        val = pts[-1] if pts else 0
        self.create_text(4, 4, anchor="nw", text=self.label,
                         fill=self.color, font=FONT_S)
        self.create_text(w - 4, 4, anchor="ne",
                         text=f"{val:.1f}",
                         fill=self.color, font=FONT_S)


class AgentPanel(tk.Frame):
    def __init__(self, parent, agent_id: str, **kw):
        super().__init__(parent, bg=BG, bd=1, relief="solid", **kw)
        self.agent_id = agent_id

        self.lbl_title = tk.Label(self, text=f"[ {agent_id} ]",
                                  bg=BG, fg=FG, font=FONT_T)
        self.lbl_title.grid(row=0, column=0, columnspan=2,
                             sticky="w", padx=8, pady=(6, 2))

        self.lbl_info = tk.Label(self, text="", bg=BG, fg=FG2,
                                 font=FONT_S, justify="left")
        self.lbl_info.grid(row=1, column=0, columnspan=2,
                            sticky="w", padx=8, pady=2)

        self.lbl_health = tk.Label(self, text="HEALTH: 100 [OK]",
                                   bg=BG, fg=FG_OK, font=FONT_B)
        self.lbl_health.grid(row=2, column=0, columnspan=2,
                              sticky="w", padx=8, pady=2)

        self.lbl_anomaly = tk.Label(self, text="", bg=BG,
                                    fg=FG_WARN, font=FONT_S)
        self.lbl_anomaly.grid(row=3, column=0, columnspan=2,
                               sticky="w", padx=8, pady=2)

        self.graph_cpu = MiniGraph(self, "CPU %", FG_OK, max_val=100)
        self.graph_cpu.grid(row=4, column=0, padx=8, pady=4)

        self.graph_ram = MiniGraph(self, "RAM MB", FG_INFO, max_val=8192)
        self.graph_ram.grid(row=4, column=1, padx=8, pady=4)

    def update_data(self, info: dict):
        status  = info["status"]
        color_s = color_for_status(status)
        score   = info.get("health")
        color_h = color_for_score(score)
        anomaly = info.get("anomaly")
        latence = info.get("latence", 0.0)

        self.lbl_title.config(fg=color_s)
        self.lbl_info.config(
            text=(f"Host: {info['hostname']}  |  IP: {info['addr']}  |  "
                  f"Status: {status}  |  Latence: {latence:.1f} ms")
        )

        # Affichage du health score (None = déconnecté, pas de score)
        if score is None:
            self.lbl_health.config(text="HEALTH:  — [déconnecté]", fg="#888888")
        else:
            self.lbl_health.config(
                text=f"HEALTH: {score:3d}  [{label_score(score)}]",
                fg=color_h
            )

        if anomaly:
            self.lbl_anomaly.config(text=f"⚠ {anomaly}", fg=FG_WARN)
        else:
            self.lbl_anomaly.config(text="")

        self.graph_cpu.push(info["cpu"])
        # hint max_val : pic historique × 1.15 pour éviter les rescales brusques
        # _draw() s'auto-ajuste de toute façon via effective_max
        ram_peak = max(self.graph_ram.data) if self.graph_ram.data else info["ram"]
        self.graph_ram.max_val = max(ram_peak * 1.15, info["ram"] * 1.15, 512)
        self.graph_ram.push(info["ram"])


class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"DASHBOARD SERVEUR — port {projet.PORT}")
        self.geometry("1280x820")
        self.configure(bg=BG)

        self._agent_panels: dict[str, AgentPanel] = {}
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=6)

        tk.Label(top, text=f"◈ Monitoring Réseau  [port {projet.PORT}] ◈",
                 bg=BG, fg=FG, font=("Courier New", 14, "bold")).pack(side="left")

        self.lbl_clock = tk.Label(top, text="", bg=BG, fg=FG2, font=FONT_M)
        self.lbl_clock.pack(side="right")

        tk.Button(top, text="[ EXPORT CSV ]",
                  bg="#001a00", fg=FG, font=FONT_B,
                  relief="flat", cursor="hand2",
                  command=self._export_csv).pack(side="right", padx=10)

        self.lbl_stats = tk.Label(self, text="",
                                  bg=BG, fg=FG_INFO, font=FONT_M)
        self.lbl_stats.pack(fill="x", padx=10, pady=2)

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=10, pady=4)

        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="▶ AGENTS", bg=BG, fg=FG, font=FONT_B).pack(anchor="w")

        canvas_frame = tk.Frame(left, bg=BG)
        canvas_frame.pack(fill="both", expand=True)

        self._canvas  = tk.Canvas(canvas_frame, bg=BG, highlightthickness=0)
        scrollbar     = tk.Scrollbar(canvas_frame, orient="vertical",
                                     command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._agents_frame = tk.Frame(self._canvas, bg=BG)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._agents_frame, anchor="nw")
        self._agents_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>",       self._on_canvas_configure)

        # Classement (agents connectés uniquement)
        right = tk.Frame(main, bg=BG, width=260)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        tk.Label(right, text="▶ CLASSEMENT (connectés)",
                 bg=BG, fg=FG, font=FONT_B).pack(anchor="w", pady=(0, 4))

        self.rank_text = tk.Text(right, bg="#060606", fg=FG,
                                  font=FONT_S, relief="flat",
                                  state="disabled", width=30)
        self.rank_text.pack(fill="both", expand=True)

        bottom = tk.Frame(self, bg=BG, height=160)
        bottom.pack(fill="x", padx=10, pady=(4, 8))
        bottom.pack_propagate(False)

        tk.Label(bottom, text="▶ JOURNAL D'ÉVÉNEMENTS",
                 bg=BG, fg=FG, font=FONT_B).pack(anchor="w")

        self.log_text = tk.Text(bottom, bg="#060606", fg=FG2,
                                 font=FONT_S, relief="flat",
                                 state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _on_frame_configure(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _refresh(self):
        self.lbl_clock.config(text=time.strftime("%H:%M:%S"))

        with agents_lock:
            snap = {aid: dict(info) for aid, info in agents.items()}

        en_ligne = [i for i in snap.values() if i["status"] == "actif"]
        suspects = [i for i in snap.values() if i["status"] == "suspect"]

        moy_cpu = (sum(a["cpu"] for a in en_ligne) / len(en_ligne)) if en_ligne else 0
        moy_ram = (sum(a["ram"] for a in en_ligne) / len(en_ligne)) if en_ligne else 0

        self.lbl_stats.config(
            text=(f"Agents actifs: {len(en_ligne)}/{len(snap)}  |  "
                  f"Suspects: {len(suspects)}  |  "
                  f"CPU moy: {moy_cpu:.1f}%  |  "
                  f"RAM moy: {moy_ram:.0f} MB")
        )

        for aid, info in snap.items():
            if aid not in self._agent_panels:
                panel = AgentPanel(self._agents_frame, aid)
                panel.pack(fill="x", padx=4, pady=4)
                self._agent_panels[aid] = panel
            self._agent_panels[aid].update_data(info)

        # Classement : EXCLURE les agents déconnectés (health == None)
        classement = [
            (aid, info) for aid, info in snap.items()
            if info.get("health") is not None          # exclut les déconnectés
        ]
        classement.sort(key=lambda x: x[1].get("health", 0), reverse=True)

        self.rank_text.config(state="normal")
        self.rank_text.delete("1.0", "end")
        if classement:
            for rang, (aid, info) in enumerate(classement, 1):
                pts   = info.get("health", 0)
                lbl   = label_score(pts)
                ligne = f" {rang:2}. {aid:<14} {pts:3d}  [{lbl}]\n"
                self.rank_text.insert("end", ligne)
        else:
            self.rank_text.insert("end", " Aucun agent connecté\n")
        self.rank_text.config(state="disabled")

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        for entree in list(event_log)[:30]:
            self.log_text.insert("end", entree + "\n")
        self.log_text.config(state="disabled")

        self.after(1000, self._refresh)

    def _export_csv(self):
        with agents_lock:
            snapshot = {aid: dict(info) for aid, info in agents.items()}

        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, projet.CSV_FILE)

        besoin_entete = not os.path.isfile(path) or os.path.getsize(path) == 0
        try:
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if besoin_entete:
                    writer.writerow(["timestamp", "agent_id", "hostname",
                                      "cpu", "ram", "latence", "health", "status"])
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                for aid, info in snapshot.items():
                    health_val = info.get("health")
                    writer.writerow([ts, aid, info["hostname"],
                                     f"{info['cpu']:.1f}", f"{info['ram']:.0f}",
                                     f"{info.get('latence', 0):.1f}",
                                     health_val if health_val is not None else "—",
                                     info["status"]])
            messagebox.showinfo("Export CSV", f"Données ajoutées dans :\n{path}")
        except Exception as e:
            messagebox.showerror("Erreur export", str(e))

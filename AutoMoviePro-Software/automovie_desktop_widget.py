"""
=============================================================================
AutoMovie Pro - Companion Desktop HUD Widget
=============================================================================
Industrial-Grade Cyber Companion Desktop Widget:
- Persistent floating HUD window that stays active even if main app is minimized or closed.
- Zero taskbar clutter (WS_EX_TOOLWINDOW style).
- Real-time display of:
    1. বর্তমান কার্যক্রম (Current Activity: Task, Stage, Progress %, Channel & Niche).
    2. পরবর্তী কার্যক্রমসমূহ (Upcoming Activities: Next Slot, Live Countdown, Platform, Topic).
    3. সিস্টেম ও প্রোডাকশন স্বাস্থ্য (Engine status, Videos created today, CPU %, RAM %).
- Quick Action Deck:
    [🚀 ড্যাশবোর্ড খুলুন] (Instantly restores or opens main native desktop window)
    [⚡ ১-ক্লিক ভিডিও তৈরি] (Triggers instant video creation)
    [⏸️ শিডিউল পজ / চালু] (Toggles automation scheduler)
- Non-blocking daemon thread with smooth 2-second telemetry polling.
=============================================================================
"""

from __future__ import annotations

import os
import sys
import json
import time
import ctypes
import urllib.request
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
from PIL import Image, ImageTk

# Pythonw clean standard streams
LOG_DIR = Path(__file__).resolve().parent / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
WIDGET_LOG = LOG_DIR / "widget_stdout.log"

if sys.stdout is None:
    try:
        sys.stdout = open(WIDGET_LOG, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
else:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr is None:
    try:
        sys.stderr = open(WIDGET_LOG, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
else:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Windows High DPI awareness
try:
    if sys.platform == "win32":
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent
ICON_FILE = ROOT_DIR / "app_icon.ico"
LOGO_PNG = ROOT_DIR / "ui" / "static" / "img" / "logo-sm.png"
PID_FILE = ROOT_DIR / "data" / "widget_process.pid"
LAUNCHER_SCRIPT = ROOT_DIR / "launch_desktop_app.py"
API_URL = "http://127.0.0.1:8787/api/widget/telemetry"
ACTION_URL = "http://127.0.0.1:8787/api/widget/action"

# Color Palette (Dark Cyber Aesthetic)
BG_DARK = "#060a12"
CARD_BG = "#0d1527"
CARD_BORDER = "#1e293b"
CARD_HEADER_BG = "#0f172a"
ACCENT_CYAN = "#38bdf8"
ACCENT_BLUE = "#0284c7"
TEXT_WHITE = "#ffffff"
TEXT_MUTED = "#94a3b8"
TEXT_AMBER = "#fbbf24"
TEXT_GREEN = "#10b981"
TEXT_RED = "#f87171"
BAR_BG = "#1e293b"
BAR_FILL = "#0ea5e9"


def _get_auth_headers() -> Dict[str, str]:
    headers = {"User-Agent": "AutoMoviePro-HUD/1.0"}
    token = os.environ.get("AUTO_MOVIE_APP_TOKEN", "").strip()
    if not token:
        token_path = ROOT_DIR / "data" / ".app_token"
        if token_path.exists():
            try:
                token = token_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    if token:
        headers["X-App-Token"] = token
    return headers


class AutoMovieDesktopWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AutoMovie Pro HUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG_DARK)

        # High-res positioning: top-right corner of screen
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.full_w, self.full_h = 420, 520
        self.compact_w, self.compact_h = 420, 160

        x = max(20, screen_w - self.full_w - 30)
        y = 45
        self.root.geometry(f"{self.full_w}x{self.full_h}+{x}+{y}")

        # Set ToolWindow style via ctypes (removes taskbar icon completely)
        self._apply_tool_window_style()

        # State variables
        self._drag_data = {"x": 0, "y": 0}
        self.is_pinned = True
        self.is_compact = False
        self.telemetry_data: Dict[str, Any] = {}
        self.is_connected = False
        self.logo_image_tk = None
        self.pulse_phase = 0
        self.current_progress = 0

        # Register PID
        self._record_pid()

        # Build GUI
        self._build_ui()

        # Start background workers
        self._start_telemetry_polling()
        self._animate_pulse()

    def _apply_tool_window_style(self):
        """Sets Windows WS_EX_TOOLWINDOW style so the widget does not show a taskbar icon."""
        if sys.platform != "win32":
            return
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000

            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception:
            pass

    def _record_pid(self):
        """Saves current process PID to data/widget_process.pid."""
        try:
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PID_FILE, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "started_at": datetime.now().isoformat()}, f, indent=2)
        except Exception:
            pass

    def _build_ui(self):
        # Outer container with border
        self.outer_border = tk.Frame(self.root, bg="#0284c7", padx=1, pady=1)
        self.outer_border.pack(fill="both", expand=True)

        self.main_container = tk.Frame(self.outer_border, bg=BG_DARK, padx=12, pady=10)
        self.main_container.pack(fill="both", expand=True)

        # -------------------------------------------------------------
        # 1. HEADER BAR (Draggable)
        # -------------------------------------------------------------
        self.header_frame = tk.Frame(self.main_container, bg=BG_DARK, cursor="fleur")
        self.header_frame.pack(fill="x", pady=(0, 10))

        # Drag bindings
        self.header_frame.bind("<ButtonPress-1>", self._start_drag)
        self.header_frame.bind("<B1-Motion>", self._do_drag)

        # Brand Icon & Title
        title_box = tk.Frame(self.header_frame, bg=BG_DARK)
        title_box.pack(side="left", fill="y")
        title_box.bind("<ButtonPress-1>", self._start_drag)
        title_box.bind("<B1-Motion>", self._do_drag)

        if LOGO_PNG.exists():
            try:
                img = Image.open(LOGO_PNG).resize((22, 22), Image.Resampling.LANCZOS)
                self.logo_image_tk = ImageTk.PhotoImage(img)
                lbl_icon = tk.Label(title_box, image=self.logo_image_tk, bg=BG_DARK)
                lbl_icon.pack(side="left", padx=(0, 6))
                lbl_icon.bind("<ButtonPress-1>", self._start_drag)
                lbl_icon.bind("<B1-Motion>", self._do_drag)
            except Exception:
                pass

        lbl_title = tk.Label(
            title_box,
            text="AutoMovie Pro",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_WHITE,
            bg=BG_DARK,
        )
        lbl_title.pack(side="left")
        lbl_title.bind("<ButtonPress-1>", self._start_drag)
        lbl_title.bind("<B1-Motion>", self._do_drag)

        lbl_badge = tk.Label(
            title_box,
            text="HUD",
            font=("Segoe UI", 7, "bold"),
            fg="#0284c7",
            bg="#0f172a",
            padx=4,
            pady=1,
            relief="solid",
            bd=1,
        )
        lbl_badge.pack(side="left", padx=(6, 0))
        lbl_badge.bind("<ButtonPress-1>", self._start_drag)
        lbl_badge.bind("<B1-Motion>", self._do_drag)

        # Status & Control buttons on the right
        btn_box = tk.Frame(self.header_frame, bg=BG_DARK)
        btn_box.pack(side="right")

        self.pulse_canvas = tk.Canvas(btn_box, width=12, height=12, bg=BG_DARK, highlightthickness=0)
        self.pulse_canvas.pack(side="left", padx=(0, 4))
        self.pulse_dot = self.pulse_canvas.create_oval(2, 2, 10, 10, fill=TEXT_GREEN, outline="")

        self.lbl_server_status = tk.Label(
            btn_box,
            text="ONLINE",
            font=("Segoe UI", 8, "bold"),
            fg=TEXT_GREEN,
            bg=BG_DARK,
        )
        self.lbl_server_status.pack(side="left", padx=(0, 8))

        # Pin Button
        self.btn_pin = tk.Button(
            btn_box,
            text="📌",
            font=("Segoe UI", 8),
            fg=ACCENT_CYAN,
            bg="#0f172a",
            activebackground="#1e293b",
            activeforeground=TEXT_WHITE,
            relief="flat",
            bd=0,
            padx=4,
            pady=1,
            cursor="hand2",
            command=self._toggle_pin,
        )
        self.btn_pin.pack(side="left", padx=2)

        # Compact Button
        self.btn_compact = tk.Button(
            btn_box,
            text="➖",
            font=("Segoe UI", 8),
            fg=TEXT_MUTED,
            bg="#0f172a",
            activebackground="#1e293b",
            activeforeground=TEXT_WHITE,
            relief="flat",
            bd=0,
            padx=4,
            pady=1,
            cursor="hand2",
            command=self._toggle_compact,
        )
        self.btn_compact.pack(side="left", padx=2)

        # Close Button
        self.btn_close = tk.Button(
            btn_box,
            text="✕",
            font=("Segoe UI", 8, "bold"),
            fg="#f87171",
            bg="#0f172a",
            activebackground="#ef4444",
            activeforeground=TEXT_WHITE,
            relief="flat",
            bd=0,
            padx=5,
            pady=1,
            cursor="hand2",
            command=self._on_close_clicked,
        )
        self.btn_close.pack(side="left", padx=(2, 0))

        # -------------------------------------------------------------
        # BODY CONTAINER (Collapsible in compact mode)
        # -------------------------------------------------------------
        self.body_container = tk.Frame(self.main_container, bg=BG_DARK)
        self.body_container.pack(fill="both", expand=True)

        # -------------------------------------------------------------
        # CARD 1: বর্তমান কার্যক্রম (Current Activity)
        # -------------------------------------------------------------
        card1 = tk.Frame(self.body_container, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        card1.pack(fill="x", pady=(0, 8))

        c1_head = tk.Frame(card1, bg=CARD_HEADER_BG, padx=8, pady=4)
        c1_head.pack(fill="x")

        tk.Label(
            c1_head,
            text="⚡ বর্তমান কার্যক্রম (Current Activity)",
            font=("Segoe UI", 8, "bold"),
            fg=ACCENT_CYAN,
            bg=CARD_HEADER_BG,
        ).pack(side="left")

        self.lbl_stage_badge = tk.Label(
            c1_head,
            text="স্ট্যান্ডবাই",
            font=("Segoe UI", 7, "bold"),
            fg=TEXT_AMBER,
            bg="#1e293b",
            padx=5,
            pady=1,
        )
        self.lbl_stage_badge.pack(side="right")

        c1_body = tk.Frame(card1, bg=CARD_BG, padx=8, pady=6)
        c1_body.pack(fill="x")

        self.lbl_job_title = tk.Label(
            c1_body,
            text="স্বয়ংক্রিয় শিডিউলের অপেক্ষায় সিস্টেম প্রস্তুত",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_WHITE,
            bg=CARD_BG,
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.lbl_job_title.pack(fill="x", pady=(0, 4))

        # Progress bar with canvas
        bar_row = tk.Frame(c1_body, bg=CARD_BG)
        bar_row.pack(fill="x", pady=(0, 4))

        self.prog_canvas = tk.Canvas(bar_row, height=8, bg=BAR_BG, highlightthickness=0)
        self.prog_canvas.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.prog_bar_rect = self.prog_canvas.create_rectangle(0, 0, 0, 8, fill=BAR_FILL, outline="")

        self.lbl_prog_pct = tk.Label(
            bar_row,
            text="০%",
            font=("Segoe UI", 8, "bold"),
            fg=ACCENT_CYAN,
            bg=CARD_BG,
            width=5,
            anchor="e",
        )
        self.lbl_prog_pct.pack(side="right")

        self.lbl_channel_info = tk.Label(
            c1_body,
            text="📺 চ্যানেল: AutoMovie Studio | নিশ: AI Automation",
            font=("Segoe UI", 8),
            fg=TEXT_MUTED,
            bg=CARD_BG,
            anchor="w",
        )
        self.lbl_channel_info.pack(fill="x")

        # -------------------------------------------------------------
        # CARD 2: পরবর্তী কার্যক্রমসমূহ (Upcoming Activities & Countdown)
        # -------------------------------------------------------------
        card2 = tk.Frame(self.body_container, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        card2.pack(fill="x", pady=(0, 8))

        c2_head = tk.Frame(card2, bg=CARD_HEADER_BG, padx=8, pady=4)
        c2_head.pack(fill="x")

        tk.Label(
            c2_head,
            text="⏰ পরবর্তী কার্যক্রমসমূহ (Upcoming Schedule)",
            font=("Segoe UI", 8, "bold"),
            fg=TEXT_AMBER,
            bg=CARD_HEADER_BG,
        ).pack(side="left")

        self.lbl_target_platform = tk.Label(
            c2_head,
            text="Reels & Shorts",
            font=("Segoe UI", 7, "bold"),
            fg=TEXT_WHITE,
            bg="#0284c7",
            padx=5,
            pady=1,
        )
        self.lbl_target_platform.pack(side="right")

        c2_body = tk.Frame(card2, bg=CARD_BG, padx=8, pady=6)
        c2_body.pack(fill="x")

        time_row = tk.Frame(c2_body, bg=CARD_BG)
        time_row.pack(fill="x", pady=(0, 2))

        self.lbl_next_slot = tk.Label(
            time_row,
            text="🕒 সময়: ১১:০০ AM",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_WHITE,
            bg=CARD_BG,
        )
        self.lbl_next_slot.pack(side="left")

        self.lbl_countdown_badge = tk.Label(
            time_row,
            text="⏳ বাকি: ০১:৩৪:১২",
            font=("Segoe UI", 8, "bold"),
            fg=TEXT_GREEN,
            bg="#064e3b",
            padx=6,
            pady=1,
        )
        self.lbl_countdown_badge.pack(side="right")

        self.lbl_upcoming_topic = tk.Label(
            c2_body,
            text="💡 টপিক: AutoMovie Pro AI Video Creation",
            font=("Segoe UI", 8),
            fg=TEXT_MUTED,
            bg=CARD_BG,
            anchor="w",
            wraplength=380,
            justify="left",
        )
        self.lbl_upcoming_topic.pack(fill="x", pady=(2, 0))

        # -------------------------------------------------------------
        # CARD 3: সিস্টেম ও প্রোডাকশন স্বাস্থ্য (Metrics Grid)
        # -------------------------------------------------------------
        card3 = tk.Frame(self.body_container, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        card3.pack(fill="x", pady=(0, 10))

        grid_frame = tk.Frame(card3, bg=CARD_BG, padx=4, pady=6)
        grid_frame.pack(fill="x")

        # 3 Columns
        for c in range(3):
            grid_frame.columnconfigure(c, weight=1)

        # Col 1: Today's Videos
        m1 = tk.Frame(grid_frame, bg="#0f172a", padx=4, pady=4, relief="flat")
        m1.grid(row=0, column=0, padx=3, sticky="nsew")
        tk.Label(m1, text="🎥 আজকের ভিডিও", font=("Segoe UI", 7), fg=TEXT_MUTED, bg="#0f172a").pack()
        self.lbl_metric_videos = tk.Label(m1, text="০ টি", font=("Segoe UI", 9, "bold"), fg=TEXT_WHITE, bg="#0f172a")
        self.lbl_metric_videos.pack()

        # Col 2: CPU Load
        m2 = tk.Frame(grid_frame, bg="#0f172a", padx=4, pady=4, relief="flat")
        m2.grid(row=0, column=1, padx=3, sticky="nsew")
        tk.Label(m2, text="⚙️ CPU লোড", font=("Segoe UI", 7), fg=TEXT_MUTED, bg="#0f172a").pack()
        self.lbl_metric_cpu = tk.Label(m2, text="৫%", font=("Segoe UI", 9, "bold"), fg=ACCENT_CYAN, bg="#0f172a")
        self.lbl_metric_cpu.pack()

        # Col 3: RAM Load
        m3 = tk.Frame(grid_frame, bg="#0f172a", padx=4, pady=4, relief="flat")
        m3.grid(row=0, column=2, padx=3, sticky="nsew")
        tk.Label(m3, text="💾 RAM ব্যবহার", font=("Segoe UI", 7), fg=TEXT_MUTED, bg="#0f172a").pack()
        self.lbl_metric_ram = tk.Label(m3, text="৩৫%", font=("Segoe UI", 9, "bold"), fg=TEXT_GREEN, bg="#0f172a")
        self.lbl_metric_ram.pack()

        # -------------------------------------------------------------
        # 4. ACTION DECK (Buttons)
        # -------------------------------------------------------------
        self.action_deck = tk.Frame(self.main_container, bg=BG_DARK)
        self.action_deck.pack(fill="x")

        self.btn_open_dash = tk.Button(
            self.action_deck,
            text="🚀 ড্যাশবোর্ড খুলুন",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_WHITE,
            bg="#0284c7",
            activebackground="#2563eb",
            activeforeground=TEXT_WHITE,
            relief="flat",
            bd=0,
            pady=6,
            cursor="hand2",
            command=self._on_open_dashboard,
        )
        self.btn_open_dash.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_instant_video = tk.Button(
            self.action_deck,
            text="⚡ ১-ক্লিক ভিডিও",
            font=("Segoe UI", 8, "bold"),
            fg=TEXT_WHITE,
            bg="#059669",
            activebackground="#10b981",
            activeforeground=TEXT_WHITE,
            relief="flat",
            bd=0,
            pady=6,
            padx=8,
            cursor="hand2",
            command=self._on_instant_video,
        )
        self.btn_instant_video.pack(side="left", padx=(0, 4))

        self.btn_pause_sched = tk.Button(
            self.action_deck,
            text="⏸️ পজ",
            font=("Segoe UI", 8),
            fg=TEXT_MUTED,
            bg="#1e293b",
            activebackground="#334155",
            activeforeground=TEXT_WHITE,
            relief="flat",
            bd=0,
            pady=6,
            padx=8,
            cursor="hand2",
            command=self._on_toggle_scheduler,
        )
        self.btn_pause_sched.pack(side="right")

    # -----------------------------------------------------------------
    # Drag & Window Controls
    # -----------------------------------------------------------------
    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _do_drag(self, event):
        deltax = event.x - self._drag_data["x"]
        deltay = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def _toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self.root.attributes("-topmost", self.is_pinned)
        self.btn_pin.configure(fg=ACCENT_CYAN if self.is_pinned else TEXT_MUTED)

    def _toggle_compact(self):
        self.is_compact = not self.is_compact
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()
        if self.is_compact:
            self.body_container.pack_forget()
            self.action_deck.pack_forget()
            self.root.geometry(f"{self.compact_w}x{self.compact_h}+{cur_x}+{cur_y}")
            self.btn_compact.configure(text="➕")
        else:
            self.body_container.pack(fill="both", expand=True)
            self.action_deck.pack(fill="x")
            self.root.geometry(f"{self.full_w}x{self.full_h}+{cur_x}+{cur_y}")
            self.btn_compact.configure(text="➖")

    def _on_close_clicked(self):
        """Clean shutdown of the widget HUD."""
        try:
            if PID_FILE.exists():
                PID_FILE.unlink()
        except Exception:
            pass
        self.root.destroy()
        sys.exit(0)

    # -----------------------------------------------------------------
    # Telemetry Polling Worker
    # -----------------------------------------------------------------
    def _start_telemetry_polling(self):
        def worker():
            while True:
                try:
                    req = urllib.request.Request(API_URL, headers=_get_auth_headers())
                    with urllib.request.urlopen(req, timeout=1.8) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            self.root.after(0, self._apply_telemetry, data)
                except Exception:
                    self.root.after(0, self._apply_offline_state)
                time.sleep(2.0)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _apply_telemetry(self, data: Dict[str, Any]):
        self.is_connected = True
        self.telemetry_data = data
        self.lbl_server_status.configure(text="ONLINE", fg=TEXT_GREEN)

        cur = data.get("current_activity") or {}
        up = data.get("upcoming_activities") or {}
        met = data.get("engine_metrics") or {}

        # 1. Current Activity
        is_busy = cur.get("is_busy", False)
        stage_label = cur.get("stage_label_bn", "স্ট্যান্ডবাই")
        self.lbl_stage_badge.configure(
            text=stage_label,
            fg=TEXT_GREEN if is_busy else TEXT_AMBER,
            bg="#064e3b" if is_busy else "#1e293b",
        )
        self.lbl_job_title.configure(text=cur.get("title", "স্বয়ংক্রিয় শিডিউলের অপেক্ষায় সিস্টেম প্রস্তুত"))

        prog = int(cur.get("progress") or 0)
        self.lbl_prog_pct.configure(text=f"{prog}%")
        self._update_progress_bar(prog)

        ch_name = cur.get("channel_name", "AutoMovie Studio")
        niche = cur.get("niche", "AI Automation")
        self.lbl_channel_info.configure(text=f"📺 চ্যানেল: {ch_name} | নিশ: {niche}")

        # 2. Upcoming Schedule
        slot_12h = up.get("next_slot_12h", "১১:০০ AM")
        self.lbl_next_slot.configure(text=f"🕒 সময়: {slot_12h}")

        countdown = up.get("countdown_clock", "00:00:00")
        self.lbl_countdown_badge.configure(text=f"⏳ বাকি: {countdown}")

        topic = up.get("topic", "AutoMovie Pro AI Video Creation")
        self.lbl_upcoming_topic.configure(text=f"💡 টপিক: {topic}")

        # 3. Metrics
        self.lbl_metric_videos.configure(text=met.get("videos_today_bn", "০ টি"))
        self.lbl_metric_cpu.configure(text=met.get("cpu_percent_bn", "৫%"))
        self.lbl_metric_ram.configure(text=met.get("ram_percent_bn", "৩৫%"))

    def _apply_offline_state(self):
        self.is_connected = False
        self.lbl_server_status.configure(text="OFFLINE", fg=TEXT_RED)
        self.lbl_stage_badge.configure(text="সার্ভার সংযোগ বিচ্ছিন্ন", fg=TEXT_RED, bg="#450a0a")
        self.lbl_job_title.configure(text="⚠️ ব্যাকগ্রাউন্ড ইঞ্জিন পুনরায় চালু করার চেষ্টা করা হচ্ছে...")

    def _update_progress_bar(self, target_prog: int):
        self.current_progress = target_prog
        self.prog_canvas.update_idletasks()
        w = self.prog_canvas.winfo_width()
        if w <= 1:
            w = 320
        fill_w = int((target_prog / 100.0) * w)
        self.prog_canvas.coords(self.prog_bar_rect, 0, 0, fill_w, 8)

    def _animate_pulse(self):
        """Subtle glowing pulse for the ONLINE indicator."""
        if self.is_connected:
            colors = ["#10b981", "#34d399", "#059669", "#10b981"]
            color = colors[self.pulse_phase % len(colors)]
            self.pulse_canvas.itemconfig(self.pulse_dot, fill=color)
            self.pulse_phase += 1
        else:
            self.pulse_canvas.itemconfig(self.pulse_dot, fill=TEXT_RED)
        self.root.after(800, self._animate_pulse)

    # -----------------------------------------------------------------
    # User Actions
    # -----------------------------------------------------------------
    def _on_open_dashboard(self):
        """Restores or launches the main native desktop application window."""
        self.btn_open_dash.configure(text="⏳ খোলা হচ্ছে...")
        self.root.update()

        def do_launch():
            try:
                # 1. Fire launcher directly
                pyw = sys.executable.replace("python.exe", "pythonw.exe")
                DETACHED = 0x08000000 | 0x00000200
                subprocess.Popen(
                    [pyw, str(LAUNCHER_SCRIPT)],
                    cwd=str(ROOT_DIR),
                    creationflags=DETACHED if sys.platform == "win32" else 0,
                    close_fds=True,
                )
            except Exception:
                pass
            time.sleep(1.0)
            self.root.after(0, lambda: self.btn_open_dash.configure(text="🚀 ড্যাশবোর্ড খুলুন"))

        threading.Thread(target=do_launch, daemon=True).start()

    def _on_instant_video(self):
        """Triggers 1-click video generation or opens dashboard."""
        self._on_open_dashboard()

    def _on_toggle_scheduler(self):
        """Toggles scheduler state between pause and resume."""
        current_text = self.btn_pause_sched.cget("text")
        if "পজ" in current_text:
            self.btn_pause_sched.configure(text="▶️ চালু", fg=TEXT_GREEN)
        else:
            self.btn_pause_sched.configure(text="⏸️ পজ", fg=TEXT_MUTED)

        def send_action():
            try:
                req = urllib.request.Request(
                    ACTION_URL,
                    data=json.dumps({"action": "toggle_scheduler"}).encode("utf-8"),
                    headers={"Content-Type": "application/json", **_get_auth_headers()},
                )
                urllib.request.urlopen(req, timeout=1.5)
            except Exception:
                pass

        threading.Thread(target=send_action, daemon=True).start()

    def run(self):
        self.root.mainloop()


def main():
    app = AutoMovieDesktopWidget()
    app.run()


if __name__ == "__main__":
    main()

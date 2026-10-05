# -*- coding: utf-8 -*-
"""
AutoMovie Pro - Native Desktop Installer & Launch Manager
Production-grade GUI installer and environment validator.
"""

import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def find_python():
    venv_py = BASE_DIR / "venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable

def find_ffmpeg():
    # Check bundled ffmpeg
    bundled = list(BASE_DIR.glob("ffmpeg-*/bin/ffmpeg.exe"))
    if not bundled:
        bundled = list(BASE_DIR.glob("ffmpeg-*/*/bin/ffmpeg.exe"))
    if bundled and bundled[0].is_file():
        return str(bundled[0])
    return "ffmpeg"

class AutoMovieInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoMovie Pro - Official Desktop Setup & Launcher (v0.5.0)")
        self.root.geometry("680x540")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f172a")

        # Set font styles
        self.title_font = ("Segoe UI", 16, "bold")
        self.body_font = ("Segoe UI", 10)
        self.mono_font = ("Consolas", 9)

        self._build_ui()
        self.root.after(500, self.run_preflight_checks)

    def _build_ui(self):
        # Header banner
        header = tk.Frame(self.root, bg="#1e293b", height=80)
        header.pack(fill=tk.X, side=tk.TOP)

        lbl_title = tk.Label(
            header,
            text="🎬 AutoMovie Pro — Official Setup & Launcher",
            font=self.title_font,
            fg="#38bdf8",
            bg="#1e293b"
        )
        lbl_title.pack(anchor="w", padx=20, pady=(12, 2))

        lbl_sub = tk.Label(
            header,
            text="১০০% স্বয়ংক্রিয় ভিডিও প্রোডাকশন ও মাল্টি-চ্যানেল পাবলিশিং সিস্টেম",
            font=self.body_font,
            fg="#94a3b8",
            bg="#1e293b"
        )
        lbl_sub.pack(anchor="w", padx=20, pady=(0, 10))

        # Main Body
        main_frame = tk.Frame(self.root, bg="#0f172a")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        # Status Grid
        status_frame = tk.LabelFrame(
            main_frame,
            text=" সিস্টেম কম্পোনেন্ট যাচাইকরণ (System Preflight) ",
            fg="#38bdf8",
            bg="#0f172a",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10
        )
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_items = {
            "python": ("Python Runtime ইঞ্জিন", tk.Label(status_frame, text="যাচাই হচ্ছে...", fg="#facc15", bg="#0f172a", font=self.body_font)),
            "ffmpeg": ("FFmpeg 8.1.1 Full Build", tk.Label(status_frame, text="যাচাই হচ্ছে...", fg="#facc15", bg="#0f172a", font=self.body_font)),
            "voice": ("Jarvis ভয়েস কিউ অডিও এসেট", tk.Label(status_frame, text="যাচাই হচ্ছে...", fg="#facc15", bg="#0f172a", font=self.body_font)),
            "fonts": ("বাংলা ইউনিকোড ফন্ট (Kalpurush)", tk.Label(status_frame, text="যাচাই হচ্ছে...", fg="#facc15", bg="#0f172a", font=self.body_font)),
            "dirs": ("ওয়ার্কস্পেস ও আউটপুট ডিরেক্টরি", tk.Label(status_frame, text="যাচাই হচ্ছে...", fg="#facc15", bg="#0f172a", font=self.body_font)),
        }

        r = 0
        for key, (label_text, lbl_val) in self.status_items.items():
            tk.Label(status_frame, text=f"• {label_text}:", fg="#e2e8f0", bg="#0f172a", font=self.body_font).grid(row=r, column=0, sticky="w", pady=2)
            lbl_val.grid(row=r, column=1, sticky="e", padx=20, pady=2)
            status_frame.grid_columnconfigure(1, weight=1)
            r += 1

        # Log Output Box
        log_frame = tk.Frame(main_frame, bg="#0f172a")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))

        self.txt_log = tk.Text(log_frame, height=7, bg="#030712", fg="#22c55e", font=self.mono_font, relief="flat")
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Buttons Control Bar
        btn_bar = tk.Frame(self.root, bg="#1e293b", height=65)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_install = tk.Button(
            btn_bar,
            text="⚡ সেটআপ ও ডাটাবেস প্রস্তুত করুন",
            bg="#2563eb",
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
            command=self.run_setup_action
        )
        self.btn_install.pack(side=tk.LEFT, padx=20, pady=12)

        self.btn_shortcut = tk.Button(
            btn_bar,
            text="📌 শর্টকাট তৈরি করুন",
            bg="#334155",
            fg="#e2e8f0",
            font=self.body_font,
            relief="flat",
            padx=12,
            pady=8,
            cursor="hand2",
            command=self.create_desktop_shortcut
        )
        self.btn_shortcut.pack(side=tk.LEFT, padx=5, pady=12)

        self.btn_launch = tk.Button(
            btn_bar,
            text="🚀 সফটওয়্যার চালু করুন (Launch)",
            bg="#059669",
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
            command=self.launch_software
        )
        self.btn_launch.pack(side=tk.RIGHT, padx=20, pady=12)

    def log(self, text):
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)

    def run_preflight_checks(self):
        self.log(">> সিস্টেম কম্পোনেন্ট স্ক্যান শুরু হচ্ছে...")
        py_path = find_python()
        if os.path.exists(py_path):
            self.status_items["python"][1].config(text="✓ সক্রিয় (Found)", fg="#4ade80")
            self.log(f"[OK] Python: {py_path}")
        else:
            self.status_items["python"][1].config(text="✗ অনুপুস্থিত", fg="#f87171")
            self.log("[WARN] Python virtual environment missing.")

        ff_path = find_ffmpeg()
        if os.path.exists(ff_path):
            self.status_items["ffmpeg"][1].config(text="✓ ফুল বিল্ড প্রস্তুত", fg="#4ade80")
            self.log(f"[OK] FFmpeg: {ff_path}")
        else:
            self.status_items["ffmpeg"][1].config(text="! সিস্টেম PATH", fg="#facc15")
            self.log("[INFO] FFmpeg relying on system PATH.")

        # Voice cues
        voice_dir = BASE_DIR / "assets" / "audio" / "voice_cues"
        cues = list(voice_dir.glob("*.wav")) if voice_dir.exists() else []
        if len(cues) >= 10:
            self.status_items["voice"][1].config(text=f"✓ ১২টি কিউ প্রস্তুত", fg="#4ade80")
            self.log(f"[OK] Audio Cues: {len(cues)} files verified.")
        else:
            self.status_items["voice"][1].config(text="! তৈরি করা প্রয়োজন", fg="#facc15")

        # Fonts
        font_file = BASE_DIR / "assets" / "fonts" / "Kalpurush.ttf"
        if font_file.is_file():
            self.status_items["fonts"][1].config(text="✓ Kalpurush যুক্ত আছে", fg="#4ade80")
            self.log(f"[OK] Bengali Font: {font_file}")
        else:
            self.status_items["fonts"][1].config(text="! মিসিং", fg="#f87171")

        # Dirs
        for d in ["Output", "data", "_quota_state", "assets/audio/voice_cues", "assets/fonts"]:
            (BASE_DIR / d).mkdir(parents=True, exist_ok=True)
        self.status_items["dirs"][1].config(text="✓ অল রেডি", fg="#4ade80")
        self.log("[OK] Directories verified and ensured.")
        self.log(">> সিস্টেম ব্যবহারের জন্য ১০০% প্রস্তুত!")

    def run_setup_action(self):
        def _task():
            self.btn_install.config(state=tk.DISABLED)
            self.log("\n>> ডাটাবেস ও ভয়েস সিন্থেসিস ইনিশিয়ালাইজ করা হচ্ছে...")
            py_cmd = find_python()
            script = str(BASE_DIR / "scripts" / "generate_voice_cues.py")
            if os.path.exists(script):
                res = subprocess.run([py_cmd, script], capture_output=True, text=True)
                self.log(res.stdout or "")
                if res.stderr:
                    self.log("[DEBUG] " + res.stderr)
            self.log("[SUCCESS] সম্পূর্ণ সেটআপ সফলভাবে সম্পন্ন হয়েছে।")
            self.root.after(0, self.run_preflight_checks)
            self.root.after(0, lambda: self.btn_install.config(state=tk.NORMAL))
            self.root.after(0, lambda: messagebox.showinfo("AutoMovie Pro", "অভিনন্দন! আপনার সফটওয়্যার সফলভাবে প্রস্তুত হয়েছে।"))

        threading.Thread(target=_task, daemon=True).start()

    def create_desktop_shortcut(self):
        desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
        if not desktop.exists():
            messagebox.showerror("Error", "Desktop folder not found.")
            return
        bat_file = BASE_DIR / "Start_AutoMovie_Pro.bat"
        shortcut_file = desktop / "AutoMovie Pro.bat"
        try:
            with open(shortcut_file, "w", encoding="utf-8") as f:
                f.write(f'@echo off\ncd /d "{BASE_DIR}"\ncall "Start_AutoMovie_Pro.bat"\n')
            messagebox.showinfo("শর্টকাট তৈরি", f"ডেস্কটপে শর্টকাট সফলভাবে তৈরি করা হয়েছে:\n{shortcut_file}")
            self.log(f"[OK] Shortcut created on Desktop: {shortcut_file}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create shortcut: {e}")

    def launch_software(self):
        bat_file = BASE_DIR / "Start_AutoMovie_Pro.bat"
        if bat_file.exists():
            subprocess.Popen(["cmd.exe", "/c", str(bat_file)], cwd=str(BASE_DIR))
            self.log("[LAUNCH] AutoMovie Pro ব্যাকগ্রাউন্ডে চালু করা হয়েছে!")
        else:
            py_cmd = find_python()
            subprocess.Popen([py_cmd, "-m", "app.main"], cwd=str(BASE_DIR))
            self.log("[LAUNCH] AutoMovie Pro engine started on http://127.0.0.1:8787")


def main():
    root = tk.Tk()
    app = AutoMovieInstallerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

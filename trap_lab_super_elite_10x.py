#!/usr/bin/env python3
"""
TRAP LAB SUPER ELITE 10X
Forensic Control Panel — with dependency bootstrap + MTK path auto-detect
"""

import sys
import subprocess
import importlib


# ─────────────────────────────────────────────
#  DEPENDENCY BOOTSTRAP
# ─────────────────────────────────────────────
REQUIRED = {"PySide6": "PySide6"}

def ensure_deps():
    missing = [pkg for mod, pkg in REQUIRED.items()
               if importlib.util.find_spec(mod) is None]
    if missing:
        print(f"[SETUP] Installing: {missing}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages"] + missing
        )
        print("[SETUP] Done. Restarting...")
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)

ensure_deps()


import time
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QPushButton, QTextEdit, QLabel, QTabWidget,
    QMessageBox, QFrame
)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont


# ─────────────────────────────────────────────
#  MTK PATH AUTO-DETECT
# ─────────────────────────────────────────────
def find_mtk():
    script_dir = Path(__file__).parent.resolve()
    candidates = [
        script_dir / "mtk.py",
        script_dir.parent / "mtk.py",
        Path.home() / "projects" / "Droidtools" / "mtk.py",
        Path.home() / "projects" / "Droidtools" / "mtkclient" / "mtk.py",
    ]
    for p in candidates:
        if p.is_file():
            return f"{sys.executable} {p}"
    if shutil.which("mtk"):
        return "mtk"
    return None


MTK_CMD = find_mtk()


# ─────────────────────────────────────────────
#  TOOL CHECK
# ─────────────────────────────────────────────
def check_tool(name):
    return shutil.which(name) is not None

TOOLS = {
    "adb":      check_tool("adb"),
    "fastboot": check_tool("fastboot"),
    "mtk":      MTK_CMD is not None,
    "lsusb":    check_tool("lsusb"),
}


# ─────────────────────────────────────────────
#  ENGINE
# ─────────────────────────────────────────────
class Engine:
    def run(self, cmd, timeout=15):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=timeout)
            out = r.stdout.strip()
            err = r.stderr.strip()
            return out if out else (err if err else "(no output)")
        except subprocess.TimeoutExpired:
            return f"[TIMEOUT] {timeout}s — {cmd}"
        except Exception as e:
            return f"[ERROR] {e}"

    def mtk(self, args, timeout=30):
        if not MTK_CMD:
            return "[MTK] Not found. See Info tab."
        return self.run(f"{MTK_CMD} {args}", timeout=timeout)

engine = Engine()


# ─────────────────────────────────────────────
#  ASYNC COMMAND WORKER
# ─────────────────────────────────────────────
class CmdWorker(QThread):
    done = Signal(str, str)

    def __init__(self, title, cmd, timeout=60):
        super().__init__()
        self.title = title
        self.cmd = cmd
        self.timeout = timeout

    def run(self):
        result = engine.run(self.cmd, self.timeout)
        self.done.emit(self.title, result)


class SeqCmdWorker(QThread):
    """Runs a list of (title, cmd, timeout) commands sequentially."""
    step = Signal(str, str)

    def __init__(self, commands):
        super().__init__()
        self.commands = commands

    def run(self):
        for title, cmd, timeout in self.commands:
            result = engine.run(cmd, timeout)
            self.step.emit(title, result)


# ─────────────────────────────────────────────
#  LOGGER
# ─────────────────────────────────────────────
class Logger:
    def __init__(self):
        self.logs = []

    def add(self, title, data):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] ── {title} ──\n{data}\n"
        self.logs.append(entry)
        return entry

    def export(self, path="traplab_report.txt"):
        Path(path).write_text("\n".join(self.logs), encoding="utf-8")
        return path

logger = Logger()


# ─────────────────────────────────────────────
#  LIVE MONITOR
# ─────────────────────────────────────────────
class Monitor(QThread):
    update = Signal(str, str, str)

    def __init__(self, interval=4):
        super().__init__()
        self._running = True
        self.interval = interval

    def run(self):
        while self._running:
            adb      = engine.run("adb devices")     if TOOLS["adb"]      else "adb not found"
            usb      = engine.run("lsusb")            if TOOLS["lsusb"]    else "lsusb not found"
            fastboot = engine.run("fastboot devices") if TOOLS["fastboot"] else "fastboot not found"
            self.update.emit(adb, usb, fastboot)
            time.sleep(self.interval)

    def stop(self):
        self._running = False
        self.wait()


# ─────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────
class TrapLab(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔥 TRAP LAB — SUPER ELITE 10X")
        self.resize(1200, 820)
        self._apply_dark_theme()

        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 10)

        self.status = QLabel("🔴  Waiting for devices...")
        self.status.setFont(QFont("Monospace", 11, QFont.Bold))
        root.addWidget(self.status)

        mtk_label = QLabel(
            f"✅  MTK → {MTK_CMD}" if MTK_CMD else
            "❌  MTK not found — see Info tab"
        )
        mtk_label.setStyleSheet("color: #00ff88;" if MTK_CMD else "color: #f0a500;")
        mtk_label.setFont(QFont("Monospace", 9))
        root.addWidget(mtk_label)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self._build_tabs()

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Monospace", 9))
        self.console.setMaximumHeight(260)
        root.addWidget(self.console)

        self._log("SYSTEM", f"Started. MTK={MTK_CMD or 'NOT FOUND'} | Tools={TOOLS}")

        self.monitor = Monitor()
        self.monitor.update.connect(self._on_device_update)
        self.monitor.start()

    def _build_tabs(self):
        self.tabs.addTab(self._dashboard_tab(), "📡  Dashboard")
        self.tabs.addTab(self._mtk_tab(),       "🔧  MTK")
        self.tabs.addTab(self._frp_da_tab(),    "🔓  FRP — DA")
        self.tabs.addTab(self._tools_tab(),     "🛠  Tools")
        self.tabs.addTab(self._info_tab(),      "ℹ️  Info")

    def _dashboard_tab(self):
        tab, l = self._tab()
        self._btn(l, "Scan ADB",          lambda: self._exec("ADB",      "adb devices"))
        self._btn(l, "Scan USB",          lambda: self._exec("USB",      "lsusb"))
        self._btn(l, "Fastboot List",     lambda: self._exec("FASTBOOT", "fastboot devices"))
        self._btn(l, "ADB getprop",       lambda: self._exec("GETPROP",  "adb shell getprop"))
        self._btn(l, "ADB Shell — df -h", lambda: self._exec("DF",       "adb shell df -h"))
        l.addStretch()
        return tab

    def _mtk_tab(self):
        tab, l = self._tab()

        # ── BROM / Preloader ──────────────────────────────────────
        brom_label = QLabel("BROM / Preloader")
        brom_label.setStyleSheet("color: #aaa; font-size: 8pt; margin-top: 4px;")
        l.addWidget(brom_label)
        self._btn(l, "Detect Mode  (BROM vs Preloader)",
                  lambda: self._mtk_async("DETECT", "printinfo", timeout=30))
        self._btn(l, "Force BROM — crash  (modes 0→2, auto)",
                  lambda: self._mtk_async("FORCE BROM", "crash", timeout=60))
        self._btn(l, "Force BROM — watchdog reset  (mode 3, reliable)",
                  lambda: self._mtk_async("FORCE BROM WDT", "crash --mode 3", timeout=60))
        self._btn(l, "Force BROM — preloader + crash  (--crash flag)",
                  lambda: self._mtk_async("FORCE BROM FLAG", "printinfo --crash", timeout=60))
        self._sep(l)

        # ── Info / Partition ──────────────────────────────────────
        self._btn(l, "MTK — Print Info",      lambda: self._mtk_async("INFO",  "printinfo", timeout=30))
        self._btn(l, "MTK — Print GPT",       lambda: self._mtk_async("GPT",   "printgpt",  timeout=30))
        self._btn(l, "MTK — Logs",            lambda: self._mtk_async("LOGS",  "logs",       timeout=30))
        self._btn(l, "MTK — Dump Partitions", lambda: self._mtk_async("DUMP",  "rl ./dump",  timeout=180))
        self._sep(l)
        frp = self._btn(l, "⚠️  FRP Safe Bypass", self._frp_safe)
        frp.setStyleSheet("QPushButton { background: #7a1a1a; color: #fff; }")
        l.addStretch()
        return tab

    def _frp_da_tab(self):
        tab, l = self._tab()
        note = QLabel(
            "Uses MTK Download Agent to erase partitions directly.\n"
            "Device must be in BROM / preloader mode (USB, powered off or vol-down)."
        )
        note.setStyleSheet("color: #aaa; font-size: 9pt;")
        note.setWordWrap(True)
        l.addWidget(note)

        self._btn(l, "Scan GPT — list partitions",
                  lambda: self._mtk_async("GPT", "printgpt", timeout=30))
        self._sep(l)

        self._btn(l, "Erase  frp  (FRP lock only)",
                  lambda: self._frp_da_erase(["frp"], "FRP"))
        self._btn(l, "Erase  frp + persistence",
                  lambda: self._frp_da_erase(["frp", "persistence"], "FRP+PERSIST"))
        self._btn(l, "Erase  frp + persistence + nvram + nvdata  (MTK full)",
                  lambda: self._frp_da_erase(["frp", "persistence", "nvram", "nvdata"],
                                             "FRP+NVRAM"))
        self._sep(l)

        full = self._btn(l, "Full FRP Reset — backup → erase → reboot",
                         self._frp_da_full)
        full.setStyleSheet("QPushButton { background: #7a1a1a; color: #fff; }")
        l.addStretch()
        return tab

    # ── DA FRP helpers ──────────────────────────────────────────

    def _frp_da_erase(self, partitions: list, label: str):
        names = ", ".join(partitions)
        reply = QMessageBox.warning(
            self, "Confirm DA Erase",
            f"Erase partition(s): {names}\n\nOwn device only. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._mtk_async(f"DA ERASE [{label}]",
                            f"e {','.join(partitions)}", timeout=300)

    def _frp_da_full(self):
        reply = QMessageBox.warning(
            self, "Full FRP Reset",
            "This will:\n"
            "  1. Backup ALL partitions → ./backup\n"
            "  2. Erase frp, persistence, nvram, nvdata\n"
            "  3. Reboot\n\n"
            "Own device only. Backup can take several minutes.\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if not MTK_CMD:
                self._log("DA BACKUP", "[MTK] Not found. See Info tab.")
                return
            cmds = [
                ("DA BACKUP",        f"{MTK_CMD} rl ./backup",                    300),
                ("DA ERASE [FULL]",  f"{MTK_CMD} e frp,persistence,nvram,nvdata", 120),
                ("DA REBOOT",        f"{MTK_CMD} reset",                           15),
            ]
            self._log("DA FULL FRP", "[RUNNING] backup → erase → reboot (sequential)")
            worker = SeqCmdWorker(cmds)
            worker.step.connect(self._log)
            worker.start()
            if not hasattr(self, "_workers"):
                self._workers = []
            self._workers.append(worker)

    def _mtk_async(self, title: str, args: str, timeout: int = 60):
        if not MTK_CMD:
            self._log(title, "[MTK] Not found. See Info tab.")
            return
        if not hasattr(self, "_workers"):
            self._workers = []
        self._workers = [w for w in self._workers if w.isRunning()]
        self._log(title, f"[RUNNING] {MTK_CMD} {args}")
        worker = CmdWorker(title, f"{MTK_CMD} {args}", timeout)
        worker.done.connect(self._log)
        worker.start()
        self._workers.append(worker)

    def _tools_tab(self):
        tab, l = self._tab()
        self._btn(l, "Export Logs", self._export_logs)
        self._btn(l, "Clear Console", lambda: self.console.clear())
        self._btn(l, "Refresh Tool Check", self._refresh_tools)
        l.addStretch()
        return tab

    def _info_tab(self):
        tab, l = self._tab()
        box = QTextEdit()
        box.setReadOnly(True)
        box.setFont(QFont("Monospace", 9))
        box.setPlainText(self._info_text())
        l.addWidget(box)
        return tab

    def _tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)
        return w, lay

    def _btn(self, layout, label, fn):
        b = QPushButton(label)
        b.setMinimumHeight(36)
        b.clicked.connect(fn)
        layout.addWidget(b)
        return b

    def _sep(self, layout):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

    def _exec(self, title, cmd, timeout=15):
        self._log(title, engine.run(cmd, timeout))

    def _mtk(self, title, args, timeout=30):
        self._log(title, engine.mtk(args, timeout))

    def _log(self, title, data):
        entry = logger.add(title, data)
        self.console.append(entry)
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_device_update(self, adb, usb, fastboot):
        connected = "device" in adb or "device" in fastboot
        if connected:
            self.status.setText("🟢  DEVICE CONNECTED")
            self.status.setStyleSheet("color: #00ff88;")
        else:
            self.status.setText("🔴  NO DEVICE DETECTED")
            self.status.setStyleSheet("color: #ff4444;")

    def _frp_safe(self):
        reply = QMessageBox.warning(
            self, "⚠️ FRP BYPASS",
            "This will:\n\n  1. Backup → ./backup\n  2. Erase frp + persistence\n  3. Reboot\n\nOwn device only. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if not MTK_CMD:
                self._log("FRP SAFE", "[MTK] Not found. See Info tab.")
                return
            cmds = [
                ("BACKUP",    f"{MTK_CMD} rl ./backup",       180),
                ("FRP ERASE", f"{MTK_CMD} e frp,persistence",  60),
                ("REBOOT",    f"{MTK_CMD} reset",               15),
            ]
            self._log("FRP SAFE", "[RUNNING] backup → erase → reboot (sequential)")
            worker = SeqCmdWorker(cmds)
            worker.step.connect(self._log)
            worker.start()
            if not hasattr(self, "_workers"):
                self._workers = []
            self._workers.append(worker)

    def _export_logs(self):
        path = logger.export()
        self._log("EXPORT", f"Saved → {path}")

    def _refresh_tools(self):
        global MTK_CMD
        MTK_CMD = find_mtk()
        for t in ["adb", "fastboot", "lsusb"]:
            TOOLS[t] = check_tool(t)
        TOOLS["mtk"] = MTK_CMD is not None
        self._log("TOOLS", f"{TOOLS}\nMTK: {MTK_CMD or 'NOT FOUND'}")

    def _info_text(self):
        lines = [
            "TRAP LAB — SUPER ELITE 10X",
            "=" * 50, "",
            "TOOL STATUS", "-" * 30,
        ]
        for t, ok in TOOLS.items():
            lines.append(f"  {'✅' if ok else '❌'}  {t}")
        lines += [
            "",
            "MTK COMMAND:", f"  {MTK_CMD or 'NOT FOUND'}",
            "",
            "MTK AUTO-DETECT ORDER:",
            "  1. Same folder as this script  (mtk.py)",
            "  2. Parent folder               (mtk.py)",
            "  3. ~/projects/Droidtools/      (mtk.py)",
            "  4. System PATH                 (mtk binary)",
            "",
            "QUICKEST FIX — run from Droidtools dir:",
            "  cd ~/projects/Droidtools",
            "  python trap_lab_super_elite_10x.py",
            "",
            "OR symlink mtk to PATH:",
            "  ln -s ~/projects/Droidtools/mtk.py ~/.local/bin/mtk",
            "  chmod +x ~/.local/bin/mtk",
            "",
            "USB PERMISSIONS:",
            "  sudo usermod -aG plugdev $USER",
            "  (log out and back in)",
        ]
        return "\n".join(lines)

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget        { background: #1a1a2e; color: #e0e0e0; }
            QTabWidget     { border: none; }
            QTabBar::tab   { background: #16213e; color: #aaa;
                             padding: 8px 18px; border-radius: 4px 4px 0 0; }
            QTabBar::tab:selected { background: #0f3460; color: #fff; }
            QPushButton    { background: #0f3460; color: #e0e0e0; border: none;
                             border-radius: 5px; padding: 8px 14px; }
            QPushButton:hover   { background: #16498a; }
            QPushButton:pressed { background: #0a2540; }
            QTextEdit      { background: #0d0d1a; color: #00ff88;
                             border: 1px solid #333; border-radius: 4px; }
            QLabel         { color: #e0e0e0; }
        """)

    def closeEvent(self, event):
        self.monitor.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("TrapLab 10X")
    win = TrapLab()
    win.show()
    sys.exit(app.exec())

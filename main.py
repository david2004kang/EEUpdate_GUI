"""I226 EEUpdate GUI: read/write NIC MAC address (requires Administrator)."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
EEUPDATE_EXE = os.path.join(APP_DIR, "I226_EEUPDATE", "EEUPDATEW64e.exe")
LOG_FILE = os.path.join(APP_DIR, "dev_log.txt")
CONFIG_FILE = os.path.join(APP_DIR, "program.dat")
HEX_CHARS = set("0123456789ABCDEF")
DEFAULT_CONFIG = {
    "next mac address": "",
    "auto_inc_mac": False,
}


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin() -> None:
    if is_admin():
        return
    if "debugpy" in sys.modules or "pydevd" in sys.modules:
        return
    if getattr(sys, "frozen", False):
        params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
        executable = sys.executable
    else:
        params = " ".join([f'"{os.path.abspath(sys.argv[0])}"'] + [f'"{arg}"' for arg in sys.argv[1:]])
        executable = sys.executable
    ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, APP_DIR, 1)
    sys.exit(0)


def format_mac(text: str) -> str:
    hex_chars = "".join(ch for ch in text.upper() if ch in HEX_CHARS)[:12]
    return ":".join(hex_chars[i : i + 2] for i in range(0, len(hex_chars), 2))


def mac_to_hex(mac: str) -> str:
    return "".join(ch for ch in mac.upper() if ch in HEX_CHARS)


def increment_mac(mac: str) -> str:
    hex_str = mac_to_hex(mac)
    if len(hex_str) != 12:
        return mac
    value = (int(hex_str, 16) + 1) & 0xFFFFFFFFFFFF
    return format_mac(f"{value:012X}")


def load_config() -> dict:
    if not os.path.isfile(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    config = dict(DEFAULT_CONFIG)
    if isinstance(data, dict):
        config.update(data)
    return config


def save_config(config: dict) -> None:
    payload = {
        "next mac address": mac_to_hex(str(config.get("next mac address", ""))),
        "auto_inc_mac": bool(config.get("auto_inc_mac", False)),
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


class TextHandler(logging.Handler):
    def __init__(self, widget: tk.Text) -> None:
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.widget.after(0, self._append, msg)

    def _append(self, msg: str) -> None:
        self.widget.configure(state="normal")
        self.widget.insert("end", msg + "\n")
        self.widget.see("end")
        self.widget.configure(state="disabled")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("I226 MAC Address")
        self.geometry("720x480")
        self.minsize(560, 360)

        self.mac_var = tk.StringVar()
        self.auto_inc_var = tk.BooleanVar(value=False)
        self._mac_updating = False
        self._busy = False
        self._loading_config = True

        self._build_ui()
        self._setup_logger()
        self._load_program_dat()
        self.mac_var.trace_add("write", self._on_mac_change)
        self.auto_inc_var.trace_add("write", self._on_auto_inc_change)
        self._loading_config = False
        if is_admin():
            logging.info("Application started (Administrator)")
        else:
            logging.warning("Application started without Administrator; EEUPDATE may fail")

    def _build_ui(self) -> None:
        row1 = ttk.Frame(self)
        row1.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(row1, text="MAC address").pack(side="left")
        self.mac_entry = ttk.Entry(row1, textvariable=self.mac_var)
        self.mac_entry.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row1, text="Clear", command=self._on_clear).pack(side="left")

        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=10, pady=4)
        ttk.Checkbutton(row2, text="自動遞增MAC address", variable=self.auto_inc_var).pack(side="left")

        row3 = ttk.Frame(self)
        row3.pack(fill="x", padx=10, pady=4)
        self.read_btn = ttk.Button(row3, text="讀取MAC address", command=self._on_read)
        self.read_btn.pack(side="left")
        self.write_btn = ttk.Button(row3, text="寫入MAC address", command=self._on_write)
        self.write_btn.pack(side="left", padx=8)
        self.save_log_btn = ttk.Button(row3, text="Save Log", command=self._on_save_log)
        self.save_log_btn.pack(side="left", padx=(32, 8))
        self.clear_log_btn = ttk.Button(row3, text="Clear Log", command=self._on_clear_log)
        self.clear_log_btn.pack(side="left")

        self.log_text = scrolledtext.ScrolledText(self, state="disabled", wrap="word", height=16)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(4, 10))

    def _setup_logger(self) -> None:
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(formatter)
        logger.addHandler(text_handler)

    def _load_program_dat(self) -> None:
        created = not os.path.isfile(CONFIG_FILE)
        config = load_config()
        self.mac_var.set(format_mac(str(config.get("next mac address", ""))))
        self.auto_inc_var.set(bool(config.get("auto_inc_mac", False)))
        if created:
            logging.info("Created %s", CONFIG_FILE)
        logging.info(
            "Loaded program.dat: next mac address=%s auto_inc_mac=%s",
            mac_to_hex(self.mac_var.get()) or "(empty)",
            self.auto_inc_var.get(),
        )

    def _save_program_dat(self) -> None:
        if self._loading_config:
            return
        save_config(
            {
                "next mac address": self.mac_var.get(),
                "auto_inc_mac": self.auto_inc_var.get(),
            }
        )

    def _on_auto_inc_change(self, *_args: object) -> None:
        self._save_program_dat()

    def _on_mac_change(self, *_args: object) -> None:
        if self._mac_updating:
            return
        formatted = format_mac(self.mac_var.get())
        if formatted != self.mac_var.get():
            self._mac_updating = True
            self.mac_var.set(formatted)
            self._mac_updating = False
            self.mac_entry.icursor("end")
        self._save_program_dat()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.read_btn.configure(state=state)
        self.write_btn.configure(state=state)

    def _on_clear(self) -> None:
        logging.info("Button: Clear")
        self.mac_var.set("")

    def _on_save_log(self) -> None:
        logging.info("Button: Save Log")
        path = filedialog.asksaveasfilename(
            title="Save Log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=APP_DIR,
            initialfile="log.txt",
        )
        if not path:
            logging.info("Save Log cancelled")
            return
        content = self.log_text.get("1.0", "end-1c")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
                if content and not content.endswith("\n"):
                    f.write("\n")
        except OSError:
            logging.exception("Failed to save log to %s", path)
            return
        logging.info("Saved log window to %s", path)

    def _on_clear_log(self) -> None:
        logging.info("Button: Clear Log")
        self.log_text.after(0, self._clear_log_window)

    def _clear_log_window(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_read(self) -> None:
        if self._busy:
            return
        logging.info("Button: 讀取MAC address")
        self._run_eeupdate(["/nic=1", "/ADAPTERINFO"])

    def _on_write(self) -> None:
        if self._busy:
            return
        logging.info("Button: 寫入MAC address")
        mac_hex = mac_to_hex(self.mac_var.get())
        if len(mac_hex) != 12:
            logging.error("Write aborted: MAC address must be 12 hex digits")
            return
        self._run_eeupdate(["/nic=1", f"/mac={mac_hex}"], increment_after_ok=self.auto_inc_var.get())

    def _run_eeupdate(self, args: list[str], increment_after_ok: bool = False) -> None:
        if not os.path.isfile(EEUPDATE_EXE):
            logging.error("EEUPDATE executable not found: %s", EEUPDATE_EXE)
            return
        self._set_busy(True)
        threading.Thread(target=self._run_eeupdate_worker, args=(args, increment_after_ok), daemon=True).start()

    def _run_eeupdate_worker(self, args: list[str], increment_after_ok: bool) -> None:
        cmd = [EEUPDATE_EXE, *args]
        logging.info("Run: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                cwd=APP_DIR,
                capture_output=True,
                check=False,
            )
        except Exception:
            logging.exception("Failed to run EEUPDATE")
            self.after(0, self._set_busy, False)
            return

        output = _decode(result.stdout) + _decode(result.stderr)
        output = output.rstrip()
        if output:
            logging.info("EEUPDATE output:\n%s", output)
        logging.info("EEUPDATE exit code: %s", result.returncode)

        if increment_after_ok and result.returncode == 0:
            new_mac = increment_mac(self.mac_var.get())
            self.after(0, self.mac_var.set, new_mac)
            logging.info("Auto-increment MAC address -> %s", new_mac)

        self.after(0, self._set_busy, False)


def _decode(data: bytes) -> str:
    if not data:
        return ""
    return data.decode("mbcs", errors="replace")


def main() -> None:
    os.chdir(APP_DIR)
    ensure_admin()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

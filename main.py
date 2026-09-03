"""I226 EEUpdate GUI: read/write NIC MAC address (requires Administrator)."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import psycopg

APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
EEUPDATE_EXE = os.path.join(APP_DIR, "I226_EEUPDATE", "EEUPDATEW64e.exe")
LOG_FILE = os.path.join(APP_DIR, "dev_log.txt")
CONFIG_FILE = os.path.join(APP_DIR, "program.dat")
HEX_CHARS = set("0123456789ABCDEF")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
DEFAULT_DB = {
    "username": "",
    "password": "",
    "host": "",
    "port": 25060,
    "database": "defaultdb",
    "sslmode": "verify-full",
    "sslrootcert": "ca-certificate.crt",
}
DEFAULT_CONFIG = {
    "next mac address": "",
    "auto_inc_mac": False,
    "db": dict(DEFAULT_DB),
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


def parse_macs_from_output(text: str) -> list[str]:
    found: list[str] = []
    for match in re.findall(r"(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}", text):
        hex_str = mac_to_hex(match)
        if hex_str not in found:
            found.append(hex_str)
    if found:
        return found
    for match in re.findall(r"\b[0-9A-Fa-f]{12}\b", text):
        hex_str = match.upper()
        if hex_str not in found:
            found.append(hex_str)
    return found


def _read_config_file() -> dict:
    if not os.path.isfile(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_config() -> dict:
    existing = _read_config_file()
    if not existing and not os.path.isfile(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return {
            "next mac address": "",
            "auto_inc_mac": False,
            "db": dict(DEFAULT_DB),
        }
    config = {
        "next mac address": existing.get("next mac address", ""),
        "auto_inc_mac": bool(existing.get("auto_inc_mac", False)),
        "db": dict(DEFAULT_DB),
    }
    if isinstance(existing.get("db"), dict):
        config["db"].update(existing["db"])
    return config


def save_config(updates: dict) -> None:
    payload: dict = {
        "next mac address": "",
        "auto_inc_mac": False,
        "db": dict(DEFAULT_DB),
    }
    existing = _read_config_file()
    if existing:
        payload["next mac address"] = existing.get("next mac address", "")
        payload["auto_inc_mac"] = bool(existing.get("auto_inc_mac", False))
        if isinstance(existing.get("db"), dict):
            payload["db"].update(existing["db"])
    if "next mac address" in updates:
        payload["next mac address"] = mac_to_hex(str(updates.get("next mac address", "")))
    if "auto_inc_mac" in updates:
        payload["auto_inc_mac"] = bool(updates.get("auto_inc_mac", False))
    if isinstance(updates.get("db"), dict):
        payload["db"].update(updates["db"])
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def lookup_product_unit(mac_hex: str) -> list[tuple[str, str]]:
    db = load_config()["db"]
    host = str(db.get("host") or "").strip()
    if not host:
        raise RuntimeError("DB host is empty in program.dat")
    cert = str(db.get("sslrootcert") or "").strip()
    if cert and not os.path.isabs(cert):
        cert = os.path.join(APP_DIR, cert)
    conn_kwargs = {
        "host": host,
        "port": int(db.get("port") or 25060),
        "user": str(db.get("username") or ""),
        "password": str(db.get("password") or ""),
        "dbname": str(db.get("database") or "defaultdb"),
        "connect_timeout": 10,
    }
    if cert and os.path.isfile(cert):
        conn_kwargs["sslmode"] = str(db.get("sslmode") or "verify-full")
        conn_kwargs["sslrootcert"] = cert
    else:
        conn_kwargs["sslmode"] = "require"
        if not getattr(lookup_product_unit, "_warned_no_ca", False):
            logging.warning("CA certificate not found; connecting with sslmode=require")
            lookup_product_unit._warned_no_ca = True
    with psycopg.connect(**conn_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT serial_number, notes
                FROM product_units
                WHERE regexp_replace(upper(coalesce(mac_address, '')), '[^0-9A-F]', '', 'g') = %s
                """,
                (mac_hex.upper(),),
            )
            rows = cur.fetchall()
    return [(str(row[0] or ""), str(row[1] or "")) for row in rows]


def format_unit_message(mac_hex: str, rows: list[tuple[str, str]], prefix: str = "") -> str:
    parts = [prefix, f"MAC address: {format_mac(mac_hex)}", ""]
    for index, (serial, notes) in enumerate(rows, 1):
        if len(rows) > 1:
            parts.append(f"--- record {index} ---")
        parts.append(f"serial_number: {serial or '(empty)'}")
        parts.append(f"notes: {notes or '(empty)'}")
        parts.append("")
    return "\n".join(parts).strip()


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
        db = config.get("db") or {}
        logging.info(
            "Loaded program.dat: next mac address=%s auto_inc_mac=%s db_host=%s db_name=%s",
            mac_to_hex(self.mac_var.get()) or "(empty)",
            self.auto_inc_var.get(),
            db.get("host") or "(empty)",
            db.get("database") or "(empty)",
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
        self._run_eeupdate(["/nic=1", "/ADAPTERINFO"], check_db_on_read=True)

    def _on_write(self) -> None:
        if self._busy:
            return
        logging.info("Button: 寫入MAC address")
        mac_hex = mac_to_hex(self.mac_var.get())
        if len(mac_hex) != 12:
            logging.error("Write aborted: MAC address must be 12 hex digits")
            return
        self._set_busy(True)
        threading.Thread(target=self._write_worker, args=(mac_hex,), daemon=True).start()

    def _write_worker(self, mac_hex: str) -> None:
        try:
            logging.info("Checking product_units for MAC %s", format_mac(mac_hex))
            rows = lookup_product_unit(mac_hex)
        except Exception:
            logging.exception("DB lookup failed")
            self.after(0, self._on_write_db_error)
            return
        if rows:
            logging.warning("MAC %s already exists in DB; write aborted", format_mac(mac_hex))
            self.after(0, self._on_write_mac_exists, mac_hex, rows)
            return
        if not os.path.isfile(EEUPDATE_EXE):
            logging.error("EEUPDATE executable not found: %s", EEUPDATE_EXE)
            self.after(0, self._set_busy, False)
            return
        logging.info("MAC %s not found in DB; writing to adapter", format_mac(mac_hex))
        self._run_eeupdate_worker(
            ["/nic=1", f"/mac={mac_hex}"],
            increment_after_ok=self.auto_inc_var.get(),
        )

    def _on_write_db_error(self) -> None:
        self._set_busy(False)
        messagebox.showerror(
            "資料庫連線失敗",
            "寫入前無法查詢 product_units，已中止燒錄。\n請檢查 program.dat 的 DB 設定與網路連線。",
        )

    def _on_write_mac_exists(self, mac_hex: str, rows: list[tuple[str, str]]) -> None:
        self._set_busy(False)
        messagebox.showwarning(
            "無法寫入 MAC address",
            format_unit_message(mac_hex, rows, prefix="此 MAC address 已存在於資料庫，不能燒錄。\n\n"),
        )

    def _on_read_mac_found(self, mac_hex: str, rows: list[tuple[str, str]]) -> None:
        messagebox.showinfo(
            "資料庫記錄",
            format_unit_message(mac_hex, rows, prefix="此 MAC address 在資料庫中已有記錄。\n\n"),
        )

    def _run_eeupdate(self, args: list[str], increment_after_ok: bool = False, check_db_on_read: bool = False) -> None:
        if not os.path.isfile(EEUPDATE_EXE):
            logging.error("EEUPDATE executable not found: %s", EEUPDATE_EXE)
            return
        self._set_busy(True)
        threading.Thread(
            target=self._run_eeupdate_worker,
            args=(args, increment_after_ok, check_db_on_read),
            daemon=True,
        ).start()

    def _run_eeupdate_worker(
        self,
        args: list[str],
        increment_after_ok: bool = False,
        check_db_on_read: bool = False,
    ) -> None:
        cmd = [EEUPDATE_EXE, *args]
        logging.info("Run: %s", " ".join(cmd))
        run_kwargs: dict = {
            "cwd": APP_DIR,
            "capture_output": True,
            "check": False,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            run_kwargs["startupinfo"] = startupinfo
            run_kwargs["creationflags"] = CREATE_NO_WINDOW
        try:
            result = subprocess.run(cmd, **run_kwargs)
        except Exception:
            logging.exception("Failed to run EEUPDATE")
            self.after(0, self._set_busy, False)
            return

        output = _decode(result.stdout) + _decode(result.stderr)
        output = output.rstrip()
        if output:
            logging.info("EEUPDATE output:\n%s", output)
        logging.info("EEUPDATE exit code: %s", result.returncode)

        if check_db_on_read:
            self._lookup_read_mac(output)

        if increment_after_ok and result.returncode == 0:
            new_mac = increment_mac(self.mac_var.get())
            self.after(0, self.mac_var.set, new_mac)
            logging.info("Auto-increment MAC address -> %s", new_mac)

        self.after(0, self._set_busy, False)

    def _lookup_read_mac(self, output: str) -> None:
        macs = parse_macs_from_output(output)
        if not macs:
            logging.warning("Could not parse MAC address from EEUPDATE output")
            return
        mac_hex = macs[0]
        logging.info("Parsed adapter MAC %s; checking product_units", format_mac(mac_hex))
        try:
            rows = lookup_product_unit(mac_hex)
        except Exception:
            logging.exception("DB lookup after read failed")
            return
        if not rows:
            logging.info("MAC %s not found in DB", format_mac(mac_hex))
            return
        logging.info("MAC %s found in DB (%s record(s))", format_mac(mac_hex), len(rows))
        self.after(0, self._on_read_mac_found, mac_hex, rows)


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

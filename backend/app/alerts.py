"""Alert otomatis kanggo Super Admin liwat Telegram.

Dipantau (cek saben 15 menit + nalika startup):
- Disk ngisor ambang (ALERT_DISK_PCT, default 80%)
- RAM available ngisor ambang (ALERT_RAM_PCT, default 12%)
- Backup gagal (BackupLog status != ok)
- Tenant expired / meh expired (< 3 dina)
- Startup server (info online)

Anti-spam: alert dikirim mung nalika STATUS BERUBAH (state disimpen ing
data/alert_state.json); pulih uga dikabari.
"""
import json
import shutil
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .backup import DATA_DIR
from .config import settings
from .db import GlobalSession
from .models import BackupLog, Tenant

WIB = ZoneInfo("Asia/Jakarta")
STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "alert_state.json"


def _cfg() -> tuple[str | None, str | None]:
    return (settings.alert_telegram_token or None,
            settings.alert_telegram_chat_id or None)


def send_telegram(text: str) -> dict:
    tok, chat = _cfg()
    if not tok or not chat:
        return {"ok": False, "pesan": "token/chat_id durung disetel"}
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    body = json.dumps({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"ok": r.status == 200, "pesan": f"HTTP {r.status}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "pesan": str(e)}


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_state(st: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2, ensure_ascii=False))


def _ram_available_pct() -> int:
    try:
        vals: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2 and parts[0] in ("MemTotal", "MemAvailable"):
                    vals[parts[0]] = int(parts[1].strip().split()[0])
        total = vals.get("MemTotal", 0)
        avail = vals.get("MemAvailable", 0)
        return round(avail * 100 / total) if total else 100
    except Exception:  # noqa: BLE001
        return 100


def _disk_pct() -> tuple[int, str]:
    u = shutil.disk_usage("/")
    return round(u.used * 100 / u.total), f"{u.free / 1024**3:.1f}G sisa"


def check_system() -> list[dict]:
    """Priksa kabeh kondisi saiki → list masalah sing ana."""
    out: list[dict] = []

    dpct, ddesc = _disk_pct()
    disk_th = settings.alert_disk_pct
    if dpct >= disk_th:
        out.append({"jenis": "disk", "level": "kritis" if dpct >= 90 else "waspada",
                    "teks": f"Disk {dpct}% ({ddesc}) — ambang {disk_th}%"})

    rpct = _ram_available_pct()
    ram_th = settings.alert_ram_pct
    if rpct < ram_th:
        out.append({"jenis": "ram", "level": "kritis",
                    "teks": f"RAM available mung {rpct}% — ambang {ram_th}%"})

    with GlobalSession() as gs:
        gagal = (gs.query(BackupLog)
                 .filter(BackupLog.status != "ok")
                 .order_by(BackupLog.waktu.desc()).first())
        if gagal:
            out.append({"jenis": "backup", "level": "kritis",
                        "teks": f"Backup gagal ({gagal.waktu:%Y-%m-%d %H:%M}): "
                                f"{gagal.pesan[:120]}"})
        hari_ini = datetime.now(WIB).date()
        expired = [
            t for t in gs.query(Tenant).all()
            if t.status in ("active", "trial") and t.masa_langganan_hingga
            and t.masa_langganan_hingga < hari_ini + timedelta(days=3)
        ]
        if expired:
            nm = ", ".join(t.kode for t in expired[:5])
            out.append({"jenis": "langganan",
                        "level": "waspada" if len(expired) <= 3 else "kritis",
                        "teks": f"{len(expired)} tenant expired/langsir (<3 dina): {nm}"})
    return out


def run_alert_check(force: bool = False) -> dict:
    """Cek kondisi; kirim mung yen status berubah (anti-spam)."""
    tok, chat = _cfg()
    if not tok or not chat:
        return {"ok": False, "pesan": "alert durung disetel (token/chat_id)",
                "kirim": []}
    issues = check_system()
    st = _load_state()
    st["last_check"] = datetime.now(WIB).isoformat(timespec="minutes")

    aktif = {i["jenis"] for i in issues}
    pesan_list: list[str] = []
    for i in issues:
        if force or not st.get(f"alert_{i['jenis']}"):
            pesan_list.append(i["teks"])
            st[f"alert_{i['jenis']}"] = True
    # pulih: jenis sing biyen alert saiki normal
    for k in list(st):
        if k.startswith("alert_") and k[6:] not in aktif and st[k]:
            st[k] = False
            pesan_list.append(f"✅ Pulih: {k[6:]} saiki normal")

    if not pesan_list:
        _save_state(st)
        return {"ok": True, "pesan": "Kabeh normal — ora ana pesan", "kirim": []}

    teks = "⚠️ *Alert Madrasah Platform*\n" + "\n".join("• " + p for p in pesan_list)
    res = send_telegram(teks)
    st["last_alert"] = datetime.now(WIB).isoformat(timespec="minutes")
    _save_state(st)
    return {"ok": res["ok"], "pesan": res["pesan"], "kirim": pesan_list}


def kirim_startup() -> dict:
    """Notifikasi server online (dipanggil nalika backend start)."""
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        jam = int(secs // 3600)
        menit = int(secs % 3600 // 60)
        uptime = f"{jam}j {menit}m"
    except Exception:  # noqa: BLE001
        uptime = "?"
    return send_telegram(
        f"✅ *Madrasah Platform online* — backend start (uptime {uptime})")


def server_status() -> dict:
    """Status server: RAM, disk, swap, uptime, load, ukuran DB, backup pungkasan."""
    def _kb(key: str) -> int:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2 and parts[0] == key:
                        return int(parts[1].strip().split()[0])
        except Exception:  # noqa: BLE001
            pass
        return 0

    total = _kb("MemTotal")
    avail = _kb("MemAvailable")
    swap_total = _kb("SwapTotal")
    swap_free = _kb("SwapFree")
    ram_pct = round((total - avail) * 100 / total) if total else 0
    swap_used = swap_total - swap_free

    u = shutil.disk_usage("/")
    disk_pct = round(u.used * 100 / u.total)

    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        jam, menit = int(secs // 3600), int(secs % 3600 // 60)
        uptime = f"{jam}j {menit}m"
    except Exception:  # noqa: BLE001
        uptime = "?"

    try:
        loadavg = open("/proc/loadavg").read().split()
        load = ", ".join(loadavg[:3])
    except Exception:  # noqa: BLE001
        load = "-"

    db_total = 0
    db_count = 0
    try:
        for p in list(Path(DATA_DIR).glob("global.db")) + \
                list(Path(DATA_DIR).glob("tenants/*.db")):
            db_total += p.stat().st_size
            db_count += 1
    except Exception:  # noqa: BLE001
        pass

    last_backup = None
    with GlobalSession() as gs:
        lb = gs.query(BackupLog).order_by(BackupLog.waktu.desc()).first()
        if lb:
            last_backup = {"waktu": lb.waktu.isoformat(timespec="minutes"),
                           "status": lb.status, "nama": lb.nama_file}

    return {
        "ram": {"total_mb": round(total / 1024), "avail_mb": round(avail / 1024),
                "used_pct": ram_pct},
        "disk": {"total_gb": round(u.total / 1024**3, 1),
                 "free_gb": round(u.free / 1024**3, 1),
                 "used_pct": disk_pct},
        "swap": {"total_mb": round(swap_total / 1024),
                 "used_mb": round(swap_used / 1024)},
        "uptime": uptime,
        "load": load,
        "db": {"jumlah": db_count, "total_mb": round(db_total / 1024**2, 1)},
        "last_backup": last_backup,
    }


def status() -> dict:
    tok, chat = _cfg()
    st = _load_state()
    return {
        "disetel": bool(tok and chat),
        "chat_id": chat or "-",
        "ambang_disk": settings.alert_disk_pct,
        "ambang_ram": settings.alert_ram_pct,
        "last_check": st.get("last_check"),
        "last_alert": st.get("last_alert"),
        "aktif": {k[6:]: v for k, v in st.items() if k.startswith("alert_")},
    }

"""
collector_linux.py — ITAM Predictive Health Collector (Linux/Ubuntu Server)
Collects hardware telemetry and service health, sends to central ITAM server.
No WMI dependency — works on any Linux system with psutil and requests.
"""
import json
import os
import socket
import subprocess
import time
from datetime import datetime, timezone

import psutil
import requests

# ── Config ───────────────────────────────────────────────────────────────────
DEFAULT_SERVER_URL = "http://192.168.1.159:5000/api/report"
SAMPLE_COUNT = 4
SAMPLE_INTERVAL = 2  # seconds


# ── Agent Config ─────────────────────────────────────────────────────────────
def load_config():
    """Load agent_config.json from script directory or cwd."""
    for path in [os.path.join(os.path.dirname(__file__), "agent_config.json"), "agent_config.json"]:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Error reading config: {e}")
    return {}


CONFIG = load_config()
SERVER_URL = CONFIG.get("server_url", DEFAULT_SERVER_URL)


# ── Identity ─────────────────────────────────────────────────────────────────
def get_asset_tag():
    """Use config asset_tag, fallback to machine-id, then hostname."""
    if CONFIG.get("asset_tag"):
        return CONFIG["asset_tag"].strip()

    # Linux machine-id (unique per install)
    try:
        with open("/etc/machine-id") as f:
            machine_id = f.read().strip()
            if machine_id:
                return machine_id[:16].upper()  # First 16 chars
    except Exception:
        pass

    return socket.gethostname()


def get_device_type():
    """Detect VM vs physical machine."""
    try:
        result = subprocess.run(
            ["systemd-detect-virt"], capture_output=True, text=True, timeout=3
        )
        virt = result.stdout.strip()
        if virt and virt != "none":
            return f"server-vm"
    except Exception:
        pass
    return "server"


# ── CPU ───────────────────────────────────────────────────────────────────────
def get_cpu():
    print(f"[~] Sampling CPU/RAM ({SAMPLE_COUNT}x{SAMPLE_INTERVAL}s)...")
    cpu_samples, ram_samples = [], []

    for i in range(SAMPLE_COUNT):
        cpu_samples.append(psutil.cpu_percent(interval=SAMPLE_INTERVAL))
        ram_samples.append(psutil.virtual_memory().percent)
        print(f"    sample {i+1}/{SAMPLE_COUNT}: CPU {cpu_samples[-1]:.1f}%  RAM {ram_samples[-1]:.1f}%")

    cpu_avg = round(sum(cpu_samples) / len(cpu_samples), 1)
    cpu_peak = round(max(cpu_samples), 1)

    # CPU temperature via sensors (if lm-sensors is installed)
    temp = None
    try:
        temps = psutil.sensors_temperatures()
        for key in ["coretemp", "cpu_thermal", "k10temp", "acpitz"]:
            if key in temps and temps[key]:
                temp = round(temps[key][0].current, 1)
                break
    except Exception:
        pass

    return {
        "usage_percent": cpu_avg,
        "usage_peak_percent": cpu_peak,
        "usage_sample_count": SAMPLE_COUNT,
        "temperature_celsius": temp,
        "throttling_events": None,  # Not available on Linux without specialized tools
    }


# ── Memory ────────────────────────────────────────────────────────────────────
def get_memory():
    vm = psutil.virtual_memory()
    return {
        "usage_percent": round(vm.percent, 1),
        "usage_peak_percent": round(vm.percent, 1),
        "available_gb": round(vm.available / (1024 ** 3), 2),
        "sample_count": 1,
    }


# ── Disks ─────────────────────────────────────────────────────────────────────
def get_disks():
    disks = []
    seen_devices = set()

    for part in psutil.disk_partitions(all=False):
        # Skip non-physical mounts
        if any(skip in part.fstype for skip in ["tmpfs", "devtmpfs", "squashfs", "overlay"]):
            continue

        device = part.device
        if device in seen_devices:
            continue
        seen_devices.add(device)

        try:
            usage = psutil.disk_usage(part.mountpoint)
            usage_pct = round(usage.used / usage.total * 100, 1)
        except Exception:
            continue

        disk = {
            "drive": part.mountpoint,
            "usage_percent": usage_pct,
            "smart_status": "Unknown",
            "read_errors": None,
            "write_errors": None,
            "temperature_celsius": None,
            "model": None,
            "serial_number": None,
            "power_on_hours": None,
            "wear_percent": None,
            "predict_failure": None,
            "telemetry_note": None,
        }

        # Try smartctl for deeper SMART data
        try:
            dev_name = device.replace("/dev/", "")
            result = subprocess.run(
                ["sudo", "smartctl", "-A", "-j", device],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode in [0, 4]:
                smart_data = json.loads(result.stdout)
                attrs = {a["id"]: a for a in smart_data.get("ata_smart_attributes", {}).get("table", [])}
                # Temperature (attr 194)
                if 194 in attrs:
                    disk["temperature_celsius"] = attrs[194].get("raw", {}).get("value")
                # Power-on hours (attr 9)
                if 9 in attrs:
                    disk["power_on_hours"] = attrs[9].get("raw", {}).get("value")
                # SSD wear (attr 177 or 231)
                for wear_id in [177, 231]:
                    if wear_id in attrs:
                        disk["wear_percent"] = attrs[wear_id].get("value")
                        break
                # SMART health
                health = smart_data.get("smart_status", {})
                disk["smart_status"] = "Healthy" if health.get("passed") else "PredictedFailure"
                disk["predict_failure"] = not health.get("passed", True)
        except Exception:
            disk["telemetry_note"] = "smartctl not available or requires sudo"

        disks.append(disk)

    return disks


# ── System ────────────────────────────────────────────────────────────────────
def get_system():
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_hours = round(uptime_seconds / 3600, 1)

    # Last OS update — check apt history log
    last_update = None
    try:
        result = subprocess.run(
            ["stat", "-c", "%y", "/var/lib/apt/periodic/update-success-stamp"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            last_update = result.stdout.strip().split(".")[0]  # Remove microseconds
    except Exception:
        pass

    # OS version
    os_version = None
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME"):
                    os_version = line.split("=")[1].strip().strip('"')
                    break
    except Exception:
        pass

    return {
        "uptime_hours": uptime_hours,
        "last_os_update": last_update,
        "os_version": os_version,
    }


# ── Services ─────────────────────────────────────────────────────────────────
DEFAULT_SERVICE_DEFS = [
    {"name": "MySQL (Billing DB)",    "host": "127.0.0.1", "port": 3306, "process_name": "mysqld"},
    {"name": "Redis (Session Cache)", "host": "127.0.0.1", "port": 6379, "process_name": "redis-server"},
    {"name": "Nginx (Web Portal)",    "host": "127.0.0.1", "port": 80,   "process_name": "nginx"},
]


def get_services():
    if CONFIG.get("check_services") is False:
        return []

    service_defs = CONFIG.get("services", DEFAULT_SERVICE_DEFS)

    # Pre-scan processes once
    found_procs = {}
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            p_name = proc.info["name"].lower()
            cmd_str = " ".join(proc.info["cmdline"] or []).lower()
            for svc in service_defs:
                svc_name = svc["name"]
                if svc_name in found_procs:
                    continue
                target = svc.get("process_name", "").lower()
                if not target or target not in p_name:
                    continue
                keyword = svc.get("cmd_keyword", "").lower()
                if keyword and keyword not in cmd_str:
                    continue
                found_procs[svc_name] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    services = []
    for svc in service_defs:
        svc_name = svc["name"]
        result = {
            "name": svc_name,
            "status": "down",
            "response_time_ms": None,
            "process_cpu_percent": None,
            "process_memory_mb": None,
            "error": None,
        }
        # TCP check
        host = svc.get("host", "127.0.0.1")
        port = svc.get("port")
        if port:
            t0 = time.time()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    s.connect((host, port))
                result["status"] = "up"
                result["response_time_ms"] = round((time.time() - t0) * 1000, 1)
            except Exception:
                result["error"] = "Port unreachable"

        # Process metrics
        proc = found_procs.get(svc_name)
        if proc:
            try:
                result["process_cpu_percent"] = proc.cpu_percent(interval=0.1)
                result["process_memory_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
            except Exception:
                pass

        services.append(result)

    return services


# ── Collect ───────────────────────────────────────────────────────────────────
def collect():
    device_type = get_device_type()
    return {
        "asset_tag": get_asset_tag(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "device_type": device_type,
        "cpu": get_cpu(),
        "memory": get_memory(),
        "disks": get_disks(),
        "system": get_system(),
        "battery": None,  # Servers don't have batteries
        "services": get_services(),
    }


# ── Send ──────────────────────────────────────────────────────────────────────
def send_to_server(snapshot):
    try:
        resp = requests.post(SERVER_URL, json=snapshot, timeout=5)
        if resp.status_code == 200:
            print(f"[OK] Data sent to {SERVER_URL}")
        else:
            print(f"[!] Server responded with status {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[!] Could not connect to {SERVER_URL}")
        print("    Make sure the Flask server is running on your Windows machine.")
    except Exception as e:
        print(f"[!] Error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ITAM Linux Collector — Djezzy Server Edition")
    print("=" * 55)
    print(f"  Asset Tag : {get_asset_tag()}")
    print(f"  Server URL: {SERVER_URL}")
    print("=" * 55)

    snapshot = collect()
    print("\n[Snapshot JSON]")
    print(json.dumps(snapshot, indent=2))
    print("\n[Sending to ITAM server...]")
    send_to_server(snapshot)
    print("\nDone.")

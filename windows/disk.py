import os
import subprocess
import json
import shutil

# Add smartmontools to PATH so smartctl is found
SMARTMONTOOLS_BIN = r"C:\Program Files\smartmontools\bin"
os.environ["PATH"] = SMARTMONTOOLS_BIN + os.pathsep + os.environ.get("PATH", "")

from pySMART import DeviceList

def smartctl_json(device_name):
    """Call smartctl -a -j directly and return parsed JSON."""
    smartctl = shutil.which("smartctl")
    if not smartctl:
        return {}
    try:
        result = subprocess.run(
            [smartctl, "-a", "-j", device_name],
            capture_output=True, text=True, timeout=10, check=False
        )
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except Exception:
        return {}

def get_disk_info(dev):
    device_path = f"/dev/{dev.name}" if not dev.name.startswith("/") else dev.name
    data = smartctl_json(device_path)
    nvme     = data.get("nvme_smart_health_information_log", {})
    temp_obj = data.get("temperature", {})
    poh_obj  = data.get("power_on_time", {})
    ata_attrs = {a["id"]: a for a in data.get("ata_smart_attributes", {}).get("table", [])}

    temperature    = nvme.get("temperature") or temp_obj.get("current") or dev.temperature
    power_on_hours = nvme.get("power_on_hours") or poh_obj.get("hours")

    # ── Media errors: NVMe vs ATA ──────────────────────
    if nvme:
        # NVMe drive
        media_errors = nvme.get("media_errors")
    else:
        # ATA/SATA drive — use SMART attribute 197 (pending sectors)
        # and attribute 5 (reallocated sectors)
        attr_197 = ata_attrs.get(197, {}).get("raw", {}).get("value", 0)
        attr_5   = ata_attrs.get(5,   {}).get("raw", {}).get("value", 0)
        media_errors = (attr_197 or 0) + (attr_5 or 0)
    # ───────────────────────────────────────────────────
    endurance       = data.get("endurance_used", {})
    pct_used        = endurance.get("current_percent") or nvme.get("percentage_used")
    wear_remaining  = (100 - pct_used) if pct_used is not None else None
    available_spare = (data.get("spare_available") or {}).get("current_percent")

    host_reads  = nvme.get("host_reads")
    host_writes = nvme.get("host_writes")

    return {
        "temperature":     temperature,
        "power_on_hours":  power_on_hours,
        "media_errors":    media_errors,
        "wear_remaining":  wear_remaining,
        "available_spare": available_spare,
        "host_reads":      host_reads,
        "host_writes":     host_writes,
    }

devices = DeviceList().devices

for dev in devices:
    info = get_disk_info(dev)
    print(f"Device          : {dev.name}")
    print(f"Model           : {dev.model}")
    print(f"Serial          : {dev.serial}")
    print(f"Health          : {dev.assessment}")
    print(f"Temperature     : {info['temperature']} °C")
    print(f"Power-On Hours  : {info['power_on_hours']} hrs")
    print(f"Media Errors    : {info['media_errors'] if info['media_errors'] is not None else 'N/A'}  (0 = healthy)")
    print(f"Wear Remaining  : {info['wear_remaining']} %")
    print(f"Available Spare : {info['available_spare']} %")
    print(f"Host Reads      : {info['host_reads']:,}" if info['host_reads'] else "Host Reads      : N/A")
    print(f"Host Writes     : {info['host_writes']:,}" if info['host_writes'] else "Host Writes     : N/A")
    print()

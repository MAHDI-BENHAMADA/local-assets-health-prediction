"""
simulate_laptops.py — Generate realistic fake laptop telemetry for ITAM demo.
Sends 3 virtual laptop snapshots to the Flask server, each with slightly
different hardware profiles to simulate a real enterprise fleet.

Usage:
    python simulate_laptops.py
"""
import json
import random
import requests
from datetime import datetime, timezone

SERVER_URL = "http://localhost:5000/api/report"

# ── Laptop Profiles ──────────────────────────────────────────────────────────
LAPTOPS = [
    {
        "asset_tag": "LAPTOP-HR-001",
        "device_type": "laptop",
        "profile": "old_laptop",       # Old machine, high disk, outdated OS
        "cpu_range": (25, 55),
        "ram_range": (60, 78),
        "disk_usage": 74.2,
        "battery_health": 62,
        "cycles": 680,
        "uptime_hours": 120,
        "last_update_days_ago": 95,
        "os_version": "Windows 10 Pro 21H2",
        "disk_model": "TOSHIBA MQ01ABD100",
        "disk_serial": "Y8A0T12FS",
        "power_on_hours": 18200,
        "wear_percent": 78,
        "disk_temp": 34,
    },
    {
        "asset_tag": "LAPTOP-FINANCE-002",
        "device_type": "laptop",
        "profile": "healthy_laptop",    # Relatively new, all good
        "cpu_range": (12, 30),
        "ram_range": (45, 60),
        "disk_usage": 52.1,
        "battery_health": 91,
        "cycles": 210,
        "uptime_hours": 8,
        "last_update_days_ago": 12,
        "os_version": "Windows 11 Pro 23H2",
        "disk_model": "Samsung SSD 980 PRO 512GB",
        "disk_serial": "S6B2NJ0T312456",
        "power_on_hours": 3400,
        "wear_percent": 97,
        "disk_temp": 28,
    },
    {
        "asset_tag": "LAPTOP-IT-003",
        "device_type": "laptop",
        "profile": "at_risk_laptop",    # Degraded battery, high disk, old OS
        "cpu_range": (35, 70),
        "ram_range": (78, 92),
        "disk_usage": 91.8,
        "battery_health": 38,
        "cycles": 1120,
        "uptime_hours": 840,
        "last_update_days_ago": 220,
        "os_version": "Windows 10 Pro 20H2",
        "disk_model": "WDC WD5000LPVX",
        "disk_serial": "WD-WX41A74P2856",
        "power_on_hours": 28500,
        "wear_percent": 45,
        "disk_temp": 42,
    },
]


def generate_snapshot(laptop):
    """Build a realistic telemetry snapshot for the given laptop profile."""
    cpu_avg = round(random.uniform(*laptop["cpu_range"]), 1)
    cpu_peak = round(cpu_avg + random.uniform(5, 20), 1)
    ram_avg = round(random.uniform(*laptop["ram_range"]), 1)
    ram_peak = round(ram_avg + random.uniform(2, 8), 1)

    # Calculate last_os_update date string
    from datetime import timedelta
    update_date = datetime.now() - timedelta(days=laptop["last_update_days_ago"])
    update_str = update_date.strftime("%-m/%-d/%Y") if hasattr(update_date, 'strftime') else update_date.strftime("%m/%d/%Y")

    snapshot = {
        "asset_tag": laptop["asset_tag"],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "device_type": laptop["device_type"],
        "cpu": {
            "usage_percent": cpu_avg,
            "usage_peak_percent": cpu_peak,
            "usage_sample_count": 6,
            "temperature_celsius": round(random.uniform(38, 55), 1),
            "throttling_events": 0 if laptop["profile"] != "at_risk_laptop" else random.randint(2, 8),
        },
        "memory": {
            "usage_percent": ram_avg,
            "usage_peak_percent": ram_peak,
            "available_gb": round(16 * (1 - ram_avg / 100), 2),
            "sample_count": 6,
        },
        "disks": [
            {
                "drive": "C:",
                "usage_percent": laptop["disk_usage"],
                "smart_status": "Healthy",
                "read_errors": 0,
                "write_errors": 0,
                "temperature_celsius": laptop["disk_temp"],
                "model": laptop["disk_model"],
                "serial_number": laptop["disk_serial"],
                "power_on_hours": laptop["power_on_hours"],
                "wear_percent": laptop["wear_percent"],
                "predict_failure": False,
                "telemetry_note": None,
            }
        ],
        "system": {
            "uptime_hours": laptop["uptime_hours"],
            "last_os_update": update_str,
            "os_version": laptop["os_version"],
        },
        "battery": {
            "health_percent": laptop["battery_health"],
            "cycle_count": laptop["cycles"],
            "charging_status": random.choice(["charging", "discharging"]),
        },
        "services": [],  # Laptops don't run monitored services
    }

    return snapshot


def main():
    print("=" * 55)
    print("  ITAM Laptop Fleet Simulator")
    print("  Generating telemetry for 3 virtual laptops...")
    print("=" * 55)

    for laptop in LAPTOPS:
        snapshot = generate_snapshot(laptop)
        tag = laptop["asset_tag"]
        profile = laptop["profile"]

        print(f"\n[{tag}] ({profile})")
        print(f"  CPU: {snapshot['cpu']['usage_percent']}% | RAM: {snapshot['memory']['usage_percent']}%")
        print(f"  Disk: {snapshot['disks'][0]['usage_percent']}% | Battery: {snapshot['battery']['health_percent']}%")
        print(f"  OS Update: {laptop['last_update_days_ago']} days ago | Uptime: {laptop['uptime_hours']}h")

        try:
            resp = requests.post(SERVER_URL, json=snapshot, timeout=5)
            if resp.status_code == 200:
                print(f"  -> Sent OK")
            else:
                print(f"  -> Server error: {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"  -> FAILED: Cannot reach {SERVER_URL}")
        except Exception as e:
            print(f"  -> Error: {e}")

    print("\n" + "=" * 55)
    print("  Done! Check your ITAM dashboard.")
    print("=" * 55)


if __name__ == "__main__":
    main()

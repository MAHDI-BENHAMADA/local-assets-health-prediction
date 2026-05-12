import pickle
import numpy as np
import os
from datetime import datetime, timezone

# --- CONFIG ---
MODELS_DIR          = "models"
HEALTH_MODEL_FILE   = os.path.join(MODELS_DIR, "health_model.pkl")
LIFETIME_MODEL_FILE = os.path.join(MODELS_DIR, "lifetime_model.pkl")
ENCODER_FILE        = os.path.join(MODELS_DIR, "label_encoder.pkl")
FEATURES_FILE       = os.path.join(MODELS_DIR, "feature_columns.pkl")


# ─────────────────────────────────────────────
# LOAD MODELS (once at startup)
# ─────────────────────────────────────────────

def load_models():
    with open(HEALTH_MODEL_FILE, "rb") as f:
        health_model = pickle.load(f)
    with open(LIFETIME_MODEL_FILE, "rb") as f:
        lifetime_model = pickle.load(f)
    with open(ENCODER_FILE, "rb") as f:
        label_encoder = pickle.load(f)
    with open(FEATURES_FILE, "rb") as f:
        feature_columns = pickle.load(f)
    return health_model, lifetime_model, label_encoder, feature_columns


# ─────────────────────────────────────────────
# SNAPSHOT → FEATURE VECTOR
# ─────────────────────────────────────────────

def snapshot_to_features(snapshot, feature_columns):
    """
    Convert a raw collector.py snapshot dict into
    the feature vector the models expect.
    """
    device_type = snapshot.get("device_type", "desktop")
    device_type_encoded = 1 if device_type == "laptop" else 0

    # estimate device age from collected_at if available
    # fallback to 24 months (2 years) if unknown
    try:
        collected_at = datetime.fromisoformat(snapshot["collected_at"])
        # we don't know manufacture date, so we estimate from uptime as a proxy
        uptime_hours = snapshot.get("system", {}).get("uptime_hours", 0) or 0
        age_months = min(uptime_hours / 730, 84)  # rough estimate, cap at 7 years
    except Exception:
        age_months = 24

    cpu        = snapshot.get("cpu", {}) or {}
    memory     = snapshot.get("memory", {}) or {}
    battery    = snapshot.get("battery") or {}
    system     = snapshot.get("system", {}) or {}

    # battery fields (-1 means desktop / not applicable)
    battery_health  = battery.get("health_percent", -1) if battery else -1
    battery_cycles  = battery.get("cycle_count", -1) if battery else -1
    charging_status = battery.get("charging_status", None) if battery else None
    battery_charging_encoded = (
        1 if charging_status == "charging"
        else 0 if charging_status == "discharging"
        else -1
    )
    battery_health  = battery_health  if battery_health  is not None else -1
    battery_cycles  = battery_cycles  if battery_cycles  is not None else -1

    # parse days since last update
    last_update_str = system.get("last_os_update", None)
    try:
        last_update = datetime.strptime(last_update_str, "%m/%d/%Y")
        days_since_update = (datetime.now() - last_update).days
    except Exception:
        days_since_update = 60  # fallback: assume 2 months

    feature_map = {
        "device_type_encoded"      : device_type_encoded,
        "age_months"               : age_months,
        "cpu_usage_percent"        : cpu.get("usage_percent", 50) or 50,
        "cpu_temperature_celsius"  : cpu.get("temperature_celsius", 60) or 60,
        "memory_usage_percent"     : memory.get("usage_percent", 50) or 50,
        "memory_available_gb"      : memory.get("available_gb", 4) or 4,
        "memory_total_gb"          : (memory.get("available_gb", 4) or 4) / max(1 - (memory.get("usage_percent", 50) or 50) / 100, 0.01),
        "battery_health_percent"   : battery_health,
        "battery_cycle_count"      : battery_cycles,
        "battery_charging_encoded" : battery_charging_encoded,
        "system_uptime_hours"      : system.get("uptime_hours", 24) or 24,
        "days_since_last_update"   : days_since_update,
    }

    # build feature vector in the correct order
    vector = [feature_map[col] for col in feature_columns]
    return np.array(vector).reshape(1, -1)


# ─────────────────────────────────────────────
# RISK LEVEL HELPER
# ─────────────────────────────────────────────

def get_risk_level(health_percent):
    if health_percent >= 80:
        return "Low"
    elif health_percent >= 60:
        return "Medium"
    elif health_percent >= 40:
        return "High"
    else:
        return "Critical"


def get_concerns(snapshot, health_percent, remaining_months):
    """Generate human-readable concern messages based on metrics."""
    concerns = []

    cpu = snapshot.get("cpu", {}) or {}
    memory = snapshot.get("memory", {}) or {}
    battery = snapshot.get("battery") or {}
    system = snapshot.get("system", {}) or {}

    temp = cpu.get("temperature_celsius")
    if temp and temp > 80:
        concerns.append(f"CPU temperature is critically high ({temp}°C)")
    elif temp and temp > 65:
        concerns.append(f"CPU temperature is elevated ({temp}°C)")

    mem_usage = memory.get("usage_percent")
    if mem_usage and mem_usage > 85:
        concerns.append(f"Memory usage is very high ({mem_usage}%)")

    if battery:
        bat_health = battery.get("health_percent")
        bat_cycles = battery.get("cycle_count")
        if bat_health and bat_health < 60:
            concerns.append(f"Battery health is low ({bat_health}%)")
        if bat_cycles and bat_cycles > 500:
            concerns.append(f"High battery cycle count ({bat_cycles} cycles)")

    uptime = system.get("uptime_hours")
    if uptime and uptime > 720:
        concerns.append(f"Device hasn't been restarted in over {int(uptime/24)} days")

    if remaining_months < 6:
        concerns.append("Device is approaching end of life")

    if not concerns:
        concerns.append("No major issues detected")

    return concerns


# ─────────────────────────────────────────────
# MAIN PREDICT FUNCTION
# ─────────────────────────────────────────────

# load models once when module is imported
_health_model, _lifetime_model, _label_encoder, _feature_columns = load_models()


def predict(snapshot: dict) -> dict:
    """
    Takes a raw snapshot from collector.py and returns
    health %, remaining lifetime, risk level, and concerns.

    Args:
        snapshot: dict — the JSON snapshot from collector.py

    Returns:
        dict with prediction results
    """
    features = snapshot_to_features(snapshot, _feature_columns)

    health_percent   = float(np.clip(_health_model.predict(features)[0], 0, 100))
    remaining_months = float(np.clip(_lifetime_model.predict(features)[0], 0, 96))

    return {
        "health_percent"   : round(health_percent, 1),
        "remaining_months" : round(remaining_months, 1),
        "risk_level"       : get_risk_level(health_percent),
        "concerns"         : get_concerns(snapshot, health_percent, remaining_months),
    }


# ─────────────────────────────────────────────
# TEST WITH SAMPLE SNAPSHOTS
# ─────────────────────────────────────────────

if __name__ == "__main__":

    test_cases = [
        {
            "name": "Healthy Laptop",
            "snapshot": {
                "asset_tag": "LAPTOP-001",
                "device_type": "laptop",
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "cpu": {"usage_percent": 25, "temperature_celsius": 52},
                "memory": {"usage_percent": 45, "available_gb": 8.8},
                "battery": {"health_percent": 91, "cycle_count": 120, "charging_status": "charging"},
                "system": {"uptime_hours": 12, "last_os_update": "04/01/2026"},
            }
        },
        {
            "name": "Aging Laptop (needs attention)",
            "snapshot": {
                "asset_tag": "LAPTOP-002",
                "device_type": "laptop",
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "cpu": {"usage_percent": 75, "temperature_celsius": 82},
                "memory": {"usage_percent": 78, "available_gb": 3.5},
                "battery": {"health_percent": 58, "cycle_count": 520, "charging_status": "discharging"},
                "system": {"uptime_hours": 900, "last_os_update": "01/10/2026"},
            }
        },
        {
            "name": "Critical Desktop",
            "snapshot": {
                "asset_tag": "DESKTOP-001",
                "device_type": "desktop",
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "cpu": {"usage_percent": 92, "temperature_celsius": 95},
                "memory": {"usage_percent": 91, "available_gb": 1.4},
                "battery": None,
                "system": {"uptime_hours": 3200, "last_os_update": "08/15/2025"},
            }
        },
    ]

    print("=" * 55)
    print("  PC Health Predictor — Test Results")
    print("=" * 55)

    for case in test_cases:
        result = predict(case["snapshot"])
        print(f"\n  📋 {case['name']}")
        print(f"     Health Score    : {result['health_percent']}%")
        print(f"     Remaining Life  : {result['remaining_months']} months")
        print(f"     Risk Level      : {result['risk_level']}")
        print(f"     Concerns:")
        for concern in result["concerns"]:
            print(f"       ⚠ {concern}")

    print("\n" + "=" * 55)

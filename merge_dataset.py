import pandas as pd
import numpy as np

# --- CONFIG ---
SIMULATED_FILE  = "dataset.csv"
DISK_FILE       = "disk_dataset.csv"
OUTPUT_FILE     = "final_dataset.csv"
RANDOM_SEED     = 42

np.random.seed(RANDOM_SEED)

print("=" * 55)
print("  Merging Simulated + Backblaze Disk Data")
print("=" * 55)


# ─────────────────────────────────────────────
# STEP 1 — LOAD BOTH DATASETS
# ─────────────────────────────────────────────

print("\n[1/5] Loading datasets...")

sim  = pd.read_csv(SIMULATED_FILE)
disk = pd.read_csv(DISK_FILE)

print(f"      Simulated records : {len(sim):,}")
print(f"      Disk records      : {len(disk):,}")


# ─────────────────────────────────────────────
# STEP 2 — RANDOMLY PAIR THEM
# ─────────────────────────────────────────────
# Since the two datasets are from different sources
# we pair each simulated device with a random disk record.
# This is valid because disk health is independent of
# CPU/memory/battery in real life too.

print("\n[2/5] Pairing simulated devices with real disk records...")

# Sample disk records to match simulated dataset size
disk_sampled = disk.sample(
    n=len(sim), replace=True, random_state=RANDOM_SEED
).reset_index(drop=True)

# Combine side by side
combined = pd.concat([
    sim.reset_index(drop=True),
    disk_sampled[[
        "disk_age_months",
        "disk_temperature_celsius",
        "read_errors",
        "write_errors",
        "pending_sectors",
        "failure",
        "disk_health_score",
        "disk_remaining_months",
    ]]
], axis=1)

print(f"      Combined shape: {combined.shape}")


# ─────────────────────────────────────────────
# STEP 3 — RECALCULATE OVERALL HEALTH
# ─────────────────────────────────────────────
# Now that we have disk health, we incorporate it
# into the overall device health score.

print("\n[3/5] Recalculating overall health with disk included...")

def recalculate_health(row):
    device_type  = row["device_type"]
    disk_health  = row["disk_health_score"]

    # weights now include disk
    if device_type == "laptop":
        weights = {
            "cpu"    : 0.25,
            "memory" : 0.15,
            "battery": 0.25,
            "system" : 0.10,
            "disk"   : 0.25,
        }
    else:  # desktop
        weights = {
            "cpu"    : 0.30,
            "memory" : 0.20,
            "battery": 0.00,
            "system" : 0.20,
            "disk"   : 0.30,
        }

    health = (
        row["cpu_score"]     * weights["cpu"]    +
        row["memory_score"]  * weights["memory"] +
        row["battery_score"] * weights["battery"]+
        row["system_score"]  * weights["system"] +
        disk_health          * weights["disk"]
    )

    # if disk physically failed → cap overall health at 30
    if row["failure"] == 1:
        health = min(health, 30)

    return round(np.clip(health, 0, 100), 1)


def recalculate_remaining(row):
    """
    Final remaining lifetime = min of all component lifetimes.
    The weakest component determines the device's fate.
    """
    candidates = [
        row["remaining_months"],       # from simulated (CPU/memory/battery)
        row["disk_remaining_months"],  # from Backblaze (disk)
    ]

    # if disk failed → 0 months
    if row["failure"] == 1:
        return 0.0

    return round(max(0, min(candidates)), 1)


combined["overall_health_percent"] = combined.apply(recalculate_health, axis=1)
combined["remaining_months"]       = combined.apply(recalculate_remaining, axis=1)

print(f"      Avg overall health : {combined['overall_health_percent'].mean():.1f}%")
print(f"      Avg remaining      : {combined['remaining_months'].mean():.1f} months")
print(f"      Devices with failed disk: {combined['failure'].sum():,}")


# ─────────────────────────────────────────────
# STEP 4 — FINALIZE COLUMNS
# ─────────────────────────────────────────────

print("\n[4/5] Finalizing columns...")

# Encode device type
combined["device_type_encoded"]     = (combined["device_type"] == "laptop").astype(int)
combined["battery_charging_encoded"] = combined["battery_charging_status"].map(
    {"charging": 1, "discharging": 0}
).fillna(-1)
combined["battery_health_percent"]  = combined["battery_health_percent"].fillna(-1)
combined["battery_cycle_count"]     = combined["battery_cycle_count"].fillna(-1)

FINAL_COLUMNS = [
    # device info
    "device_type",
    "device_type_encoded",
    "age_months",
    # cpu
    "cpu_usage_percent",
    "cpu_temperature_celsius",
    # memory
    "memory_usage_percent",
    "memory_available_gb",
    "memory_total_gb",
    # battery
    "battery_health_percent",
    "battery_cycle_count",
    "battery_charging_encoded",
    # system
    "system_uptime_hours",
    "days_since_last_update",
    # disk (real Backblaze data)
    "disk_age_months",
    "disk_temperature_celsius",
    "read_errors",
    "write_errors",
    "pending_sectors",
    "disk_health_score",
    # component scores
    "cpu_score",
    "memory_score",
    "battery_score",
    "system_score",
    # ← TARGETS
    "overall_health_percent",
    "remaining_months",
]

final = combined[FINAL_COLUMNS]


# ─────────────────────────────────────────────
# STEP 5 — SAVE
# ─────────────────────────────────────────────

print("\n[5/5] Saving final dataset...")
final.to_csv(OUTPUT_FILE, index=False)

print(f"      Records  : {len(final):,}")
print(f"      Features : {len(FINAL_COLUMNS) - 2} (excl. targets)")
print(f"      Targets  : overall_health_percent, remaining_months")
print(f"      Saved to : {OUTPUT_FILE}")

print("\n" + "=" * 55)
print("  ✅ Merge complete!")
print("  Simulated data  → CPU, memory, battery, system")
print("  Backblaze data  → Disk health (real world)")
print("\n  Next: re-run train_model.py with final_dataset.csv")
print("=" * 55)

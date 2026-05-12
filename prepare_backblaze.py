import pandas as pd
import numpy as np
import os

# --- CONFIG ---
BACKBLAZE_FILE = "harddrive.csv"   # your downloaded file
OUTPUT_FILE    = "disk_dataset.csv"
SAMPLE_SIZE    = 50000             # rows to sample (keeps it manageable)
RANDOM_SEED    = 42

print("=" * 55)
print("  Backblaze Dataset Preparation")
print("=" * 55)

# ─────────────────────────────────────────────
# STEP 1 — LOAD ONLY THE COLUMNS WE NEED
# ─────────────────────────────────────────────

COLUMNS_NEEDED = [
    "date",
    "serial_number",
    "model",
    "failure",
    "smart_5_raw",    # reallocated sectors (read errors proxy)
    "smart_9_raw",    # power-on hours (disk age)
    "smart_187_raw",  # uncorrectable errors (write errors proxy)
    "smart_190_raw",  # temperature (celsius)
    "smart_194_raw",  # temperature alternative (some drives use this)
    "smart_197_raw",  # pending sectors (wear proxy)
    "smart_198_raw",  # uncorrectable sectors (additional wear)
]

print(f"\n[1/5] Loading only needed columns from {BACKBLAZE_FILE}...")
print("      (This may take a moment for a large file...)")

df = pd.read_csv(
    BACKBLAZE_FILE,
    usecols=lambda c: c in COLUMNS_NEEDED,
    low_memory=False
)

print(f"      Loaded {len(df):,} rows  |  {df.shape[1]} columns")


# ─────────────────────────────────────────────
# STEP 2 — CLEAN & RENAME
# ─────────────────────────────────────────────

print("\n[2/5] Cleaning data...")

# Rename columns to friendly names
df.rename(columns={
    "smart_5_raw"  : "read_errors",
    "smart_9_raw"  : "power_on_hours",
    "smart_187_raw": "write_errors",
    "smart_190_raw": "temperature_190",
    "smart_194_raw": "temperature_194",
    "smart_197_raw": "pending_sectors",
    "smart_198_raw": "uncorrectable_sectors",
}, inplace=True)

# Use smart_194 as temperature fallback when smart_190 is missing
if "temperature_190" in df.columns and "temperature_194" in df.columns:
    df["disk_temperature_celsius"] = df["temperature_190"].combine_first(df["temperature_194"])
elif "temperature_190" in df.columns:
    df["disk_temperature_celsius"] = df["temperature_190"]
elif "temperature_194" in df.columns:
    df["disk_temperature_celsius"] = df["temperature_194"]
else:
    df["disk_temperature_celsius"] = np.nan

df.drop(columns=["temperature_190", "temperature_194"], errors="ignore", inplace=True)

# Convert to numeric (some columns may have NAs stored as strings)
numeric_cols = [
    "read_errors", "power_on_hours", "write_errors",
    "disk_temperature_celsius", "pending_sectors",
    "uncorrectable_sectors", "failure"
]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Drop rows where ALL smart metrics are missing
smart_cols = ["read_errors", "power_on_hours", "write_errors",
              "disk_temperature_celsius", "pending_sectors"]
df.dropna(subset=[c for c in smart_cols if c in df.columns], how="all", inplace=True)

print(f"      Rows after cleaning: {len(df):,}")
print(f"      Failed drives: {df['failure'].sum():,} ({df['failure'].mean()*100:.2f}%)")


# ─────────────────────────────────────────────
# STEP 3 — ENGINEER FEATURES
# ─────────────────────────────────────────────

print("\n[3/5] Engineering features...")

# Power-on hours → months
df["disk_age_months"] = (df["power_on_hours"].fillna(0) / 730).round(1)

# Clamp temperature to valid range
df["disk_temperature_celsius"] = df["disk_temperature_celsius"].clip(0, 70)

# Fill missing errors with 0 (no errors reported = 0)
df["read_errors"]            = df["read_errors"].fillna(0).clip(0, 10000)
df["write_errors"]           = df["write_errors"].fillna(0).clip(0, 10000)
df["pending_sectors"]        = df["pending_sectors"].fillna(0).clip(0, 10000)
df["uncorrectable_sectors"]  = df["uncorrectable_sectors"].fillna(0) if "uncorrectable_sectors" in df.columns else 0


# ─────────────────────────────────────────────
# STEP 4 — CALCULATE DISK HEALTH SCORE (0-100)
# ─────────────────────────────────────────────

print("\n[4/5] Calculating disk health scores...")

def score_disk(row):
    score = 100.0

    # Temperature penalty
    temp = row.get("disk_temperature_celsius", np.nan)
    if pd.notna(temp):
        if temp > 55:
            score -= 30
        elif temp > 45:
            score -= 15
        elif temp > 40:
            score -= 5

    # Read errors penalty
    re = row.get("read_errors", 0) or 0
    if re > 100:
        score -= 30
    elif re > 10:
        score -= 15
    elif re > 0:
        score -= 5

    # Write errors penalty
    we = row.get("write_errors", 0) or 0
    if we > 50:
        score -= 25
    elif we > 5:
        score -= 10
    elif we > 0:
        score -= 3

    # Pending sectors penalty
    ps = row.get("pending_sectors", 0) or 0
    if ps > 10:
        score -= 25
    elif ps > 0:
        score -= 10

    # Age penalty
    age = row.get("disk_age_months", 0) or 0
    if age > 60:
        score -= 20
    elif age > 36:
        score -= 10
    elif age > 24:
        score -= 5

    # If the drive actually failed → health is near 0
    if row.get("failure", 0) == 1:
        score = min(score, 15)

    return round(max(0, min(100, score)), 1)


def estimate_disk_remaining(row):
    """Estimate remaining months based on health and age"""
    health    = row.get("disk_health_score", 50)
    age       = row.get("disk_age_months", 0) or 0
    failure   = row.get("failure", 0)
    max_life  = 72  # avg HDD lifespan ~6 years

    if failure == 1:
        return 0.0
    if health < 20:
        return round(np.random.uniform(0, 3), 1)
    if health < 40:
        return round(np.random.uniform(1, 12), 1)

    remaining = max_life - age
    # scale by health
    remaining = remaining * (health / 100)
    return round(max(0, min(remaining, 60)), 1)


df["disk_health_score"]      = df.apply(score_disk, axis=1)
df["disk_remaining_months"]  = df.apply(estimate_disk_remaining, axis=1)

print(f"      Avg disk health   : {df['disk_health_score'].mean():.1f}%")
print(f"      Avg remaining     : {df['disk_remaining_months'].mean():.1f} months")


# ─────────────────────────────────────────────
# STEP 5 — SAMPLE & SAVE
# ─────────────────────────────────────────────

print(f"\n[5/5] Sampling {SAMPLE_SIZE:,} records and saving...")

# Balance: keep all failures + sample healthy drives
failures  = df[df["failure"] == 1]
healthy   = df[df["failure"] == 0].sample(
    min(SAMPLE_SIZE - len(failures), len(df[df["failure"] == 0])),
    random_state=RANDOM_SEED
)
df_final = pd.concat([failures, healthy]).sample(frac=1, random_state=RANDOM_SEED)

# Keep only useful columns for the model
final_cols = [
    "serial_number", "model",
    "disk_age_months",
    "disk_temperature_celsius",
    "read_errors",
    "write_errors",
    "pending_sectors",
    "failure",
    "disk_health_score",
    "disk_remaining_months",
]
df_final = df_final[[c for c in final_cols if c in df_final.columns]]
df_final.to_csv(OUTPUT_FILE, index=False)

print(f"      Saved {len(df_final):,} records → {OUTPUT_FILE}")
print(f"      Failed drives in sample : {df_final['failure'].sum():,}")
print(f"      Healthy drives in sample: {(df_final['failure']==0).sum():,}")

print("\n" + "=" * 55)
print("  ✅ Backblaze data ready!")
print("  Next: run merge_dataset.py to combine with simulated data")
print("=" * 55)

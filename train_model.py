import pandas as pd
import numpy as np
import pickle
import os
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb

# --- CONFIG ---
DATASET_FILE = "dataset.csv"
MODELS_DIR   = "models"
HEALTH_MODEL_FILE   = os.path.join(MODELS_DIR, "health_model.pkl")
LIFETIME_MODEL_FILE = os.path.join(MODELS_DIR, "lifetime_model.pkl")
ENCODER_FILE        = os.path.join(MODELS_DIR, "label_encoder.pkl")
FEATURES_FILE       = os.path.join(MODELS_DIR, "feature_columns.pkl")

os.makedirs(MODELS_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# STEP 1 — LOAD & PREPROCESS
# ─────────────────────────────────────────────

print("=" * 50)
print("  PC Health Prediction — Model Trainer")
print("=" * 50)
print()
print("[1/5] Loading dataset...")

df = pd.read_csv(DATASET_FILE)
print(f"      Loaded {len(df):,} records  |  {df.shape[1]} columns")

# Encode device_type: laptop=1, desktop=0
le = LabelEncoder()
df["device_type_encoded"] = le.fit_transform(df["device_type"])

# Encode battery_charging_status: charging=1, discharging=0, missing=-1
df["battery_charging_encoded"] = df["battery_charging_status"].map(
    {"charging": 1, "discharging": 0}
).fillna(-1)

# Fill missing battery values with -1 (means desktop / not applicable)
df["battery_health_percent"]  = df["battery_health_percent"].fillna(-1)
df["battery_cycle_count"]     = df["battery_cycle_count"].fillna(-1)

print("      Missing values handled ✓")


# ─────────────────────────────────────────────
# STEP 2 — DEFINE FEATURES & TARGETS
# ─────────────────────────────────────────────

print()
print("[2/5] Preparing features...")

FEATURE_COLUMNS = [
    "device_type_encoded",
    "age_months",
    # CPU
    "cpu_usage_percent",
    "cpu_temperature_celsius",
    # Memory
    "memory_usage_percent",
    "memory_available_gb",
    "memory_total_gb",
    # Battery
    "battery_health_percent",
    "battery_cycle_count",
    "battery_charging_encoded",
    # System
    "system_uptime_hours",
    "days_since_last_update",
]

TARGET_HEALTH   = "overall_health_percent"
TARGET_LIFETIME = "remaining_months"

X = df[FEATURE_COLUMNS]
y_health   = df[TARGET_HEALTH]
y_lifetime = df[TARGET_LIFETIME]

print(f"      Features  : {len(FEATURE_COLUMNS)}")
print(f"      Samples   : {len(X):,}")

# Train/test split (80% train, 20% test)
X_train, X_test, yh_train, yh_test, yl_train, yl_test = train_test_split(
    X, y_health, y_lifetime, test_size=0.2, random_state=42
)
print(f"      Train set : {len(X_train):,} records")
print(f"      Test set  : {len(X_test):,} records")


# ─────────────────────────────────────────────
# STEP 3 — TRAIN HEALTH MODEL (Random Forest)
# ─────────────────────────────────────────────

print()
print("[3/5] Training health % model (Random Forest)...")

health_model = RandomForestRegressor(
    n_estimators=200,
    max_depth=15,
    min_samples_split=5,
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1,
)
health_model.fit(X_train, yh_train)

yh_pred = health_model.predict(X_test)
health_mae = mean_absolute_error(yh_test, yh_pred)
health_r2  = r2_score(yh_test, yh_pred)

print(f"      MAE : {health_mae:.2f}%  (avg error in health prediction)")
print(f"      R²  : {health_r2:.4f}   (1.0 = perfect)")

# Feature importance
importances = pd.Series(
    health_model.feature_importances_, index=FEATURE_COLUMNS
).sort_values(ascending=False)
print("      Top features:")
for feat, score in importances.head(5).items():
    print(f"        {feat:<35} {score:.3f}")


# ─────────────────────────────────────────────
# STEP 4 — TRAIN LIFETIME MODEL (XGBoost)
# ─────────────────────────────────────────────

print()
print("[4/5] Training remaining lifetime model (XGBoost)...")

lifetime_model = xgb.XGBRegressor(
    n_estimators=300,
    max_depth=8,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1,
    verbosity=0,
)
lifetime_model.fit(
    X_train, yl_train,
    eval_set=[(X_test, yl_test)],
    verbose=False,
)

yl_pred = lifetime_model.predict(X_test)
lifetime_mae = mean_absolute_error(yl_test, yl_pred)
lifetime_r2  = r2_score(yl_test, yl_pred)

print(f"      MAE : {lifetime_mae:.2f} months  (avg error in lifetime prediction)")
print(f"      R²  : {lifetime_r2:.4f}          (1.0 = perfect)")

importances_xgb = pd.Series(
    lifetime_model.feature_importances_, index=FEATURE_COLUMNS
).sort_values(ascending=False)
print("      Top features:")
for feat, score in importances_xgb.head(5).items():
    print(f"        {feat:<35} {score:.3f}")


# ─────────────────────────────────────────────
# STEP 5 — SAVE MODELS
# ─────────────────────────────────────────────

print()
print("[5/5] Saving models...")

with open(HEALTH_MODEL_FILE, "wb") as f:
    pickle.dump(health_model, f)
print(f"      Health model   → {HEALTH_MODEL_FILE}")

with open(LIFETIME_MODEL_FILE, "wb") as f:
    pickle.dump(lifetime_model, f)
print(f"      Lifetime model → {LIFETIME_MODEL_FILE}")

with open(ENCODER_FILE, "wb") as f:
    pickle.dump(le, f)
print(f"      Label encoder  → {ENCODER_FILE}")

with open(FEATURES_FILE, "wb") as f:
    pickle.dump(FEATURE_COLUMNS, f)
print(f"      Feature list   → {FEATURES_FILE}")

print()
print("=" * 50)
print("  ✅ Training complete! Models saved to /models")
print("=" * 50)
print()
print("  Next step: run predict.py to test predictions")

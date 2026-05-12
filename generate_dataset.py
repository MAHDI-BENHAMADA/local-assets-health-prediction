import random
import csv
import math

# --- CONFIG ---
NUM_DEVICES = 10000        # number of device records to generate
OUTPUT_FILE = "dataset.csv"
RANDOM_SEED = 42

random.seed(RANDOM_SEED)


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))

def add_noise(value, noise_pct=0.05):
    """Add small random noise to a value (±noise_pct)"""
    noise = value * noise_pct * random.uniform(-1, 1)
    return value + noise


# ─────────────────────────────────────────────
# COMPONENT GENERATORS
# ─────────────────────────────────────────────

def generate_cpu(age_months):
    """
    CPU degrades via thermal paste drying out over time.
    Temperature rises ~0.3°C per month after month 18.
    High usage accelerates degradation.
    """
    base_temp = 52.0
    usage = random.uniform(10, 95)

    # thermal paste degradation kicks in after 18 months
    paste_degradation = max(0, (age_months - 18)) * 0.3
    # high usage adds heat
    usage_heat = (usage / 100) * 15
    # random variation
    temp = base_temp + paste_degradation + usage_heat + random.uniform(-5, 5)
    temp = clamp(temp, 35, 105)

    return {
        "cpu_usage_percent": round(usage, 1),
        "cpu_temperature_celsius": round(temp, 1),
    }


def generate_memory(age_months):
    """
    Memory is the most stable component.
    Usage grows slightly as OS bloat increases over time.
    """
    total_gb = random.choice([8, 16, 32])
    base_usage = random.uniform(30, 60)
    # slight increase in usage over time (OS bloat)
    age_bloat = age_months * 0.1
    usage = clamp(base_usage + age_bloat + random.uniform(-5, 5), 10, 98)
    available_gb = round(total_gb * (1 - usage / 100), 1)

    return {
        "memory_usage_percent": round(usage, 1),
        "memory_available_gb": available_gb,
        "memory_total_gb": total_gb,
    }


def generate_battery(age_months, device_type):
    """
    Battery loses ~1% health every 35 cycles.
    Average user does ~1 full cycle per day = ~30/month.
    Health degrades faster with more cycles and age.
    """
    if device_type == "desktop":
        return {
            "battery_health_percent": None,
            "battery_cycle_count": None,
            "battery_charging_status": None,
        }

    # cycles accumulate over time (25-40 per month depending on usage)
    cycles_per_month = random.uniform(25, 40)
    cycle_count = int(age_months * cycles_per_month)
    cycle_count = clamp(cycle_count, 0, 1500)

    # health degrades ~1% per 35 cycles
    health = 100 - (cycle_count / 35)
    health = clamp(health + random.uniform(-3, 3), 20, 100)

    charging_status = random.choice(["charging", "discharging"])

    return {
        "battery_health_percent": round(health, 1),
        "battery_cycle_count": cycle_count,
        "battery_charging_status": charging_status,
    }


def generate_system(age_months):
    """
    Uptime grows with usage habits.
    Days since last update increases over time (users skip updates).
    """
    # uptime: some people restart daily, others never
    restart_habit = random.choice(["daily", "weekly", "monthly", "never"])
    if restart_habit == "daily":
        uptime_hours = random.uniform(1, 24)
    elif restart_habit == "weekly":
        uptime_hours = random.uniform(24, 168)
    elif restart_habit == "monthly":
        uptime_hours = random.uniform(168, 720)
    else:
        uptime_hours = random.uniform(720, 4320)

    # days since last update grows with age (people update less over time)
    base_days_since_update = random.uniform(0, 30)
    age_factor = age_months * random.uniform(0.5, 2.0)
    days_since_update = clamp(base_days_since_update + age_factor, 0, 365)

    return {
        "system_uptime_hours": round(uptime_hours, 1),
        "days_since_last_update": round(days_since_update, 0),
    }


# ─────────────────────────────────────────────
# HEALTH SCORE CALCULATION
# ─────────────────────────────────────────────

def score_cpu(cpu):
    """Score CPU health 0-100"""
    temp = cpu["cpu_temperature_celsius"]
    usage = cpu["cpu_usage_percent"]

    # temperature score (weight: 70%)
    if temp < 60:
        temp_score = 100
    elif temp < 75:
        temp_score = 100 - ((temp - 60) / 15) * 30   # 100 → 70
    elif temp < 90:
        temp_score = 70 - ((temp - 75) / 15) * 40    # 70 → 30
    else:
        temp_score = 30 - ((temp - 90) / 15) * 30    # 30 → 0

    # usage score (weight: 30%)
    if usage < 50:
        usage_score = 100
    elif usage < 80:
        usage_score = 100 - ((usage - 50) / 30) * 40
    else:
        usage_score = 60 - ((usage - 80) / 20) * 60

    return clamp(temp_score * 0.7 + usage_score * 0.3, 0, 100)


def score_memory(memory):
    """Score memory health 0-100"""
    usage = memory["memory_usage_percent"]
    available = memory["memory_available_gb"]

    if usage < 60:
        usage_score = 100
    elif usage < 80:
        usage_score = 100 - ((usage - 60) / 20) * 40
    else:
        usage_score = 60 - ((usage - 80) / 20) * 60

    if available > 4:
        avail_score = 100
    elif available > 2:
        avail_score = 100 - ((4 - available) / 2) * 40
    else:
        avail_score = clamp((available / 2) * 60, 0, 60)

    return clamp(usage_score * 0.6 + avail_score * 0.4, 0, 100)


def score_battery(battery, device_type):
    """Score battery health 0-100"""
    if device_type == "desktop":
        return 100  # desktops don't have batteries, not a concern

    health = battery["battery_health_percent"]
    cycles = battery["battery_cycle_count"]

    if health > 80:
        health_score = 100
    elif health > 60:
        health_score = 100 - ((80 - health) / 20) * 40
    else:
        health_score = clamp((health / 60) * 60, 0, 60)

    if cycles < 300:
        cycle_score = 100
    elif cycles < 500:
        cycle_score = 100 - ((cycles - 300) / 200) * 40
    else:
        cycle_score = clamp(60 - ((cycles - 500) / 500) * 60, 0, 60)

    return clamp(health_score * 0.7 + cycle_score * 0.3, 0, 100)


def score_system(system):
    """Score system health 0-100"""
    uptime = system["system_uptime_hours"]
    days_no_update = system["days_since_last_update"]

    if uptime < 168:       # less than 1 week
        uptime_score = 100
    elif uptime < 720:     # less than 1 month
        uptime_score = 80
    elif uptime < 2160:    # less than 3 months
        uptime_score = 50
    else:
        uptime_score = 20

    if days_no_update < 30:
        update_score = 100
    elif days_no_update < 90:
        update_score = 100 - ((days_no_update - 30) / 60) * 50
    else:
        update_score = clamp(50 - ((days_no_update - 90) / 275) * 50, 0, 50)

    return clamp(uptime_score * 0.4 + update_score * 0.6, 0, 100)


def calculate_overall_health(cpu_score, memory_score, battery_score, system_score, device_type):
    """
    Weighted average of all component scores.
    Disk is handled separately (Backblaze data).
    """
    if device_type == "laptop":
        weights = {
            "cpu": 0.35,
            "memory": 0.20,
            "battery": 0.30,
            "system": 0.15,
        }
    else:  # desktop
        weights = {
            "cpu": 0.40,
            "memory": 0.30,
            "battery": 0.00,
            "system": 0.30,
        }

    health = (
        cpu_score * weights["cpu"] +
        memory_score * weights["memory"] +
        battery_score * weights["battery"] +
        system_score * weights["system"]
    )
    return clamp(health, 0, 100)


# ─────────────────────────────────────────────
# REMAINING LIFETIME CALCULATION
# ─────────────────────────────────────────────

def calculate_remaining_months(health_percent, age_months, device_type, battery):
    """
    Estimate remaining lifetime in months.
    Based on current health and degradation rate so far.
    Average PC lifespan: 48-72 months (4-6 years).
    """
    # base lifespan varies by device type
    if device_type == "laptop":
        max_lifespan = random.uniform(48, 72)
    else:
        max_lifespan = random.uniform(60, 96)

    # if health is very low, remaining life is short regardless of age
    if health_percent < 30:
        remaining = random.uniform(0, 6)
    elif health_percent < 50:
        remaining = random.uniform(3, 18)
    else:
        # estimate based on degradation rate
        if age_months > 0:
            # how much health lost per month so far
            initial_health = 100
            degradation_rate = (initial_health - health_percent) / age_months
            if degradation_rate > 0:
                months_until_zero = health_percent / degradation_rate
                remaining = clamp(months_until_zero, 0, max_lifespan - age_months)
            else:
                remaining = max_lifespan - age_months
        else:
            remaining = max_lifespan

    # battery on laptops can cut remaining life short
    if device_type == "laptop" and battery["battery_health_percent"] is not None:
        bat_health = battery["battery_health_percent"]
        if bat_health < 40:
            remaining = min(remaining, 6)
        elif bat_health < 60:
            remaining = min(remaining, 18)

    return clamp(round(remaining, 1), 0, 96)


# ─────────────────────────────────────────────
# MAIN GENERATOR
# ─────────────────────────────────────────────

def generate_record():
    device_type = random.choice(["laptop", "desktop"])
    # age in months: 0 to 84 (7 years)
    age_months = random.uniform(0, 84)

    # generate component data
    cpu = generate_cpu(age_months)
    memory = generate_memory(age_months)
    battery = generate_battery(age_months, device_type)
    system = generate_system(age_months)

    # score each component
    cpu_score = score_cpu(cpu)
    memory_score = score_memory(memory)
    battery_score = score_battery(battery, device_type)
    system_score = score_system(system)

    # overall health
    overall_health = calculate_overall_health(
        cpu_score, memory_score, battery_score, system_score, device_type
    )
    # add small noise to health
    overall_health = clamp(overall_health + random.uniform(-2, 2), 0, 100)

    # remaining lifetime
    remaining_months = calculate_remaining_months(
        overall_health, age_months, device_type, battery
    )

    return {
        # identifiers
        "device_type": device_type,
        "age_months": round(age_months, 1),
        # cpu
        "cpu_usage_percent": cpu["cpu_usage_percent"],
        "cpu_temperature_celsius": cpu["cpu_temperature_celsius"],
        # memory
        "memory_usage_percent": memory["memory_usage_percent"],
        "memory_available_gb": memory["memory_available_gb"],
        "memory_total_gb": memory["memory_total_gb"],
        # battery (None for desktops)
        "battery_health_percent": battery["battery_health_percent"],
        "battery_cycle_count": battery["battery_cycle_count"],
        "battery_charging_status": battery["battery_charging_status"],
        # system
        "system_uptime_hours": system["system_uptime_hours"],
        "days_since_last_update": system["days_since_last_update"],
        # component scores (useful for analysis)
        "cpu_score": round(cpu_score, 1),
        "memory_score": round(memory_score, 1),
        "battery_score": round(battery_score, 1),
        "system_score": round(system_score, 1),
        # ← TARGETS (what the model will predict)
        "overall_health_percent": round(overall_health, 1),
        "remaining_months": remaining_months,
    }


def main():
    print(f"Generating {NUM_DEVICES} device records...")

    records = [generate_record() for _ in range(NUM_DEVICES)]

    # write to CSV
    fieldnames = records[0].keys()
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"✅ Dataset saved to {OUTPUT_FILE}")
    print(f"   Total records : {len(records)}")
    print(f"   Laptops       : {sum(1 for r in records if r['device_type'] == 'laptop')}")
    print(f"   Desktops      : {sum(1 for r in records if r['device_type'] == 'desktop')}")
    print(f"\n   Avg health    : {sum(r['overall_health_percent'] for r in records) / len(records):.1f}%")
    print(f"   Avg remaining : {sum(r['remaining_months'] for r in records) / len(records):.1f} months")


if __name__ == "__main__":
    main()

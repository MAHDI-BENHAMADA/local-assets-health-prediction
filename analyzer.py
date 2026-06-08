import json
from datetime import datetime, timezone

def parse_date(date_str):
    if not date_str:
        return None
    try:
        # Date format: "M/D/YYYY" or "M/D/YY"
        return datetime.strptime(date_str, "%m/%d/%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            # Also try without zero padding or two digit years via %Y if possible; let's stick to simple iso fallback
            parts = date_str.split("/")
            if len(parts) == 3:
                return datetime(int(parts[2]), int(parts[0]), int(parts[1]), tzinfo=timezone.utc)
            return datetime.fromisoformat(date_str)
        except Exception:
            return None

def calculate_device_health(snapshot: dict) -> dict:
    total_score = 0
    triggered_rules = []
    recommended_actions = []
    
    collected_at_str = snapshot.get("collected_at")
    try:
        collected_at = datetime.fromisoformat(collected_at_str)
    except Exception:
        collected_at = datetime.now(timezone.utc)
        
    disks = snapshot.get("disks", [])
    
    # Deduplicate disks by serial_number
    seen_serials = set()
    unique_disks = []
    for disk in disks:
        serial = disk.get("serial_number")
        if serial:
            if serial not in seen_serials:
                seen_serials.add(serial)
                unique_disks.append(disk)
        else:
            unique_disks.append(disk)
            
    # DISK Rules
    has_high_disk_temp = False
    has_low_wear = False
    has_high_disk_usage = False
    has_high_power_on_hours = False
    
    for disk in unique_disks:
        drive_name = disk.get("drive", "Unknown")
        
        # D1
        wear = disk.get("wear_percent")
        if wear is not None:
            if wear <= 10:
                mult = 1.0; action = "Schedule SSD replacement within 30 days"
            elif wear <= 20:
                mult = 0.7; action = "Schedule SSD replacement within 30 days"
            elif wear <= 40:
                mult = 0.4; action = "Add SSD to replacement watchlist"
                has_low_wear = True
            else:
                mult = 0.0; action = None
            
            if mult > 0:
                total_score += 40 * mult
                triggered_rules.append({"rule_id": "D1", "label": f"SSD Remaining Life", "value": wear, "score_contribution": 40 * mult, "note": f"{wear}% life remaining"})
                if action and action not in recommended_actions:
                    recommended_actions.append(action)
            if wear <= 40: has_low_wear = True

        # D2
        predict_failure = disk.get("predict_failure")
        if predict_failure is not None:
            if predict_failure:
                total_score += 45
                triggered_rules.append({"rule_id": "D2", "label": f"SMART Failure Prediction", "value": predict_failure, "score_contribution": 45, "note": "SMART predicts failure"})
                action = "IMMEDIATE: Back up data and replace SSD"
                if action not in recommended_actions:
                    recommended_actions.append(action)
                    
        # D3
        usage = disk.get("usage_percent")
        if usage is not None:
            if usage >= 95: mult = 1.0
            elif usage >= 90: mult = 0.6
            elif usage >= 80: mult = 0.3
            else: mult = 0.0
                
            if mult > 0:
                total_score += 10 * mult
                triggered_rules.append({"rule_id": "D3", "label": f"Disk Space Usage", "value": usage, "score_contribution": 10 * mult, "note": f"{usage}% used"})
                if usage >= 90:
                    action = "Free disk space — aim for at least 20% free"
                    if action not in recommended_actions: recommended_actions.append(action)
            if usage >= 90: has_high_disk_usage = True
                
        # D4
        read_errors = disk.get("read_errors", 0) or 0
        write_errors = disk.get("write_errors", 0) or 0
        if read_errors > 0 or write_errors > 0:
            total_score += 35
            triggered_rules.append({"rule_id": "D4", "label": f"Read/Write Errors", "value": f"R:{read_errors} W:{write_errors}", "score_contribution": 35, "note": "I/O errors detected"})
            action = "Run full SMART diagnostic — I/O errors detected"
            if action not in recommended_actions: recommended_actions.append(action)
                
        # D5
        disk_temp = disk.get("temperature_celsius")
        if disk_temp is not None:
            if disk_temp >= 60: mult = 1.0
            elif disk_temp >= 50: mult = 0.5
            else: mult = 0.0
                
            if mult > 0:
                total_score += 25 * mult
                triggered_rules.append({"rule_id": "D5", "label": f"Disk Temperature", "value": disk_temp, "score_contribution": 25 * mult, "note": f"{disk_temp}°C"})
                if disk_temp >= 50:
                    action = "Check drive ventilation and chassis airflow"
                    if action not in recommended_actions: recommended_actions.append(action)
            if disk_temp >= 50: has_high_disk_temp = True
                
        # D6
        hours = disk.get("power_on_hours")
        if hours is not None:
            if hours >= 35000: mult = 1.0
            elif hours >= 25000: mult = 0.6
            elif hours >= 15000: mult = 0.3
            else: mult = 0.0
                
            if mult > 0:
                total_score += 30 * mult
                triggered_rules.append({"rule_id": "D6", "label": f"Power-On Hours", "value": hours, "score_contribution": 30 * mult, "note": f"{hours} hours"})
                if hours >= 25000:
                    action = "Disk approaching end of rated lifetime"
                    if action not in recommended_actions: recommended_actions.append(action)
            if hours >= 15000: has_high_power_on_hours = True

    # BATT
    has_poor_battery_health = False
    has_high_cycle_count = False
    device_type = snapshot.get("device_type")
    battery = snapshot.get("battery")
    if device_type == "laptop" and battery is not None:
        # B1
        health = battery.get("health_percent")
        if health is not None:
            if health <= 40: mult = 1.0
            elif health <= 60: mult = 0.6
            elif health <= 75: mult = 0.3
            else: mult = 0.0
            if mult > 0:
                total_score += 35 * mult
                triggered_rules.append({"rule_id": "B1", "label": "Battery Health", "value": health, "score_contribution": 35 * mult, "note": f"{health}% health"})
                if health <= 60:
                    action = "Battery replacement recommended"
                    if action not in recommended_actions: recommended_actions.append(action)
            if health <= 60: has_poor_battery_health = True
                
        # B2
        cycles = battery.get("cycle_count")
        if cycles is not None:
            if cycles >= 1000: mult = 1.0
            elif cycles >= 700: mult = 0.6
            elif cycles >= 500: mult = 0.3
            else: mult = 0.0
            if mult > 0:
                total_score += 25 * mult
                triggered_rules.append({"rule_id": "B2", "label": "Battery Cycle Count", "value": cycles, "score_contribution": 25 * mult, "note": f"{cycles} cycles"})
                if cycles >= 700:
                    action = "Battery near end of rated cycle life"
                    if action not in recommended_actions: recommended_actions.append(action)
            if cycles >= 500: has_high_cycle_count = True

    # CPU
    has_high_cpu_temp = False
    cpu = snapshot.get("cpu", {})
    cpu_temp = cpu.get("temperature_celsius")
    if cpu_temp is not None:
        if cpu_temp >= 95: mult = 1.0
        elif cpu_temp >= 85: mult = 0.6
        elif cpu_temp >= 75: mult = 0.3
        else: mult = 0.0
        if mult > 0:
            total_score += 30 * mult
            triggered_rules.append({"rule_id": "C1", "label": "CPU Temperature", "value": cpu_temp, "score_contribution": 30 * mult, "note": f"{cpu_temp}°C"})
            if cpu_temp >= 85:
                action = "Check CPU cooling — clean fan and reapply thermal paste"
                if action not in recommended_actions: recommended_actions.append(action)
        if cpu_temp >= 85: has_high_cpu_temp = True
            
    cpu_usage = cpu.get("usage_percent")
    if cpu_usage is not None:
        if cpu_usage >= 90:
            total_score += 8  # lowered: sustained high CPU is a workload signal, not a hardware failure
            triggered_rules.append({"rule_id": "C2", "label": "CPU Usage (avg)", "value": cpu_usage, "score_contribution": 8, "note": f"{cpu_usage}% avg — may reflect heavy workload"})
            
    throttling = cpu.get("throttling_events")
    if throttling is not None:
        if throttling > 10: mult = 1.0
        elif throttling > 0: mult = 0.5
        else: mult = 0.0
        if mult > 0:
            total_score += 20 * mult
            triggered_rules.append({"rule_id": "C3", "label": "Throttling Events", "value": throttling, "score_contribution": 20 * mult, "note": f"{throttling} events"})
            action = "CPU thermal throttling detected — inspect cooling"
            if action not in recommended_actions: recommended_actions.append(action)

    # MEM
    mem = snapshot.get("memory", {})
    mem_usage = mem.get("usage_percent")
    if mem_usage is not None:
        if mem_usage >= 95: mult = 1.0
        elif mem_usage >= 85: mult = 0.5
        else: mult = 0.0
        if mult > 0:
            total_score += 10 * mult  # lowered: RAM pressure is mostly a workload signal
            triggered_rules.append({"rule_id": "M1", "label": "RAM Usage (avg)", "value": mem_usage, "score_contribution": 10 * mult, "note": f"{mem_usage}% avg — may reflect active workload"})
            
    mem_avail = mem.get("available_gb")
    if mem_avail is not None:
        if mem_avail < 0.5: mult = 1.0
        elif mem_avail <= 1.0: mult = 0.5
        else: mult = 0.0
        if mult > 0:
            total_score += 12 * mult  # lowered: low available RAM can be transient
            triggered_rules.append({"rule_id": "M2", "label": "Available RAM (avg)", "value": mem_avail, "score_contribution": 12 * mult, "note": f"{mem_avail:.2f} GB avg available"})

    # SYS
    has_old_os = False
    sys_info = snapshot.get("system", {})
    last_update_str = sys_info.get("last_os_update")
    if last_update_str:
        last_update = parse_date(last_update_str)
        if last_update:
            days_ago = (collected_at.replace(tzinfo=None) - last_update.replace(tzinfo=None)).days
            if days_ago > 180: mult = 1.0
            elif days_ago >= 90: mult = 0.5
            else: mult = 0.0
            if mult > 0:
                total_score += 20 * mult
                triggered_rules.append({"rule_id": "S1", "label": "OS Update Age", "value": days_ago, "score_contribution": 20 * mult, "note": f"{days_ago} days ago"})
                if days_ago > 180:
                    action = "Apply pending OS updates immediately"
                    if action not in recommended_actions: recommended_actions.append(action)
            has_old_os = (days_ago > 180)
                
    uptime = sys_info.get("uptime_hours")
    if uptime is not None:
        if uptime >= 720: mult = 1.0
        elif uptime >= 168: mult = 0.4
        else: mult = 0.0
        if mult > 0:
            total_score += 15 * mult
            triggered_rules.append({"rule_id": "S2", "label": "System Uptime", "value": uptime, "score_contribution": 15 * mult, "note": f"{uptime} hours"})
            if uptime >= 720:
                action = "Reboot machine to apply updates and clear memory"
                if action not in recommended_actions: recommended_actions.append(action)

    # SERVICES
    has_down_services = False
    down_service_count = 0
    services = snapshot.get("services", [])
    
    for svc in services:
        name = svc.get("name", "Unknown Service")
        status = svc.get("status")
        resp_time = svc.get("response_time_ms")
        cpu_usage = svc.get("process_cpu_percent")
        mem_usage = svc.get("process_memory_mb")
        
        # SV1: Service is DOWN
        if status == "down":
            total_score += 100
            triggered_rules.append({"rule_id": "SV1", "label": f"{name} is Offline", "value": "down", "score_contribution": 100, "note": "Service port is unreachable"})
            action = f"Restart {name} immediately"
            if action not in recommended_actions: recommended_actions.append(action)
            has_down_services = True
            down_service_count += 1
        if status == "up":
            # SV_INFO: Service is UP (Informational for UI, 0 points)
            triggered_rules.append({
                "rule_id": "SV_INFO",
                "label": name,
                "value": "up",
                "score_contribution": 0,
                "note": f"Running (Latency: {resp_time}ms, RAM: {mem_usage}MB)"
            })
            
        # SV2: Service is very slow (degraded)
        if resp_time is not None and resp_time > 2000:
            mult = 1.0 if resp_time > 5000 else 0.5
            total_score += 20 * mult
            triggered_rules.append({"rule_id": "SV2", "label": f"{name} is Degraded", "value": f"{resp_time}ms", "score_contribution": 20 * mult, "note": "Service responding very slowly"})
            action = f"Investigate performance of {name}"
            if action not in recommended_actions: recommended_actions.append(action)

        # SV3: Memory Leak Detection (1024 MB threshold for Server Services)
        if mem_usage is not None and mem_usage > 1024:
            mult = 1.0 if mem_usage > 2048 else 0.5
            total_score += 25 * mult
            triggered_rules.append({"rule_id": "SV3", "label": f"{name} High Memory", "value": f"{mem_usage} MB", "score_contribution": 25 * mult, "note": "Potential memory leak detected"})
            action = f"Check {name} for memory leaks"
            if action not in recommended_actions: recommended_actions.append(action)

        # SV4: CPU Spike / Saturation
        if cpu_usage is not None and cpu_usage > 80:
            total_score += 15
            triggered_rules.append({"rule_id": "SV4", "label": f"{name} CPU Spike", "value": f"{cpu_usage}%", "score_contribution": 15, "note": "Service is maxing out CPU"})
            action = f"Monitor {name} for high load"
            if action not in recommended_actions: recommended_actions.append(action)

    # COMPOUND
    compound_bonuses = []
    if has_high_cpu_temp and has_high_disk_temp:
        total_score += 10
        compound_bonuses.append({"rule_id": "X1", "label": "High CPU temp + High disk temp", "bonus": 10})
    if has_low_wear and has_high_disk_usage:
        total_score += 15
        compound_bonuses.append({"rule_id": "X2", "label": "Low SSD life + High disk usage", "bonus": 15})
    if has_high_power_on_hours and has_old_os:
        total_score += 10
        compound_bonuses.append({"rule_id": "X3", "label": "High disk power on hours + Old OS", "bonus": 10})
    if has_poor_battery_health and has_high_cycle_count:
        total_score += 15
        compound_bonuses.append({"rule_id": "X4", "label": "Low battery health + High cycle count", "bonus": 15})
    if down_service_count > 1:
        total_score += 20
        compound_bonuses.append({"rule_id": "X5", "label": "Multiple critical services down", "bonus": 20})

    # ADD DYNAMIC FLUTTER FOR DEMO VISUALIZATION
    # This adds a tiny continuous jitter based on live CPU/RAM to make the chart look "alive"
    raw_cpu = snapshot.get("cpu", {}).get("usage_percent", 0)
    raw_ram = snapshot.get("memory", {}).get("usage_percent", 0)
    if raw_cpu is not None and raw_ram is not None:
        dynamic_flutter = (raw_cpu * 0.05) + (raw_ram * 0.02)
        total_score += dynamic_flutter
        
        # Inject raw metrics invisibly for the React frontend charts!
        triggered_rules.append({
            "rule_id": "RAW_CPU", "label": "Live CPU", "value": raw_cpu, "score_contribution": 0, "note": f"{raw_cpu}%"
        })
        triggered_rules.append({
            "rule_id": "RAW_RAM", "label": "Live RAM", "value": raw_ram, "score_contribution": 0, "note": f"{raw_ram}%"
        })

    total_score = round(min(100, max(0, total_score)), 2)
    
    if total_score < 30: risk_level = "Healthy"
    elif total_score < 60: risk_level = "Watch"
    elif total_score < 90: risk_level = "At Risk"
    else: risk_level = "Critical"
        
    return {
        "asset_tag": snapshot.get("asset_tag", "UNKNOWN"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_score": total_score,
        "risk_level": risk_level,
        "triggered_rules": triggered_rules,
        "compound_bonuses": compound_bonuses,
        "recommended_actions": recommended_actions,
        "summary": f"Device {snapshot.get('asset_tag', 'UNKNOWN')} scored {total_score} ({risk_level})"
    }

if __name__ == "__main__":
    example = {
      "asset_tag": "066256322857",
      "collected_at": "2026-05-15T10:00:00Z",
      "device_type": "laptop",
      "cpu": {"usage_percent": 32.8, "temperature_celsius": 36.8, "throttling_events": None},
      "memory": {"usage_percent": 67.1, "available_gb": 5.21},
      "disks": [
        {"drive": "C:", "usage_percent": 92.7, "smart_status": "OK", "read_errors": 0, "write_errors": 0, "temperature_celsius": 26.0, "power_on_hours": 1759, "wear_percent": 93, "predict_failure": False}
      ],
      "system": {"uptime_hours": 23.5, "last_os_update": "8/29/2025"},
      "battery": {"health_percent": 83.3, "cycle_count": 455, "charging_status": "discharging"},
      "services": [
        {"name": "MySQL", "status": "up", "response_time_ms": 12.4},
        {"name": "ITAM API (Node.js)", "status": "down", "response_time_ms": None}
      ]
    }
    print(json.dumps(calculate_device_health(example), indent=2))

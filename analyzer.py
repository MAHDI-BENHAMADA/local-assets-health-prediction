def calculate_device_health(telemetry: dict) -> dict:
    """
    Calculates a rule-based health score from 0 to 100 based on device telemetry.
    This is the first basic version. We will add more rules (like temperatures, SMART errors) later.
    """
    score = 100
    issues = []

    # 1. CPU Checks
    cpu_usage = telemetry.get('cpu_percent', 0)
    if cpu_usage > 95:
        score -= 20
        issues.append("Critical: CPU usage is extremely high (>95%)")
    elif cpu_usage > 85:
        score -= 10
        issues.append("Warning: CPU usage is high (>85%)")

    # 2. Memory (RAM) Checks
    memory_percent = telemetry.get('memory_percent', 0)
    if memory_percent > 95:
        score -= 20
        issues.append("Critical: Memory usage is nearly full (>95%)")
    elif memory_percent > 85:
        score -= 10
        issues.append("Warning: Memory usage is high (>85%)")

    # 3. Disk Space Checks
    disk_percent = telemetry.get('disk_percent', 0)
    if disk_percent > 95:
        score -= 30
        issues.append("Critical: Disk space is critically low (>95% used)")
    elif disk_percent > 85:
        score -= 15
        issues.append("Warning: Disk space is running low (>85% used)")

    # Ensure score doesn't drop below 0
    score = max(0, score)

    # Determine overall status classification
    if score >= 80:
        status = "Healthy"
    elif score >= 50:
        status = "Warning"
    else:
        status = "Critical"

    return {
        "health_score": score,
        "status": status,
        "issues": issues
    }

# Quick test to see how it works (you can remove this later)
if __name__ == "__main__":
    sample_telemetry = {
        "cpu_percent": 88,     # Should trigger a Warning
        "memory_percent": 60,  # Healthy
        "disk_percent": 96     # Should trigger a Critical
    }
    
    result = calculate_device_health(sample_telemetry)
    print("Test Result:", result)

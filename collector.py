import psutil
import wmi
import json
import socket
import requests
from datetime import datetime, timezone

# --- CONFIG ---
ASSET_TAG = "DJZ-00142"  # later this comes from a local config file
SERVER_URL = "http://localhost:5000/api/report"  # Change to your server address if running remotely
SEND_TO_SERVER = True  # Set to False to only print to terminal

def get_device_type():
    battery = psutil.sensors_battery()
    return "laptop" if battery is not None else "desktop"

def get_cpu():
    temp = None
    
    # Method 1: Try WMI (MSAcpi_ThermalZoneTemperature)
    try:
        w = wmi.WMI(namespace="root\\wmi")
        temps = w.MSAcpi_ThermalZoneTemperature()
        if temps and hasattr(temps[0], 'CurrentTemperature'):
            raw_temp = temps[0].CurrentTemperature
            converted = (raw_temp / 10.0) - 273.15
            # Only accept reasonable temperatures (0-120°C)
            if 0 <= converted <= 120:
                temp = round(converted, 1)
    except Exception as e:
        pass
    
    # Method 2: Try Win32_PerfFormattedData (CPU temperature)
    if temp is None:
        try:
            w = wmi.WMI()
            temps = w.Win32_PerfFormattedData_Counters_ThermalZoneInformation()
            if temps and len(temps) > 0:
                for t in temps:
                    if hasattr(t, 'HighPrecisionTemperature'):
                        raw_temp = t.HighPrecisionTemperature
                        converted = (raw_temp / 10.0) - 273.15
                        if 0 <= converted <= 120:
                            temp = round(converted, 1)
                            break
        except Exception as e:
            pass
    
    # Method 3: Fallback to psutil.sensors_temperatures()
    if temp is None:
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for sensor_name, readings in temps.items():
                    if readings:
                        for reading in readings:
                            if 0 <= reading.current <= 120:
                                temp = round(reading.current, 1)
                                break
                    if temp is not None:
                        break
        except Exception as e:
            pass

    return {
        "usage_percent": psutil.cpu_percent(interval=1),
        "temperature_celsius": temp,
        "throttling_events": None  # placeholder, hard to get without kernel access
    }

def get_memory():
    mem = psutil.virtual_memory()
    return {
        "usage_percent": round(mem.percent, 1),
        "available_gb": round(mem.available / (1024 ** 3), 2)
    }

def get_disks():
    disks = []
    # Try to get disk temps from psutil if available
    disk_temps = {}
    try:
        temps = psutil.sensors_temperatures()
        if 'ssd' in temps or 'nvme' in temps or 'ata' in temps:
            for sensor_type in ['ssd', 'nvme', 'ata']:
                if sensor_type in temps:
                    disk_temps[sensor_type] = round(temps[sensor_type][0].current, 1) if temps[sensor_type] else None
    except:
        pass
    
    for partition in psutil.disk_partitions():
        if 'cdrom' in partition.opts or partition.fstype == '':
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            # Try to assign temperature from sensors if available
            disk_temp = next((v for k, v in disk_temps.items() if v is not None), None)
            
            disks.append({
                "drive": partition.mountpoint,
                "usage_percent": round(usage.percent, 1),
                "smart_status": None,   # requires pySMART library
                "read_errors": None,    # requires pySMART library
                "write_errors": None,   # requires pySMART library
                "temperature_celsius": disk_temp
            })
        except PermissionError:
            continue
    return disks

def get_system():
    uptime_seconds = psutil.boot_time()
    uptime_hours = round((datetime.now().timestamp() - uptime_seconds) / 3600, 1)

    try:
        w = wmi.WMI()
        updates = w.Win32_QuickFixEngineering()
        dates = [u.InstalledOn for u in updates if u.InstalledOn]
        last_update = sorted(dates)[-1] if dates else None
    except:
        last_update = None

    try:
        os_info = wmi.WMI().Win32_OperatingSystem()[0]
        os_version = os_info.Caption.strip()
    except:
        os_version = None

    return {
        "uptime_hours": uptime_hours,
        "last_os_update": last_update,
        "os_version": os_version
    }

def get_battery(device_type):
    if device_type == "desktop":
        return None

    battery = psutil.sensors_battery()
    if battery is None:
        return None

    health = None
    cycle_count = None
    
    # Method 1: Try WMI for design vs full capacity
    try:
        w = wmi.WMI(namespace="root\\wmi")
        batteries = w.BatteryFullChargedCapacity()
        static = w.BatteryStaticData()
        full_capacity = batteries[0].FullChargedCapacity if batteries else None
        design_capacity = static[0].DesignedCapacity if static else None
        health = round((full_capacity / design_capacity) * 100, 1) if full_capacity and design_capacity else None
        cycle_count = static[0].CycleCount if static else None
    except:
        pass
    
    # Method 2: Try alternate WMI path for battery info
    if health is None:
        try:
            w = wmi.WMI()
            battery_info = w.Win32_Battery()
            if battery_info:
                # EstimatedChargeRemaining is a percentage
                health = battery_info[0].EstimatedChargeRemaining
        except:
            pass

    return {
        "health_percent": health,
        "cycle_count": cycle_count,
        "charging_status": "charging" if battery.power_plugged else "discharging"
    }

def collect():
    device_type = get_device_type()

    snapshot = {
        "asset_tag": ASSET_TAG,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "device_type": device_type,
        "cpu": get_cpu(),
        "memory": get_memory(),
        "disks": get_disks(),
        "system": get_system(),
        "battery": get_battery(device_type)
    }

    return snapshot

def send_to_server(snapshot):
    """Send snapshot to local server for dashboard viewing"""
    if not SEND_TO_SERVER:
        return
    
    try:
        response = requests.post(SERVER_URL, json=snapshot, timeout=5)
        if response.status_code == 200:
            print(f"✓ Data sent to {SERVER_URL}")
        else:
            print(f"✗ Server responded with status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"✗ Could not connect to server at {SERVER_URL}")
        print("  Make sure server.py is running: python server.py")
    except Exception as e:
        print(f"✗ Error sending data: {e}")

if __name__ == "__main__":
    snapshot = collect()
    print(json.dumps(snapshot, indent=2))
    send_to_server(snapshot)
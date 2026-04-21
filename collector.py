import json
import re
import shutil
import subprocess
import psutil
import requests
import wmi
from datetime import datetime, timezone

# --- CONFIG ---
SERVER_URL = "http://127.0.0.1:5000/api/report"  # Change to your server address if running remotely
SEND_TO_SERVER = True  # Set to False to only print to terminal
TEMP_MIN_C = 0.0
TEMP_MAX_C = 120.0
POWERSHELL_TIMEOUT_SECONDS = 8

def get_asset_tag():
    """Retrieve the actual asset tag from system BIOS via WMI"""
    try:
        w = wmi.WMI()
        system_enclosure = w.Win32_SystemEnclosure()
        if system_enclosure and hasattr(system_enclosure[0], 'SMBIOSAssetTag'):
            asset_tag = system_enclosure[0].SMBIOSAssetTag
            if asset_tag and asset_tag.strip():
                return asset_tag.strip()
    except:
        pass
    
    # Fallback to SerialNumber if SMBIOSAssetTag is not available
    try:
        w = wmi.WMI()
        system_product = w.Win32_ComputerSystemProduct()
        if system_product and hasattr(system_product[0], 'IdentifyingNumber'):
            serial = system_product[0].IdentifyingNumber
            if serial and serial.strip():
                return serial.strip()
    except:
        pass
    
    # Final fallback
    return "UNKNOWN"

def get_device_type():
    battery = psutil.sensors_battery()
    return "laptop" if battery is not None else "desktop"


def to_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_temperature(value):
    try:
        if value is None:
            return None
        temp = float(value)
    except (TypeError, ValueError):
        return None

    if TEMP_MIN_C <= temp <= TEMP_MAX_C:
        return round(temp, 1)
    return None


def normalize_serial(value):
    if value is None:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return cleaned if cleaned else None


def parse_json_output(output):
    if not output:
        return None

    raw = output.strip()
    if not raw:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def run_powershell_json(script):
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=POWERSHELL_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    return parse_json_output(result.stdout)


def get_psutil_any_disk_temp():
    try:
        temps = psutil.sensors_temperatures() or {}
    except Exception:
        return None

    for sensor_type in ("nvme", "ssd", "ata"):
        readings = temps.get(sensor_type, [])
        for reading in readings:
            temp = normalize_temperature(getattr(reading, "current", None))
            if temp is not None:
                return temp
    return None


def get_logical_drive_map():
    mapping = {}

    try:
        w = wmi.WMI()
        disk_drives = w.Win32_DiskDrive()
    except Exception:
        return mapping

    for disk in disk_drives:
        disk_info = {
            "index": to_int(getattr(disk, "Index", None)),
            "device_id": str(getattr(disk, "DeviceID", "")) or None,
            "model": getattr(disk, "Model", None),
            "serial_number": normalize_serial(getattr(disk, "SerialNumber", None)),
            "status": getattr(disk, "Status", None),
        }

        try:
            partitions = disk.associators("Win32_DiskDriveToDiskPartition")
        except Exception:
            partitions = []

        for partition in partitions:
            try:
                logical_disks = partition.associators("Win32_LogicalDiskToPartition")
            except Exception:
                logical_disks = []

            for logical_disk in logical_disks:
                logical_id = str(getattr(logical_disk, "DeviceID", "")).upper()
                if logical_id:
                    mapping[logical_id] = dict(disk_info)

    return mapping


def get_storage_reliability_rows():
    script = r"""
    $rows = @()
    Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {
        $pd = $_
        $rel = $null
        try { $rel = $pd | Get-StorageReliabilityCounter -ErrorAction Stop } catch {}

        $rows += [PSCustomObject]@{
            DeviceId = [string]$pd.DeviceId
            FriendlyName = [string]$pd.FriendlyName
            SerialNumber = [string]$pd.SerialNumber
            HealthStatus = [string]$pd.HealthStatus
            OperationalStatus = [string](($pd.OperationalStatus | ForEach-Object { $_.ToString() }) -join ',')
            Temperature = if ($rel -and $null -ne $rel.Temperature) { [double]$rel.Temperature } else { $null }
            ReadErrorsTotal = if ($rel -and $null -ne $rel.ReadErrorsTotal) { [int64]$rel.ReadErrorsTotal } else { $null }
            WriteErrorsTotal = if ($rel -and $null -ne $rel.WriteErrorsTotal) { [int64]$rel.WriteErrorsTotal } else { $null }
            PowerOnHours = if ($rel -and $null -ne $rel.PowerOnHours) { [int64]$rel.PowerOnHours } else { $null }
            Wear = if ($rel -and $null -ne $rel.Wear) { [int]$rel.Wear } else { $null }
        }
    }
    $rows | ConvertTo-Json -Depth 4 -Compress
    """

    rows = run_powershell_json(script)
    if rows is None:
        return []
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, list):
        return rows
    return []


def get_wmi_predict_failure_map():
    failure_by_index = {}
    try:
        w = wmi.WMI(namespace="root\\wmi")
        statuses = w.MSStorageDriver_FailurePredictStatus()
    except Exception:
        return failure_by_index

    for status in statuses:
        disk_index = to_int(getattr(status, "DiskNumber", None))

        if disk_index is None:
            instance = str(getattr(status, "InstanceName", "")).upper()
            match = re.search(r"PHYSICALDRIVE(\d+)", instance)
            if match:
                disk_index = int(match.group(1))

        if disk_index is None:
            continue

        predict_failure = getattr(status, "PredictFailure", None)
        failure_by_index[disk_index] = bool(predict_failure) if predict_failure is not None else None

    return failure_by_index


def parse_wmi_smart_data(vendor_data):
    parsed = {}

    if vendor_data is None:
        return parsed

    try:
        byte_values = [int(v) & 0xFF for v in vendor_data]
    except Exception:
        return parsed

    upper = min(len(byte_values), 362)
    for offset in range(2, upper, 12):
        try:
            attr_id = byte_values[offset]
            if attr_id == 0:
                continue

            raw_bytes = bytes(byte_values[offset + 5: offset + 11])
            if len(raw_bytes) != 6:
                continue

            raw_value = int.from_bytes(raw_bytes, byteorder="little", signed=False)

            if attr_id == 1:
                parsed["read_errors"] = raw_value
            elif attr_id == 5:
                parsed["reallocated_sectors"] = raw_value
            elif attr_id == 9:
                parsed["power_on_hours"] = raw_value
            elif attr_id == 194:
                parsed["temperature_celsius"] = normalize_temperature(raw_value & 0xFF)
            elif attr_id == 197:
                parsed["pending_sectors"] = raw_value
            elif attr_id == 198:
                parsed["write_errors"] = raw_value
        except Exception:
            continue

    return parsed


def get_wmi_smart_attribute_map():
    attributes_by_index = {}

    try:
        w = wmi.WMI(namespace="root\\wmi")
        rows = w.MSStorageDriver_ATAPISmartData()
    except Exception:
        return attributes_by_index

    for row in rows:
        disk_index = to_int(getattr(row, "DiskNumber", None))

        if disk_index is None:
            instance = str(getattr(row, "InstanceName", "")).upper()
            match = re.search(r"PHYSICALDRIVE(\d+)", instance)
            if match:
                disk_index = int(match.group(1))

        if disk_index is None:
            continue

        vendor_data = getattr(row, "VendorSpecificData", None)
        if vendor_data is None:
            vendor_data = getattr(row, "VendorSpecific", None)

        parsed = parse_wmi_smart_data(vendor_data)
        if parsed:
            attributes_by_index[disk_index] = parsed

    return attributes_by_index


def get_smartctl_rows():
    smartctl_path = shutil.which("smartctl")
    if not smartctl_path:
        return []

    try:
        scan_result = subprocess.run(
            [smartctl_path, "--scan-open", "--json"],
            capture_output=True,
            text=True,
            timeout=POWERSHELL_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    scan_payload = parse_json_output(scan_result.stdout)
    if not isinstance(scan_payload, dict):
        return []

    devices = scan_payload.get("devices") or []
    rows = []

    for device in devices:
        device_name = str(device.get("name") or "").strip()
        if not device_name:
            continue

        try:
            detail_result = subprocess.run(
                [smartctl_path, "-a", "-j", device_name],
                capture_output=True,
                text=True,
                timeout=POWERSHELL_TIMEOUT_SECONDS,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

        payload = parse_json_output(detail_result.stdout)
        if not isinstance(payload, dict):
            continue

        info_name = str(payload.get("info_name") or "").upper()
        disk_index = None
        match = re.search(r"PHYSICALDRIVE(\d+)", info_name)
        if match:
            disk_index = int(match.group(1))

        smart_status = None
        predict_failure = None
        smart_status_obj = payload.get("smart_status")
        if isinstance(smart_status_obj, dict) and "passed" in smart_status_obj:
            passed = smart_status_obj.get("passed")
            if passed is True:
                smart_status = "OK"
                predict_failure = False
            elif passed is False:
                smart_status = "Failed"
                predict_failure = True

        ata_table = (payload.get("ata_smart_attributes") or {}).get("table") or []

        read_errors = None
        write_errors = None
        temperature = normalize_temperature((payload.get("temperature") or {}).get("current"))
        power_on_hours = to_int((payload.get("power_on_time") or {}).get("hours"))

        for attr in ata_table:
            attr_id = to_int(attr.get("id"))
            raw_value = to_int((attr.get("raw") or {}).get("value"))
            if attr_id == 1 and read_errors is None:
                read_errors = raw_value
            elif attr_id == 198 and write_errors is None:
                write_errors = raw_value
            elif attr_id == 194 and temperature is None:
                temperature = normalize_temperature(raw_value)
            elif attr_id == 9 and power_on_hours is None:
                power_on_hours = raw_value

        nvme_health = payload.get("nvme_smart_health_information_log") or {}
        media_errors = to_int(nvme_health.get("media_errors"))
        if read_errors is None:
            read_errors = media_errors
        if write_errors is None:
            write_errors = media_errors

        if power_on_hours is None:
            power_on_hours = to_int(nvme_health.get("power_on_hours"))

        wear_percent = None
        percentage_used = to_int(nvme_health.get("percentage_used"))
        if percentage_used is not None:
            wear_percent = max(0, 100 - percentage_used)

        rows.append(
            {
                "disk_index": disk_index,
                "model": payload.get("model_name"),
                "serial_number": normalize_serial(payload.get("serial_number")),
                "smart_status": smart_status,
                "predict_failure": predict_failure,
                "temperature_celsius": temperature,
                "read_errors": read_errors,
                "write_errors": write_errors,
                "power_on_hours": power_on_hours,
                "wear_percent": wear_percent,
            }
        )

    return rows


def find_smartctl_match(disk_info, smartctl_rows):
    if not disk_info:
        return None

    disk_index = disk_info.get("index")
    if disk_index is not None:
        for row in smartctl_rows:
            if row.get("disk_index") == disk_index:
                return row

    disk_serial = normalize_serial(disk_info.get("serial_number"))
    if disk_serial:
        for row in smartctl_rows:
            row_serial = normalize_serial(row.get("serial_number"))
            if row_serial and row_serial == disk_serial:
                return row

    disk_model = str(disk_info.get("model") or "").strip().upper()
    if disk_model:
        for row in smartctl_rows:
            model_name = str(row.get("model") or "").strip().upper()
            if model_name and disk_model in model_name:
                return row

    return None


def find_reliability_match(disk_info, reliability_rows):
    if not disk_info:
        return None

    disk_index = disk_info.get("index")
    if disk_index is not None:
        for row in reliability_rows:
            if str(row.get("DeviceId")) == str(disk_index):
                return row

    disk_serial = normalize_serial(disk_info.get("serial_number"))
    if disk_serial:
        for row in reliability_rows:
            row_serial = normalize_serial(row.get("SerialNumber"))
            if row_serial and row_serial == disk_serial:
                return row

    disk_model = str(disk_info.get("model") or "").strip().upper()
    if disk_model:
        for row in reliability_rows:
            friendly_name = str(row.get("FriendlyName") or "").strip().upper()
            if friendly_name and disk_model in friendly_name:
                return row

    return None


def derive_smart_status(base_status, reliability_row, predict_failure):
    if predict_failure is True:
        return "PredictedFailure"

    if reliability_row:
        health_status = str(reliability_row.get("HealthStatus") or "").strip()
        if health_status:
            return health_status

        operational_status = str(reliability_row.get("OperationalStatus") or "").strip()
        if operational_status:
            return operational_status

    if base_status:
        return str(base_status)

    return "Unknown"

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
    except Exception:
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
        except Exception:
            pass
    
    # Method 3: Fallback to psutil.sensors_temperatures()
    if temp is None:
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for readings in temps.values():
                    if readings:
                        for reading in readings:
                            if 0 <= reading.current <= 120:
                                temp = round(reading.current, 1)
                                break
                    if temp is not None:
                        break
        except Exception:
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
    logical_drive_map = get_logical_drive_map()
    reliability_rows = get_storage_reliability_rows()
    predict_failure_by_index = get_wmi_predict_failure_map()
    smart_attributes_by_index = get_wmi_smart_attribute_map()
    smartctl_rows = get_smartctl_rows()
    psutil_temp_fallback = get_psutil_any_disk_temp()

    for partition in psutil.disk_partitions():
        if "cdrom" in partition.opts or partition.fstype == "":
            continue

        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except PermissionError:
            continue

        drive_letter = partition.mountpoint.rstrip("\\").upper()
        disk_info = logical_drive_map.get(drive_letter)
        reliability = find_reliability_match(disk_info, reliability_rows)
        smartctl = find_smartctl_match(disk_info, smartctl_rows)

        disk_index = disk_info.get("index") if disk_info else None
        smart_attrs = smart_attributes_by_index.get(disk_index, {}) if disk_index is not None else {}
        predict_failure = predict_failure_by_index.get(disk_index) if disk_index is not None else None
        if predict_failure is None and smartctl:
            predict_failure = smartctl.get("predict_failure")

        smart_status = derive_smart_status(
            base_status=disk_info.get("status") if disk_info else None,
            reliability_row=reliability,
            predict_failure=predict_failure,
        )

        if smartctl and smartctl.get("smart_status"):
            smartctl_status = smartctl.get("smart_status")
            if smartctl_status in ("Failed", "PredictedFailure"):
                smart_status = smartctl_status
            elif smart_status in ("Unknown", "OK", "Healthy"):
                smart_status = smartctl_status

        disk_temp = normalize_temperature(reliability.get("Temperature")) if reliability else None
        if disk_temp is None:
            disk_temp = normalize_temperature(smart_attrs.get("temperature_celsius"))
        if disk_temp is None and smartctl:
            disk_temp = normalize_temperature(smartctl.get("temperature_celsius"))
        if disk_temp is None:
            disk_temp = psutil_temp_fallback

        read_errors = to_int(reliability.get("ReadErrorsTotal")) if reliability else None
        if read_errors is None:
            read_errors = to_int(smart_attrs.get("read_errors"))
        if read_errors is None and smartctl:
            read_errors = to_int(smartctl.get("read_errors"))

        write_errors = to_int(reliability.get("WriteErrorsTotal")) if reliability else None
        if write_errors is None:
            write_errors = to_int(smart_attrs.get("write_errors"))
        if write_errors is None and smartctl:
            write_errors = to_int(smartctl.get("write_errors"))

        power_on_hours = to_int(reliability.get("PowerOnHours")) if reliability else None
        if power_on_hours is None:
            power_on_hours = to_int(smart_attrs.get("power_on_hours"))
        if power_on_hours is None and smartctl:
            power_on_hours = to_int(smartctl.get("power_on_hours"))

        wear_percent = to_int(reliability.get("Wear")) if reliability else None
        if wear_percent is None and smartctl:
            wear_percent = to_int(smartctl.get("wear_percent"))

        telemetry_note = None
        if all(value is None for value in (disk_temp, read_errors, write_errors, power_on_hours, wear_percent)):
            if not smartctl_rows:
                telemetry_note = "Extended telemetry unavailable. Install smartmontools (smartctl) for deeper SMART counters."
            else:
                telemetry_note = "Extended disk telemetry is not exposed by this controller/driver."
        elif any(value is None for value in (disk_temp, read_errors, write_errors, power_on_hours)):
            telemetry_note = "Partial disk telemetry available."

        disks.append(
            {
                "drive": partition.mountpoint,
                "usage_percent": round(usage.percent, 1),
                "smart_status": smart_status,
                "read_errors": read_errors,
                "write_errors": write_errors,
                "temperature_celsius": disk_temp,
                "model": (disk_info.get("model") if disk_info else None) or (smartctl.get("model") if smartctl else None),
                "serial_number": (disk_info.get("serial_number") if disk_info else None) or (smartctl.get("serial_number") if smartctl else None),
                "power_on_hours": power_on_hours,
                "wear_percent": wear_percent,
                "predict_failure": predict_failure,
                "telemetry_note": telemetry_note,
            }
        )

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
        if batteries and static:
            full_capacity = batteries[0].FullChargedCapacity if batteries else None
            design_capacity = static[0].DesignedCapacity if static else None
            health = round((full_capacity / design_capacity) * 100, 1) if full_capacity and design_capacity else None
            cycle_count = static[0].CycleCount if hasattr(static[0], 'CycleCount') else None
    except:
        pass
    
    # Method 2: Try Win32_PerfFormattedData for battery info
    if cycle_count is None:
        try:
            w = wmi.WMI()
            batteries = w.Win32_PerfFormattedData_Counters_BatteryData()
            if batteries and len(batteries) > 0:
                for batt in batteries:
                    if hasattr(batt, 'CycleCount'):
                        cycle_count = batt.CycleCount
                        break
        except Exception:
            pass

    # Method 3: Try CIM BatteryCycleCount class via PowerShell
    if cycle_count is None:
        cycle_script = (
            "$c = Get-CimInstance -Namespace root\\wmi -ClassName BatteryCycleCount "
            "-ErrorAction SilentlyContinue; "
            "if ($c -and $null -ne $c.CycleCount) { [int]$c.CycleCount | ConvertTo-Json -Compress }"
        )
        cycle_json = run_powershell_json(cycle_script)
        cycle_count = to_int(cycle_json)
    
    # Method 4: Try Win32_Battery for current health
    if health is None:
        try:
            w = wmi.WMI()
            battery_info = w.Win32_Battery()
            if battery_info:
                # EstimatedChargeRemaining is a percentage
                health = battery_info[0].EstimatedChargeRemaining
        except Exception:
            pass

    return {
        "health_percent": health,
        "cycle_count": cycle_count,
        "charging_status": "charging" if battery.power_plugged else "discharging"
    }

def collect():
    device_type = get_device_type()

    snapshot = {
        "asset_tag": get_asset_tag(),
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
            print("[OK] Data sent to server")
        else:
            print(f"[!] Server responded with status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[!] Could not connect to server at {SERVER_URL}")
        print("    Make sure server.py is running: python server.py")
    except Exception as e:
        print(f"[!] Error sending data: {e}")

if __name__ == "__main__":
    snapshot = collect()
    print(json.dumps(snapshot, indent=2))
    send_to_server(snapshot)
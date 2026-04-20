# Device Health Collector

A Python utility that collects comprehensive hardware health and performance metrics from Windows devices.

## Features

- **CPU**: Usage percentage, temperature, throttling events
- **Memory**: Usage percentage, available capacity
- **Disks**: Per-drive usage, SMART status, temperature, read/write errors
- **System**: Uptime, OS version, last update date
- **Battery** (Laptops): Health percentage, cycle count, charging status
- **Device Type Detection**: Automatically detects laptop vs desktop

## Required Libraries

Install dependencies with:

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install psutil pypiwin32 WMI
```

### Libraries Explained

| Library | Purpose | Installation |
|---------|---------|--------------|
| `psutil` | CPU, memory, disk, battery metrics | `pip install psutil` |
| `pypiwin32` | Windows API support | `pip install pypiwin32` |
| `WMI` | Windows Management Instrumentation queries | `pip install WMI` |
| `json` | Output formatting (built-in) | - |
| `socket` | Networking utilities (built-in, currently unused) | - |
| `datetime` | Timestamp generation (built-in) | - |

## Optional Libraries for Enhanced Data

To unlock additional health data, optionally install:

```bash
# For SMART disk errors and status
pip install pySMART

# For LibreHardwareMonitor integration (more complete temperature data)
# Download from: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor
```

## Setup & Installation

1. **Clone/Download** this repository
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Optional: Run as Administrator** for full sensor access:
   - Right-click PowerShell → Run as Administrator
   - Then: `python collector.py`

## Usage

### Run Collector
```bash
python collector.py
```

### Output Format
Returns JSON with structure:
```json
{
  "asset_tag": "DJZ-00142",
  "collected_at": "2026-04-20T18:32:43.993406+00:00",
  "device_type": "laptop",
  "cpu": {...},
  "memory": {...},
  "disks": [...],
  "system": {...},
  "battery": {...}
}
```

## Troubleshooting

### Temperature Returns `null`
- **Cause**: Sensors not exposed via psutil or WMI
- **Solution**: 
  - Run as Administrator for full sensor access
  - Or install LibreHardwareMonitor and run in background
  - Or try Option 3 in the code: Windows Performance Counters

### Battery Data Returns `null`
- **Cause**: Running on desktop (has no battery)
- **Expected**: Battery field is `null` for desktops, populated for laptops

### SMART Status/Errors Return `null`
- **Cause**: pySMART not installed
- **Solution**: `pip install pySMART`

### WMI Errors
- **Cause**: Insufficient privileges or WMI service not running
- **Solution**: Run as Administrator

## Requirements File

Create `requirements.txt`:
```
psutil==6.0.0
pypiwin32==305
```

Install from file:
```bash
pip install -r requirements.txt
```

## Configuration

Edit the `ASSET_TAG` variable in `collector.py` to customize device identifier:
```python
ASSET_TAG = "DJZ-00142"  # Change this to your device's asset tag
```

## Notes

- Temperatures require either admin privileges, LibreHardwareMonitor, or compatible sensors
- Run with admin privileges for maximum data collection
- Battery info only available on laptop devices
- Throttling events currently require kernel access (placeholder)

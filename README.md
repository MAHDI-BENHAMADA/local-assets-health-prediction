# Device Health Collector

A Python utility that collects comprehensive hardware health and performance metrics from Windows devices.

## Features

- **CPU**: Usage percentage, temperature, throttling events
- **Memory**: Usage percentage, available capacity
- **Disks**: Per-drive usage, **SMART status**, temperature, read/write errors
- **System**: Uptime, OS version, last update date
- **Battery** (Laptops): Health percentage, cycle count, charging status
- **Device Type Detection**: Automatically detects laptop vs desktop

## Data Collection Status

### ✅ Fully Working
- CPU usage & temperature (via WMI)
- Memory usage & available space
- **Disk SMART status** (shows "OK" or error)
- Disk usage per drive
- System uptime & OS version
- Battery health % & charging status

### ⚠️ Null Values (Expected)
- **Disk Temperature**: Requires hardware sensors/drivers
- **Read/Write Errors**: Requires `pip install pySMART` + Administrator mode
- **Throttling Events**: System limitation (kernel access needed)
- **Battery Cycle Count**: Not available on all systems

## Required Libraries

Install dependencies with:

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install psutil pypiwin32 WMI requests flask
```

### Libraries Explained

| Library | Purpose | Installation |
|---------|---------|--------------|
| `psutil` | CPU, memory, disk, battery metrics | `pip install psutil` |
| `pypiwin32` | Windows API support | `pip install pypiwin32` |
| `WMI` | Windows Management Instrumentation queries | `pip install WMI` |
| `requests` | HTTP requests to send data to server | `pip install requests` |
| `flask` | Web server for dashboard | `pip install flask` |
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

### Dashboard Server (NEW!)

View collected data on a live dashboard instead of the terminal:

**Terminal 1 - Start the dashboard server:**
```bash
python server.py
```
Output:
```
Starting Device Health Monitor Server...
📊 Open http://localhost:5000 in your browser
Press Ctrl+C to stop
```

**Terminal 2 - Run collector on one or multiple devices:**
```bash
python collector.py
```

Then open your browser to **http://localhost:5000** to see:
- ✅ Real-time device health data
- ✅ CPU/Memory/Disk usage with color-coded alerts
- ✅ Battery health and charging status
- ✅ System uptime and OS version
- ✅ Auto-refreshes every 5 seconds
- ✅ Multiple devices displayed side-by-side

**For remote machines:**
Edit `collector.py` and change:
```python
SERVER_URL = "http://your-server-ip:5000/api/report"
```

Then run collector on the remote machine - data will stream to your central server.

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
WMI==1.5.1
requests==2.31.0
flask==3.0.0
```

Install from file:
```bash
pip install -r requirements.txt
```

## Server API

The dashboard server provides REST endpoints:

### GET `/` 
HTML dashboard interface (open in browser)

### GET `/api/devices`
Returns JSON of all connected devices:
```bash
curl http://localhost:5000/api/devices
```

### POST `/api/report`
Receive a device health report (used by collector.py):
```bash
curl -X POST http://localhost:5000/api/report \
  -H "Content-Type: application/json" \
  -d @snapshot.json
```

## Configuration

Edit the `ASSET_TAG` variable in `collector.py` to customize device identifier:
```python
ASSET_TAG = "DJZ-00142"  # Change this to your device's asset tag
```

Edit `SERVER_URL` and `SEND_TO_SERVER` to control where data is sent:
```python
SERVER_URL = "http://localhost:5000/api/report"  # Change for remote servers
SEND_TO_SERVER = True  # Set to False to only print to terminal, not send
```

## Notes

- Temperatures require either admin privileges, LibreHardwareMonitor, or compatible sensors
- Run with admin privileges for maximum data collection
- Battery info only available on laptop devices
- Throttling events currently require kernel access (placeholder)

## Dashboard Features

The web dashboard (`server.py`) provides:

- **Real-time monitoring**: Updates every 5 seconds
- **Color-coded alerts**: 
  - 🟢 Green: Good (< 75%)
  - 🟡 Orange: Warning (75-90%)
  - 🔴 Red: Critical (> 90%)
- **Multi-device view**: See all devices at once
- **Temperature display**: Color-coded by severity
- **Responsive design**: Works on mobile and desktop
- **No external dependencies**: Just Flask (built-in web framework)

## Troubleshooting Dashboard

### "Could not connect to server" error
- Ensure `server.py` is running in another terminal
- Check that port 5000 is not blocked by firewall
- From remote machine, ensure `SERVER_URL` points to correct IP/port

### Dashboard shows no devices
- Run `collector.py` to send the first data point
- Check browser console for errors (F12)

### Server won't start
- Port 5000 may be in use: `netstat -ano | findstr :5000`
- Kill the process or change port in `server.py`

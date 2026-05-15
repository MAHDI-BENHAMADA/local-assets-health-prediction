# Predictive Maintenance Engine – Execution Guide

This document explains how to set up and run the predictive maintenance system, testing the server, analyzer, and collector in the correct order.

## Prerequisites
- Python 3.x installed on all machines.
- `smartmontools` installed (to allow deep disk SMART metric collection).
- Network access between the client machines and the server (if running on multiple machines).

---

## 1. Install Dependencies
Before running anything, ensure all required Python packages are installed.
```powershell
pip install -r requirements.txt
```

## 2. Start the Server (The Central Hub)
The server acts as the central brain. It receives data, stores it in the local SQLite database (`itam_agent.db`), analyzes it using the rule-based engine, and serves the dashboard.

**Command:**
```powershell
python server.py
```
**What happens:**
- The database tables (`snapshots` and `labels`) are automatically initialized via `storage.py`.
- The Flask web server starts running on `http://0.0.0.0:5000` (accessible locally at `http://127.0.0.1:5000` and via your machine's local IP address for other devices on the network).

## 3. View the Dashboard
Open your web browser and navigate to:
👉 **[http://localhost:5000](http://localhost:5000)**

*(Right now, it will say it is waiting for device telemetry).*

## 4. Run the Collector (The Client Agent)
The collector gathers hardware telemetry (CPU, Memory, Battery, Storage), deduplicates disks by serial number, and pushes the JSON snapshot to the server.

**Command:** *(Open a new, separate terminal window for this)*
```powershell
python collector.py
```
**What happens:**
- The script analyzes the hardware.
- It sends an HTTP POST request to `http://localhost:5000/api/report`.
- The server receives it, runs `analyzer.py` on the data, saves the results to the database, and updates the in-memory state.
- If you look at your browser (the dashboard), it will instantly update with the new device card, risk score, triggered rules, and recommended actions.

## 5. Connecting Other Machines (Optional)
If you want to monitor *other* machines on your network:
1. Copy `collector.py` (and install dependencies/`smartmontools`) onto the target machine.
2. Open `collector.py` on that target machine and change the `SERVER_URL` variable at the top to point to your main server's local IP address instead of `localhost`:
   ```python
   SERVER_URL = "http://<YOUR_SERVER_IP>:5000/api/report"
   ```
3. Run `python collector.py` on the target machine. It will show up on your main server's dashboard!

## 6. How to Check the Database
All snapshots and scored rules are saved into a local SQLite database file named `itam_agent.db`. 

There are a few easy ways to check this data:

### Option A: Using a GUI Tool (Recommended)
Download and install a tool like [DB Browser for SQLite](https://sqlitebrowser.org/). Simply open the `itam_agent.db` file in the program to easily view, filter, and export the `snapshots` and `labels` tables.

### Option B: Using Python in the Terminal
You can run a quick Python script to query and print the contents inside your terminal. 
Create a file called `check_db.py` (or just run this via python):
```python
import sqlite3
import json

conn = sqlite3.connect("itam_agent.db")
cursor = conn.cursor()

print("--- RECENT LABELS (SCORES) ---")
cursor.execute("SELECT asset_tag, scored_at, risk_score, risk_level FROM labels ORDER BY id DESC LIMIT 5")
for row in cursor.fetchall():
    print(row)

conn.close()
```

### Option C: Using SQLite Command Line
If you have `sqlite3` installed in your terminal, simply run:
```bash
sqlite3 itam_agent.db "SELECT asset_tag, risk_score, risk_level, recommended_action FROM labels;"
```
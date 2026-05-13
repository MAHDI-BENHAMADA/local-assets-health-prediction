import sqlite3
import json
from datetime import datetime

DB_PATH = "itam_agent.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_tag TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            snapshot JSON NOT NULL,
            synced INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_tag TEXT NOT NULL,
            scored_at TEXT NOT NULL,
            risk_score REAL,
            risk_level TEXT,
            triggered_rules JSON,
            recommended_action TEXT,
            synced INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def save_snapshot(snapshot: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO snapshots (asset_tag, collected_at, snapshot)
        VALUES (?, ?, ?)
    """, (
        snapshot["asset_tag"],
        snapshot["collected_at"],
        json.dumps(snapshot)
    ))
    conn.commit()
    conn.close()
    print(f"[+] Snapshot saved for {snapshot['asset_tag']} at {snapshot['collected_at']}")

def get_unsynced_labels():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM labels WHERE synced = 0")
    rows = cursor.fetchall()
    conn.close()
    return rows

def mark_label_synced(label_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE labels SET synced = 1 WHERE id = ?", (label_id,))
    conn.commit()
    conn.close()

def save_label(label: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO labels (asset_tag, scored_at, risk_score, risk_level, triggered_rules, recommended_action)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        label["asset_tag"],
        label["scored_at"],
        label["risk_score"],
        label["risk_level"],
        json.dumps(label["triggered_rules"]),
        label["recommended_action"]
    ))
    conn.commit()
    conn.close()
    print(f"[+] Label saved: {label['risk_level']} ({label['risk_score']}) for {label['asset_tag']}")

if __name__ == "__main__":
    init_db()
    print("[+] Database initialized — tables: snapshots, labels")
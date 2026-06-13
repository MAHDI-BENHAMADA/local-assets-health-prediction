import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request
import urllib.parse
import json
import time
import storage

# Configuration
DEFAULT_ITAM_SERVER_URL = "http://192.168.1.159:3000/api/telemetry/sync"
ITAM_API_KEY = "default_itam_agent_key"
BATCH_SIZE = 50

def load_itam_server_url():
    config_paths = [
        os.path.join(os.path.dirname(__file__), "agent_config.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent_config.json"),
        "agent_config.json"
    ]
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    config = json.load(f)
                    if "itam_server_url" in config:
                        return config["itam_server_url"].strip()
                    # Secondary fallback: if server_url contains port 3000
                    if "server_url" in config and ":3000" in config["server_url"]:
                        return config["server_url"].strip()
            except Exception as e:
                print(f"Error reading config in sync service: {e}")
    return DEFAULT_ITAM_SERVER_URL


def sync_labels():
    itam_server_url = load_itam_server_url()
    print(f"Starting sync to ITAM server ({itam_server_url})...")
    
    # 1. Fetch unsynced labels from local DB
    unsynced = storage.get_unsynced_labels()
    
    if not unsynced:
        print("No new labels to sync.")
        return
 
    print(f"Found {len(unsynced)} unsynced labels.")
    
    # Process in batches
    for i in range(0, len(unsynced), BATCH_SIZE):
        batch = unsynced[i:i + BATCH_SIZE]
        
        # Prepare payload
        payload = []
        for row in batch:
            # row format from storage.py: (id, asset_tag, scored_at, risk_score, risk_level, triggered_rules, recommended_action, synced)
            payload.append({
                "label_id": row[0], # for local tracking
                "asset_tag": row[1],
                "scored_at": row[2],
                "risk_score": row[3],
                "risk_level": row[4],
                "triggered_rules": json.loads(row[5]) if row[5] else [],
                "recommended_action": row[6]
            })
 
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(itam_server_url, data=data)
        req.add_header('Content-Type', 'application/json')
        req.add_header('x-telemetry-key', ITAM_API_KEY)
 
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print(f"Successfully synced batch of {len(batch)} labels.")
                    # Mark as synced in local SQLite
                    for item in payload:
                        storage.mark_label_synced(item["label_id"])
                else:
                    print(f"Failed to sync batch. Server returned {response.status}")
        except Exception as e:
            print(f"Error syncing to ITAM server: {e}")
            print("Will try again next cycle.")
            break # stop processing batches if server is down


if __name__ == "__main__":
    print("Starting continuous sync service. Press Ctrl+C to stop.")
    try:
        while True:
            sync_labels()
            time.sleep(15) # Check for new data every 15 seconds
    except KeyboardInterrupt:
        print("\nSync service stopped.")


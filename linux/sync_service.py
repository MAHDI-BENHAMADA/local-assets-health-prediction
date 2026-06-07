import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request
import urllib.parse
import json
import time
import storage

# Configuration
ITAM_SERVER_URL = "http://192.168.1.159:3000/api/telemetry/sync"
ITAM_API_KEY = "default_itam_agent_key"
BATCH_SIZE = 50

def sync_labels():
    print("Starting sync to ITAM server...")
    
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
        
        req = urllib.request.Request(ITAM_SERVER_URL, data=data)
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


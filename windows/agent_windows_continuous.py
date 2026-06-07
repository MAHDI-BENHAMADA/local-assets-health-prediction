import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import urllib.request
import urllib.parse
import json
import traceback

# Import the existing collector and analyzer
import collector
import analyzer

ITAM_SERVER_URL = "http://192.168.1.159:3000/api/telemetry/sync"
ITAM_API_KEY = "default_itam_agent_key"
POLL_INTERVAL = 10

def load_server_url():
    global ITAM_SERVER_URL
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent_config.json")
    try:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
                if config.get("server_url"):
                    ITAM_SERVER_URL = config["server_url"].strip()
    except Exception:
        pass

def main():
    load_server_url()
    print(f"Starting ITAM Windows Agent...")
    print(f"Target Server: {ITAM_SERVER_URL}")
    print("Running continuously in the background. Press Ctrl+C to stop (if running in terminal).")
    
    while True:
        try:
            # 1. Collect Raw Telemetry (using the Windows collector)
            # Temporarily disable console prints from collector by overriding print? 
            # It's fine, pythonw ignores prints.
            snapshot = collector.collect()
            
            # 2. Analyze & Score (using Expert Rules)
            health_data = analyzer.calculate_device_health(snapshot)
            
            # 3. Format Payload for Node.js
            payload = [{
                "asset_tag": snapshot.get("asset_tag", "UNKNOWN"),
                "scored_at": health_data.get("evaluated_at", snapshot.get("collected_at")),
                "risk_score": health_data.get("total_score", 0),
                "risk_level": health_data.get("risk_level", "Healthy"),
                "triggered_rules": health_data.get("triggered_rules", []),
                "recommended_action": health_data.get("recommended_actions")[0] if health_data.get("recommended_actions") else None
            }]
            
            # 4. Push directly to Central Node.js Server
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(ITAM_SERVER_URL, data=data)
            req.add_header('Content-Type', 'application/json')
            req.add_header('x-telemetry-key', ITAM_API_KEY)
            
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        timestamp = health_data.get('evaluated_at', 'Now')
                        score = health_data.get('total_score', 0)
                        print(f"[{timestamp}] Synced successfully! (Risk: {score})")
                    else:
                        print(f"Failed to sync. Status: {response.status}")
            except Exception as e:
                print(f"Connection failed (Is the Node.js server running?): {e}")
                    
        except Exception as e:
            print(f"Error in agent loop:")
            traceback.print_exc()
            
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()


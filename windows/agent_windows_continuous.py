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

def main():
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
                "scored_at": health_data["scored_at"],
                "risk_score": health_data["risk_score"],
                "risk_level": health_data["risk_level"],
                "triggered_rules": health_data["triggered_rules"],
                "recommended_action": health_data["recommended_actions"][0] if health_data["recommended_actions"] else None
            }]
            
            # 4. Push directly to Central Node.js Server
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(ITAM_SERVER_URL, data=data)
            req.add_header('Content-Type', 'application/json')
            req.add_header('x-telemetry-key', ITAM_API_KEY)
            
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        print(f"[{health_data['scored_at']}] Synced successfully! (Risk: {health_data['risk_score']})")
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


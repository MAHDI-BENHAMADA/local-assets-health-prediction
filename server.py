from flask import Flask, render_template, jsonify, request
import storage
import analyzer

app = Flask(__name__)

# Store latest snapshot + analysis from each device for fast frontend serve
device_snapshots = {}

# Initialize DB
storage.init_db()

@app.route('/', methods=['GET'])
def dashboard():
    """Serve HTML dashboard to view device data"""
    return render_template("index.html")

@app.route('/api/devices', methods=['GET'])
def get_devices():
    return jsonify(device_snapshots)

@app.route('/api/report', methods=['POST'])
def receive_report():
    """Receive device health report from collector, save to DB, and analyze"""
    try:
        data = request.json
        asset_tag = data.get('asset_tag', 'unknown')

        # 1. Save raw snapshot to database
        storage.save_snapshot(data)

        # 2. Run rule-based analyzer
        analysis = analyzer.calculate_device_health(data)
        
        # 3. Save label to database
        label = {
            "asset_tag": asset_tag,
            "scored_at": analysis["evaluated_at"],
            "risk_score": analysis["total_score"],
            "risk_level": analysis["risk_level"],
            "triggered_rules": analysis["triggered_rules"],
            "recommended_action": "; ".join(analysis["recommended_actions"])
        }
        storage.save_label(label)
        
        # 4. Attach analysis to data for the frontend and keep in memory
        data["analysis"] = analysis
        device_snapshots[asset_tag] = data

        print(f"[{asset_tag}] Score: {analysis['total_score']} | Risk: {analysis['risk_level']}")
        
        return jsonify({"status": "ok", "message": f"Received data for {asset_tag}"}), 200

    except Exception as e:
        print(f"Error processing report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    # host='0.0.0.0' allows external devices on the same network to connect
    app.run(host='0.0.0.0', port=5000, debug=False)

from flask import Flask, render_template, jsonify, request
import json
from datetime import datetime
app = Flask(__name__)
# Store latest snapshot from each device
device_snapshots = {}
@app.route('/', methods=['GET'])
def dashboard():
    """Serve HTML dashboard to view device data"""
    return render_template('index.html')
@app.route('/api/devices', methods=['GET'])
def get_devices():
    return jsonify(device_snapshots)
@app.route('/api/report', methods=['POST'])
def receive_report():
    try:
        data = request.json
        asset_tag = data.get('asset_tag', 'unknown')
        device_snapshots[asset_tag] = data
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
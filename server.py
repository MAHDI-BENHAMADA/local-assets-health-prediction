from flask import Flask, render_template_string, jsonify, request
import json
from datetime import datetime
b
app = Flask(__name__)

# Store latest snapshot from each device
device_snapshots = {}

@app.route('/', methods=['GET'])
def dashboard():
    """Serve HTML dashboard to view device data"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Device Health Monitor</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            h1 { color: #333; margin-bottom: 30px; text-align: center; }
            .devices-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }
            .device-card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .device-header { border-bottom: 2px solid #007bff; padding-bottom: 10px; margin-bottom: 15px; }
            .device-tag { font-weight: bold; font-size: 18px; color: #007bff; }
            .device-type { font-size: 12px; color: #666; margin-top: 5px; }
            .timestamp { font-size: 11px; color: #999; margin-top: 5px; }
            .metric { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #eee; }
            .metric-label { color: #555; font-weight: 500; }
            .metric-value { font-weight: bold; color: #333; }
            .warning { color: #ff9800; }
            .critical { color: #f44336; }
            .good { color: #4caf50; }
            .null-value { color: #999; font-style: italic; }
            .no-devices { text-align: center; color: #999; padding: 40px; }
            .refresh-info { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🖥️ Device Health Monitor</h1>
            <div id="devicesContainer" class="devices-grid"></div>
            <div class="refresh-info">
                Page auto-refreshes every 5 seconds | <a href="">Manual Refresh</a>
            </div>
        </div>

        <script>
            function formatValue(value, metric) {
                if (value === null || value === undefined) return '<span class="null-value">N/A</span>';
                
                let className = '';
                if (metric.includes('percent') || metric === 'health_percent') {
                    if (value > 90) className = 'critical';
                    else if (value > 75) className = 'warning';
                    else className = 'good';
                    return `<span class="${className}">${value}%</span>`;
                }
                if (metric === 'temperature_celsius') {
                    if (value > 80) className = 'critical';
                    else if (value > 60) className = 'warning';
                    else className = 'good';
                    return `<span class="${className}">${value}°C</span>`;
                }
                return value;
            }

            function renderDevice(assetTag, data) {
                const device = data;
                const cpu = device.cpu || {};
                const memory = device.memory || {};
                const system = device.system || {};
                const battery = device.battery || {};
                const disks = device.disks || [];

                let html = `
                    <div class="device-card">
                        <div class="device-header">
                            <div class="device-tag">${assetTag}</div>
                            <div class="device-type">${device.device_type || 'unknown'}</div>
                            <div class="timestamp">${new Date(device.collected_at).toLocaleString()}</div>
                        </div>
                        
                        <div style="font-size: 13px; font-weight: bold; color: #333; margin: 10px 0;">SYSTEM</div>
                        <div class="metric">
                            <span class="metric-label">Uptime</span>
                            <span class="metric-value">${system.uptime_hours || 'N/A'} hrs</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">OS Version</span>
                            <span class="metric-value">${system.os_version || 'N/A'}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Last Update</span>
                            <span class="metric-value">${system.last_os_update || 'N/A'}</span>
                        </div>

                        <div style="font-size: 13px; font-weight: bold; color: #333; margin: 15px 0 10px 0;">HARDWARE</div>
                        <div class="metric">
                            <span class="metric-label">CPU Usage</span>
                            <span class="metric-value">${formatValue(cpu.usage_percent, 'usage_percent')}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">CPU Temp</span>
                            <span class="metric-value">${formatValue(cpu.temperature_celsius, 'temperature_celsius')}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Memory Usage</span>
                            <span class="metric-value">${formatValue(memory.usage_percent, 'usage_percent')}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Memory Available</span>
                            <span class="metric-value">${memory.available_gb || 'N/A'} GB</span>
                        </div>
                `;

                if (battery && battery.health_percent !== null) {
                    html += `
                        <div style="font-size: 13px; font-weight: bold; color: #333; margin: 15px 0 10px 0;">BATTERY</div>
                        <div class="metric">
                            <span class="metric-label">Health</span>
                            <span class="metric-value">${formatValue(battery.health_percent, 'health_percent')}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Status</span>
                            <span class="metric-value">${battery.charging_status || 'N/A'}</span>
                        </div>
                        ${battery.cycle_count ? `
                        <div class="metric">
                            <span class="metric-label">Cycle Count</span>
                            <span class="metric-value">${battery.cycle_count}</span>
                        </div>
                        ` : ''}
                    `;
                }

                if (disks.length > 0) {
                    html += `
                        <div style="font-size: 13px; font-weight: bold; color: #333; margin: 15px 0 10px 0;">DISKS</div>
                    `;
                    disks.forEach(disk => {
                        html += `
                            <div class="metric">
                                <span class="metric-label">${disk.drive} Usage</span>
                                <span class="metric-value">${formatValue(disk.usage_percent, 'usage_percent')}</span>
                            </div>
                        `;
                    });
                }

                html += `</div>`;
                return html;
            }

            function loadDevices() {
                fetch('/api/devices')
                    .then(r => r.json())
                    .then(data => {
                        const container = document.getElementById('devicesContainer');
                        if (Object.keys(data).length === 0) {
                            container.innerHTML = '<div class="no-devices">No devices connected yet. Run collector.py to send data.</div>';
                        } else {
                            container.innerHTML = Object.entries(data)
                                .map(([tag, snapshot]) => renderDevice(tag, snapshot))
                                .join('');
                        }
                    });
            }

            loadDevices();
            setInterval(loadDevices, 5000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/api/devices', methods=['GET'])
def get_devices():
    """Return JSON of all device snapshots"""
    return jsonify(device_snapshots)

@app.route('/api/report', methods=['POST'])
def receive_report():
    """Receive device health report from collector"""
    try:
        data = request.json
        asset_tag = data.get('asset_tag', 'unknown')
        device_snapshots[asset_tag] = data
        return jsonify({"status": "ok", "message": f"Received data for {asset_tag}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    print("Starting Device Health Monitor Server...")
    print("📊 Open http://localhost:5000 in your browser")
    print("Press Ctrl+C to stop")
    app.run(host='0.0.0.0', port=5000, debug=False)

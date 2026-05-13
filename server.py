from flask import Flask, render_template, jsonify, request
import json
from datetime import datetime

# ── AI Prediction ──────────────────────────────────────────
try:
    from predict import predict as ai_predict
    AI_ENABLED = True
    print("✅ AI prediction model loaded successfully")
except Exception as e:
    AI_ENABLED = False
    print(f"⚠️  AI model not available: {e}")
    print("   Run train_model.py first to enable predictions")
# ───────────────────────────────────────────────────────────

app = Flask(__name__)

# Store latest snapshot + prediction from each device
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
            body { font-family: Arial, sans-serif; background: #f0f2f5; padding: 20px; }
            .container { max-width: 1300px; margin: 0 auto; }
            h1 { color: #1a1a2e; margin-bottom: 30px; text-align: center; font-size: 26px; }

            .devices-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
                gap: 24px;
            }

            /* ── Device Card ── */
            .device-card {
                background: white;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            }
            .device-header {
                padding: 16px 20px;
                background: #1a1a2e;
                color: white;
            }
            .device-tag  { font-weight: bold; font-size: 18px; }
            .device-type { font-size: 12px; color: #aaa; margin-top: 3px; text-transform: uppercase; letter-spacing: 1px; }
            .timestamp   { font-size: 11px; color: #888; margin-top: 4px; }

            /* ── AI Score Banner ── */
            .ai-banner {
                padding: 18px 20px;
                display: flex;
                align-items: center;
                gap: 20px;
                border-bottom: 1px solid #eee;
            }
            .ai-banner.low      { background: #f0fff4; border-left: 5px solid #4caf50; }
            .ai-banner.medium   { background: #fffbf0; border-left: 5px solid #ff9800; }
            .ai-banner.high     { background: #fff5f5; border-left: 5px solid #f44336; }
            .ai-banner.critical { background: #1a1a2e; border-left: 5px solid #9c27b0; }

            .score-circle {
                width: 72px; height: 72px;
                border-radius: 50%;
                display: flex; flex-direction: column;
                align-items: center; justify-content: center;
                font-weight: bold; flex-shrink: 0;
                border: 3px solid;
            }
            .score-circle.low      { border-color: #4caf50; color: #4caf50; }
            .score-circle.medium   { border-color: #ff9800; color: #ff9800; }
            .score-circle.high     { border-color: #f44336; color: #f44336; }
            .score-circle.critical { border-color: #9c27b0; color: #9c27b0; }

            .score-num   { font-size: 22px; line-height: 1; }
            .score-label { font-size: 10px; color: #999; }

            .ai-details { flex: 1; }
            .ai-risk {
                font-size: 13px; font-weight: bold; text-transform: uppercase;
                letter-spacing: 1px; margin-bottom: 4px;
            }
            .ai-risk.low      { color: #4caf50; }
            .ai-risk.medium   { color: #ff9800; }
            .ai-risk.high     { color: #f44336; }
            .ai-risk.critical { color: #9c27b0; }

            .ai-lifetime  { font-size: 13px; color: #555; margin-bottom: 8px; }
            .ai-concerns  { font-size: 12px; }
            .concern-item { color: #666; margin-top: 3px; }
            .concern-item::before { content: "⚠ "; }
            .concern-ok   { color: #4caf50; font-size: 12px; }
            .concern-ok::before { content: "✓ "; }

            /* ── Metrics ── */
            .metrics-body { padding: 16px 20px; }
            .section-title {
                font-size: 11px; font-weight: bold; color: #999;
                text-transform: uppercase; letter-spacing: 1px;
                margin: 14px 0 8px 0;
            }
            .section-title:first-child { margin-top: 0; }
            .metric {
                display: flex; justify-content: space-between;
                padding: 7px 0; border-bottom: 1px solid #f5f5f5;
                font-size: 13px;
            }
            .metric-label { color: #666; }
            .metric-value { font-weight: 600; color: #333; }
            .warning  { color: #ff9800; }
            .critical { color: #f44336; }
            .good     { color: #4caf50; }
            .null-value { color: #bbb; font-style: italic; font-weight: normal; }

            .no-devices { text-align: center; color: #999; padding: 60px; background: white; border-radius: 12px; }
            .refresh-info { text-align: center; color: #999; font-size: 12px; margin-top: 20px; }
            .ai-badge {
                display: inline-block; font-size: 10px; background: #e8f0fe;
                color: #1967d2; padding: 2px 8px; border-radius: 10px;
                font-weight: bold; margin-left: 8px; vertical-align: middle;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🖥️ Device Health Monitor <span class="ai-badge">AI Powered</span></h1>
            <div id="devicesContainer" class="devices-grid"></div>
            <div class="refresh-info">
                Auto-refreshes every 5 seconds &nbsp;|&nbsp; <a href="">Manual Refresh</a>
            </div>
        </div>

        <script>
            function riskClass(risk) {
                if (!risk) return 'low';
                return risk.toLowerCase();
            }

            function formatMetric(value, type) {
                if (value === null || value === undefined)
                    return '<span class="null-value">N/A</span>';

                if (type === 'percent') {
                    let cls = value > 85 ? 'critical' : value > 70 ? 'warning' : 'good';
                    return `<span class="${cls}">${value}%</span>`;
                }
                if (type === 'temp') {
                    let cls = value > 80 ? 'critical' : value > 65 ? 'warning' : 'good';
                    return `<span class="${cls}">${value}°C</span>`;
                }
                if (type === 'bat_health') {
                    let cls = value < 60 ? 'critical' : value < 80 ? 'warning' : 'good';
                    return `<span class="${cls}">${value}%</span>`;
                }
                return value;
            }

            function renderAIBanner(prediction) {
                if (!prediction) {
                    return `<div class="ai-banner low" style="background:#f9f9f9; border-left-color:#ccc;">
                        <div style="color:#999; font-size:13px;">AI prediction not available</div>
                    </div>`;
                }

                const rc   = riskClass(prediction.risk_level);
                const health = prediction.health_percent;
                const months = prediction.remaining_months;
                const years  = (months / 12).toFixed(1);
                const concerns = prediction.concerns || [];

                const concernsHtml = concerns.map(c =>
                    c.toLowerCase().includes('no major')
                        ? `<div class="concern-ok">${c}</div>`
                        : `<div class="concern-item">${c}</div>`
                ).join('');

                return `
                    <div class="ai-banner ${rc}">
                        <div class="score-circle ${rc}">
                            <span class="score-num">${health}%</span>
                            <span class="score-label">Health</span>
                        </div>
                        <div class="ai-details">
                            <div class="ai-risk ${rc}">${prediction.risk_level} Risk</div>
                            <div class="ai-lifetime">
                                ⏱ Est. <strong>${months} months</strong> (${years} yrs) remaining
                            </div>
                            <div class="ai-concerns">${concernsHtml}</div>
                        </div>
                    </div>`;
            }

            function renderDevice(assetTag, data) {
                const cpu    = data.cpu    || {};
                const memory = data.memory || {};
                const system = data.system || {};
                const battery = data.battery || null;
                const disks  = data.disks  || [];
                const prediction = data.prediction || null;

                let html = `
                    <div class="device-card">
                        <div class="device-header">
                            <div class="device-tag">${assetTag}</div>
                            <div class="device-type">${data.device_type || 'unknown'}</div>
                            <div class="timestamp">Last seen: ${new Date(data.collected_at).toLocaleString()}</div>
                        </div>

                        ${renderAIBanner(prediction)}

                        <div class="metrics-body">
                            <div class="section-title">System</div>
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

                            <div class="section-title">CPU</div>
                            <div class="metric">
                                <span class="metric-label">Usage</span>
                                <span class="metric-value">${formatMetric(cpu.usage_percent, 'percent')}</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Temperature</span>
                                <span class="metric-value">${formatMetric(cpu.temperature_celsius, 'temp')}</span>
                            </div>

                            <div class="section-title">Memory</div>
                            <div class="metric">
                                <span class="metric-label">Usage</span>
                                <span class="metric-value">${formatMetric(memory.usage_percent, 'percent')}</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Available</span>
                                <span class="metric-value">${memory.available_gb || 'N/A'} GB</span>
                            </div>
                `;

                if (battery && battery.health_percent !== null && battery.health_percent !== undefined) {
                    html += `
                            <div class="section-title">Battery</div>
                            <div class="metric">
                                <span class="metric-label">Health</span>
                                <span class="metric-value">${formatMetric(battery.health_percent, 'bat_health')}</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Status</span>
                                <span class="metric-value">${battery.charging_status || 'N/A'}</span>
                            </div>
                            ${battery.cycle_count != null ? `
                            <div class="metric">
                                <span class="metric-label">Cycle Count</span>
                                <span class="metric-value">${battery.cycle_count}</span>
                            </div>` : ''}
                    `;
                }

                if (disks.length > 0) {
                    html += `<div class="section-title">Disks</div>`;
                    disks.forEach(disk => {
                        const driveLabel = disk.drive.replace(/\\+/g, '');
                        const model = disk.model ? `<span style="color:#aaa;font-size:11px;margin-left:6px">${disk.model}</span>` : '';
                        const poh = disk.power_on_hours;
                        let ageStr = '<span class="null-value">N/A</span>';
                        if (poh !== null && poh !== undefined) {
                            const years = Math.floor(poh / 8760);
                            const months = Math.floor((poh % 8760) / 730);
                            ageStr = years > 0 ? `${years}y ${months}m (${poh.toLocaleString()} hrs)` : `${months} months (${poh.toLocaleString()} hrs)`;
                        }
                        const smartCls = disk.smart_status === 'Healthy' || disk.smart_status === 'OK' ? 'good'
                            : disk.smart_status === 'PredictedFailure' || disk.smart_status === 'Failed' ? 'critical'
                            : disk.smart_status === 'Warning' ? 'warning' : '';
                        const reCls  = disk.read_errors  > 0 ? 'critical' : disk.read_errors === 0 ? 'good' : '';
                        const wrCls  = disk.write_errors > 0 ? 'critical' : disk.write_errors === 0 ? 'good' : '';
                        const wearCls = disk.wear_percent !== null && disk.wear_percent !== undefined
                            ? (disk.wear_percent < 20 ? 'critical' : disk.wear_percent < 50 ? 'warning' : 'good') : '';
                        html += `
                            <div style="background:#fafafa;border:1px solid #eee;border-radius:8px;padding:10px 12px;margin-bottom:8px">
                                <div style="font-weight:600;font-size:13px;margin-bottom:6px">${driveLabel} ${model}</div>
                                <div class="metric">
                                    <span class="metric-label">Usage</span>
                                    <span class="metric-value">${formatMetric(disk.usage_percent, 'percent')}</span>
                                </div>
                                <div class="metric">
                                    <span class="metric-label">Temperature</span>
                                    <span class="metric-value">${formatMetric(disk.temperature_celsius, 'temp')}</span>
                                </div>
                                <div class="metric">
                                    <span class="metric-label">Read Errors</span>
                                    <span class="metric-value ${reCls}">${disk.read_errors !== null && disk.read_errors !== undefined ? disk.read_errors : '<span class="null-value">N/A</span>'}</span>
                                </div>
                                <div class="metric">
                                    <span class="metric-label">Write Errors</span>
                                    <span class="metric-value ${wrCls}">${disk.write_errors !== null && disk.write_errors !== undefined ? disk.write_errors : '<span class="null-value">N/A</span>'}</span>
                                </div>
                                <div class="metric">
                                    <span class="metric-label">Age (Power-On)</span>
                                    <span class="metric-value">${ageStr}</span>
                                </div>
                                ${disk.wear_percent !== null && disk.wear_percent !== undefined ? `
                                <div class="metric">
                                    <span class="metric-label">Wear Remaining</span>
                                    <span class="metric-value ${wearCls}">${disk.wear_percent}%</span>
                                </div>` : ''}
                                <div class="metric">
                                    <span class="metric-label">SMART Status</span>
                                    <span class="metric-value ${smartCls}">${disk.smart_status || '<span class="null-value">N/A</span>'}</span>
                                </div>
                                ${disk.telemetry_note ? `<div style="font-size:11px;color:#999;margin-top:4px">ℹ️ ${disk.telemetry_note}</div>` : ''}
                            </div>`;
                    });
                }

                html += `</div></div>`;
                return html;
            }

            function loadDevices() {
                fetch('/api/devices')
                    .then(r => r.json())
                    .then(data => {
                        const container = document.getElementById('devicesContainer');
                        if (Object.keys(data).length === 0) {
                            container.innerHTML = `
                                <div class="no-devices">
                                    <div style="font-size:40px;margin-bottom:16px">📡</div>
                                    <div>No devices connected yet.</div>
                                    <div style="font-size:12px;margin-top:8px">Run collector.py to send data.</div>
                                </div>`;
                        } else {
                            try {
                                container.innerHTML = Object.entries(data)
                                    .map(([tag, snapshot]) => renderDevice(tag, snapshot))
                                    .join('');
                            } catch (e) {
                                console.error(e);
                                container.innerHTML = `<div style="color:red">Error rendering device: ${e.message}</div>`;
                            }
                        }
                    })
                    .catch(err => console.error("Fetch error:", err));
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
    return jsonify(device_snapshots)


@app.route('/api/report', methods=['POST'])
def receive_report():
    """Receive device health report from collector and run AI prediction"""
    try:
        data = request.json
        asset_tag = data.get('asset_tag', 'unknown')

        # ── Run AI prediction ──────────────────────────
        if AI_ENABLED:
            try:
                prediction = ai_predict(data)
                data["prediction"] = prediction
                print(f"[AI] {asset_tag} → Health: {prediction['health_percent']}% | "
                      f"Remaining: {prediction['remaining_months']} months | "
                      f"Risk: {prediction['risk_level']}")
            except Exception as e:
                print(f"[AI] Prediction failed for {asset_tag}: {e}")
                data["prediction"] = None
        else:
            data["prediction"] = None
        # ───────────────────────────────────────────────

        device_snapshots[asset_tag] = data
        return jsonify({"status": "ok", "message": f"Received data for {asset_tag}"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

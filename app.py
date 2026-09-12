import os
import logging
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify)
from config import Config
from database import Database
from csv_loader import import_devices_from_csv
from network_scanner import NetworkScanner
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload folder exists
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

# ---------- Health Check Route for Jenkins ----------
@app.route('/health')
def health_check():
    try:
        # ডাটাবেজ কানেকশন চেক করা হচ্ছে
        Database.execute_query("SELECT 1")
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'app': 'network-dashboard'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 500

# ========== Initialize Database ==========

def init_app():
    """Initialize database connection pool"""
    Database.init_pool()
    logger.info("Application initialized")


# ========== ROUTES ==========

# ---------- Dashboard ----------

@app.route('/')
def index():
    """Main dashboard page"""
    try:
        stats = Database.get_dashboard_stats()
        devices = Database.get_all_devices()
        recent_scans = Database.get_scan_history(limit=10)
        return render_template('index.html',
                               stats=stats,
                               devices=devices,
                               recent_scans=recent_scans)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return render_template('index.html',
                               stats={}, devices=[], recent_scans=[],
                               error=str(e))


# ---------- Device Detail (Main switch page) ----------

@app.route('/device/<int:device_id>')
def device_detail(device_id):
    """Device detail page with left nav"""
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))

    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template('dashboard.html',
                           device=device,
                           summary=summary,
                           all_devices=all_devices)


# ---------- VLANs ----------

@app.route('/device/<int:device_id>/vlans')
def device_vlans(device_id):
    device = Database.get_device(device_id)
    vlans = Database.get_vlans(device_id)
    all_devices = Database.get_all_devices()
    return render_template('vlans.html',
                           device=device,
                           vlans=vlans,
                           all_devices=all_devices,
                           active_section='vlans')


# ---------- VLAN IPs ----------

@app.route('/device/<int:device_id>/vlan-ips')
def device_vlan_ips(device_id):
    device = Database.get_device(device_id)
    vlan_ips = Database.get_vlan_ips(device_id)
    all_devices = Database.get_all_devices()
    return render_template('vlan_ips.html',
                           device=device,
                           vlan_ips=vlan_ips,
                           all_devices=all_devices,
                           active_section='vlan_ips')


# ---------- RADIUS ----------

@app.route('/device/<int:device_id>/radius')
def device_radius(device_id):
    device = Database.get_device(device_id)
    radius_servers = Database.get_radius_servers(device_id)
    all_devices = Database.get_all_devices()
    return render_template('radius.html',
                           device=device,
                           radius_servers=radius_servers,
                           all_devices=all_devices,
                           active_section='radius')


# ---------- Log Server ----------

@app.route('/device/<int:device_id>/log-server')
def device_log_server(device_id):
    device = Database.get_device(device_id)
    log_servers = Database.get_log_servers(device_id)
    all_devices = Database.get_all_devices()
    return render_template('log_server.html',
                           device=device,
                           log_servers=log_servers,
                           all_devices=all_devices,
                           active_section='log_server')


# ---------- SNMP Server ----------

@app.route('/device/<int:device_id>/snmp-server')
def device_snmp_server(device_id):
    device = Database.get_device(device_id)
    snmp_servers = Database.get_snmp_servers(device_id)
    all_devices = Database.get_all_devices()
    return render_template('snmp_server.html',
                           device=device,
                           snmp_servers=snmp_servers,
                           all_devices=all_devices,
                           active_section='snmp_server')


# ---------- Syslog ----------

@app.route('/device/<int:device_id>/syslog')
def device_syslog(device_id):
    device = Database.get_device(device_id)
    syslog_entries = Database.get_syslog_entries(device_id)
    all_devices = Database.get_all_devices()
    return render_template('syslog.html',
                           device=device,
                           syslog_entries=syslog_entries,
                           all_devices=all_devices,
                           active_section='syslog')


# ---------- CDP Neighbors ----------

@app.route('/device/<int:device_id>/cdp-neighbors')
def device_cdp_neighbors(device_id):
    device = Database.get_device(device_id)
    cdp_neighbors = Database.get_cdp_neighbors(device_id)
    all_devices = Database.get_all_devices()
    return render_template('cdp_neighbors.html',
                           device=device,
                           cdp_neighbors=cdp_neighbors,
                           all_devices=all_devices,
                           active_section='cdp_neighbors')


# ---------- CSV Upload ----------

@app.route('/upload', methods=['GET', 'POST'])
def upload_csv():
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)

        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)

        if file and file.filename.endswith('.csv'):
            try:
                content = file.read()
                result = import_devices_from_csv(content)
                flash(
                    f"Imported {result['imported']} of "
                    f"{result['total_parsed']} devices successfully!",
                    'success'
                )
                if result['errors']:
                    for err in result['errors'][:5]:
                        flash(err, 'warning')
            except Exception as e:
                flash(f'Error processing CSV: {str(e)}', 'error')
        else:
            flash('Please upload a CSV file', 'error')

        return redirect(url_for('index'))

    return render_template('upload.html')


# ---------- Scan API ----------

@app.route('/api/scan/device/<int:device_id>', methods=['POST'])
def api_scan_device(device_id):
    """Trigger scan for a single device"""
    def scan_thread():
        NetworkScanner.scan_device(device_id)

    thread = threading.Thread(target=scan_thread)
    thread.start()

    return jsonify({
        'status': 'started',
        'message': f'Scan started for device {device_id}'
    })


@app.route('/api/scan/all', methods=['POST'])
def api_scan_all():
    """Trigger scan for all devices"""
    def scan_thread():
        NetworkScanner.scan_all_devices()

    thread = threading.Thread(target=scan_thread)
    thread.start()

    return jsonify({
        'status': 'started',
        'message': 'Full network scan started'
    })




@app.route('/api/device/<int:device_id>/delete', methods=['POST'])
def api_delete_device(device_id):
    """Delete a device"""
    try:
        Database.delete_device(device_id)
        return jsonify({'status': 'success', 'message': 'Device deleted'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/devices')
def api_devices():
    """Get all devices as JSON"""
    devices = Database.get_all_devices()
    return jsonify(devices)


@app.route('/api/stats')
def api_stats():
    """Get dashboard stats as JSON"""
    stats = Database.get_dashboard_stats()
    return jsonify(stats)


# ========== Error Handlers ==========

@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', error='Page not found'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('base.html', error='Internal server error'), 500


# ========== Main ==========

if __name__ == '__main__':
    init_app()
    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG)
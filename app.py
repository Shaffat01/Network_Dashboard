import os
import logging
import threading
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify)
from config import Config
from database import Database
from csv_loader import import_devices_from_csv
from network_scanner import NetworkScanner

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


# ---------- Health Check Route for Jenkins / Testing ----------
@app.route('/health')
def health_check():
    try:
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
    """Initialize SQLite database tables"""
    Database.init_db()
    logger.info("Application initialized with SQLite")


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
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))

    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'dashboard.html',
        device=device,
        summary=summary,
        all_devices=all_devices,
        active_section='overview'
    )


@app.route('/device/<int:device_id>/vlans')
def device_vlans(device_id):
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))
    vlans = Database.get_vlans(device_id)
    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'vlans.html',
        device=device,
        vlans=vlans,
        summary=summary,
        all_devices=all_devices,
        active_section='vlans',
        path_suffix='/vlans'
    )


@app.route('/device/<int:device_id>/vlan-ips')
def device_vlan_ips(device_id):
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))
    vlan_ips = Database.get_vlan_ips(device_id)
    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'vlan_ips.html',
        device=device,
        vlan_ips=vlan_ips,
        summary=summary,
        all_devices=all_devices,
        active_section='vlan_ips',
        path_suffix='/vlan-ips'
    )


@app.route('/device/<int:device_id>/radius')
def device_radius(device_id):
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))
    radius_servers = Database.get_radius_servers(device_id)
    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'radius.html',
        device=device,
        radius_servers=radius_servers,
        summary=summary,
        all_devices=all_devices,
        active_section='radius',
        path_suffix='/radius'
    )


@app.route('/device/<int:device_id>/log-server')
def device_log_server(device_id):
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))
    log_servers = Database.get_log_servers(device_id)
    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'log_server.html',
        device=device,
        log_servers=log_servers,
        summary=summary,
        all_devices=all_devices,
        active_section='log_server',
        path_suffix='/log-server'
    )


@app.route('/device/<int:device_id>/snmp-server')
def device_snmp_server(device_id):
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))
    snmp_servers = Database.get_snmp_servers(device_id)
    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'snmp_server.html',
        device=device,
        snmp_servers=snmp_servers,
        summary=summary,
        all_devices=all_devices,
        active_section='snmp_server',
        path_suffix='/snmp-server'
    )


@app.route('/device/<int:device_id>/syslog')
def device_syslog(device_id):
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))
    syslog_entries = Database.get_syslog_entries(device_id)
    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'syslog.html',
        device=device,
        syslog_entries=syslog_entries,
        summary=summary,
        all_devices=all_devices,
        active_section='syslog',
        path_suffix='/syslog'
    )


@app.route('/device/<int:device_id>/cdp-neighbors')
def device_cdp_neighbors(device_id):
    device = Database.get_device(device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('index'))
    cdp_neighbors = Database.get_cdp_neighbors(device_id)
    summary = Database.get_device_summary(device_id)
    all_devices = Database.get_all_devices()
    return render_template(
        'cdp_neighbors.html',
        device=device,
        cdp_neighbors=cdp_neighbors,
        summary=summary,
        all_devices=all_devices,
        active_section='cdp_neighbors',
        path_suffix='/cdp-neighbors'
    )


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



# ---------- Manual Device Add ----------

@app.route('/device/add', methods=['GET', 'POST'])
def add_device():
    """Manually add a single device"""
    if request.method == 'POST':
        try:
            node_name = request.form.get('node_name', '').strip()
            ip_address = request.form.get('ip_address', '').strip()
            device_type = request.form.get('device_type', 'access_switch')
            snmp_community = request.form.get('snmp_community', '').strip() or None
            ssh_username = request.form.get('ssh_username', '').strip() or None
            ssh_password = request.form.get('ssh_password', '').strip() or None

            if not node_name or not ip_address:
                flash('Node Name and IP Address are required!', 'error')
                return redirect(url_for('add_device'))

            if device_type not in ('access_switch', 'distribution_switch'):
                flash('Invalid device type selected!', 'error')
                return redirect(url_for('add_device'))

            Database.add_device(
                node_name=node_name,
                ip_address=ip_address,
                device_type=device_type,
                snmp_community=snmp_community,
                ssh_username=ssh_username,
                ssh_password=ssh_password
            )

            flash(f'Device "{node_name}" ({ip_address}) added successfully!', 'success')
            return redirect(url_for('index'))

        except Exception as e:
            logger.error(f"Error adding device: {e}")
            flash(f'Error adding device: {str(e)}', 'error')
            return redirect(url_for('add_device'))

    return render_template('add_device.html')

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
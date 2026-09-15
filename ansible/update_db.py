import sys
import json
import os

# Root directory path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import Database

def save_ansible_data(device_ip, raw_output):
    """Parses raw text from Ansible and updates SQLite DB"""
    
    # 1. Get Device ID from DB
    devices = Database.execute_query("SELECT id FROM devices WHERE ip_address=?", (device_ip,))
    if not devices:
        print(f"Device {device_ip} not found in Database.")
        return
    
    device_id = devices[0]['id']

    # raw_output-এ ৩টি কমান্ডের রেসপন্স আছে: [show vlan, show ip int brief, show cdp neighbors]
    cmd_results = raw_output.get('stdout', [])
    if len(cmd_results) < 3:
        print("Incomplete command output from Ansible.")
        return

    vlan_raw = cmd_results[0]
    vlan_ip_raw = cmd_results[1]
    cdp_raw = cmd_results[2]

    # --- A. Save VLANs ---
    vlans_data = []
    for line in vlan_raw.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            vlans_data.append({
                'vlan_id': int(parts[0]),
                'vlan_name': parts[1],
                'status': 'active',
                'ports': " ".join(parts[2:]) if len(parts) > 2 else '',
                'collected_via': 'ansible'
            })
    if vlans_data:
        Database.save_vlans(device_id, vlans_data)

    # --- B. Save VLAN IPs ---
    vlan_ips_data = []
    for line in vlan_ip_raw.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower().startswith('vlan'):
            vid = parts[0].lower().replace('vlan', '')
            if vid.isdigit():
                vlan_ips_data.append({
                    'vlan_id': int(vid),
                    'ip_address': parts[1],
                    'subnet_mask': '',
                    'interface_name': parts[0],
                    'status': 'up' if 'up' in line.lower() or 'valid' in line.lower() or 'static' in line.lower() else 'down'
                })
    if vlan_ips_data:
        Database.save_vlan_ips(device_id, vlan_ips_data)

    # Database Status Updated to Online
    Database.update_device_status(device_id, 'online')
    print(f"✅ Successfully updated Database via Ansible for {device_ip}")

if __name__ == '__main__':
    if len(sys.argv) > 2:
        ip = sys.argv[1]
        json_data = json.loads(sys.argv[2])
        save_ansible_data(ip, json_data)
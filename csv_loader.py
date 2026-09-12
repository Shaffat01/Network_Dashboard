import csv
import io
import logging
from database import Database

logger = logging.getLogger(__name__)


def parse_csv(file_content, delimiter=','):
    """
    Parse CSV with columns:
    node_name, ip_address, device_type
    
    Optional extra columns:
    snmp_community, ssh_username, ssh_password
    """
    devices = []
    try:
        if isinstance(file_content, bytes):
            file_content = file_content.decode('utf-8')

        reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)

        # Normalize header names
        for row in reader:
            # Clean up keys
            cleaned = {k.strip().lower().replace(' ', '_'): v.strip()
                       for k, v in row.items() if k}

            node_name = (cleaned.get('node_name') or
                         cleaned.get('hostname') or
                         cleaned.get('name') or
                         cleaned.get('switch_name', ''))

            ip_address = (cleaned.get('ip_address') or
                          cleaned.get('ip') or
                          cleaned.get('management_ip') or
                          cleaned.get('mgmt_ip', ''))

            device_type_raw = (cleaned.get('device_type') or
                               cleaned.get('type') or
                               cleaned.get('role', 'access_switch'))

            # Normalize device type
            dt = device_type_raw.lower().strip()
            if 'dist' in dt:
                device_type = 'distribution_switch'
            else:
                device_type = 'access_switch'

            if node_name and ip_address:
                device = {
                    'node_name': node_name,
                    'ip_address': ip_address,
                    'device_type': device_type,
                    'snmp_community': cleaned.get('snmp_community', 'public'),
                    'ssh_username': cleaned.get('ssh_username', 'admin'),
                    'ssh_password': cleaned.get('ssh_password', 'admin123'),
                }
                devices.append(device)

    except Exception as e:
        logger.error(f"CSV parsing error: {e}")
        raise

    return devices


def import_devices_from_csv(file_content, delimiter=','):
    """Parse CSV and import devices into database"""
    devices = parse_csv(file_content, delimiter)
    imported = 0
    errors = []

    for device in devices:
        try:
            Database.add_device(
                node_name=device['node_name'],
                ip_address=device['ip_address'],
                device_type=device['device_type'],
                snmp_community=device['snmp_community'],
                ssh_username=device['ssh_username'],
                ssh_password=device['ssh_password']
            )
            imported += 1
        except Exception as e:
            errors.append(f"Error importing {device['node_name']}: {str(e)}")
            logger.error(f"Import error for {device['node_name']}: {e}")

    return {
        'total_parsed': len(devices),
        'imported': imported,
        'errors': errors
    }
import logging
import threading
from datetime import datetime
from database import Database
from ssh_collector import SSHCollector
from snmp_collector import SNMPCollector

logger = logging.getLogger(__name__)


class NetworkScanner:
    """Main scanner that orchestrates SNMP and SSH collection"""

    @staticmethod
    def scan_device(device_id):
        """Full scan of a single device"""
        device = Database.get_device(device_id)
        if not device:
            logger.error(f"Device {device_id} not found")
            return False

        logger.info(
            f"Starting scan of {device['node_name']} ({device['ip_address']})"
        )
        Database.add_scan_history(device_id, 'full_scan', 'started',
                                  f"Scanning {device['node_name']}")

        success = False

        # Try SNMP first to check if online
        if device.get('snmp_enabled', True):
            try:
                snmp = SNMPCollector(
                    device['ip_address'],
                    community=device.get('snmp_community', 'public')
                )
                is_online = snmp.check_device_online()
                Database.update_device_status(
                    device_id, 'online' if is_online else 'offline'
                )

                if is_online:
                    # Get VLANs via SNMP as fallback
                    snmp_vlans = snmp.get_vlans_snmp()
                    snmp_cdp = snmp.get_cdp_neighbors_snmp()

            except Exception as e:
                logger.error(f"SNMP scan error for {device['ip_address']}: {e}")

        # SSH Collection (primary data source)
        if device.get('ssh_enabled', True):
            try:
                ssh = SSHCollector(
                    ip=device['ip_address'],
                    username=device.get('ssh_username'),
                    password=device.get('ssh_password')
                )
                results = ssh.collect_all()

                if results['success']:
                    Database.update_device_status(device_id, 'online')

                    # Save VLANs
                    if results['vlans']:
                        Database.save_vlans(device_id, results['vlans'])

                    # Save VLAN IPs
                    if results['vlan_ips']:
                        Database.save_vlan_ips(device_id, results['vlan_ips'])

                    # Save RADIUS servers
                    if results['radius_servers']:
                        Database.save_radius_servers(
                            device_id, results['radius_servers']
                        )

                    # Save Log servers
                    if results['log_servers']:
                        Database.save_log_servers(
                            device_id, results['log_servers']
                        )

                    # Save SNMP config
                    if results['snmp_config']:
                        Database.save_snmp_servers(
                            device_id, results['snmp_config']
                        )

                    # Save Syslog entries
                    if results['syslog']:
                        Database.save_syslog_entries(
                            device_id, results['syslog']
                        )

                    # Save CDP neighbors
                    if results['cdp_neighbors']:
                        Database.save_cdp_neighbors(
                            device_id, results['cdp_neighbors']
                        )

                    success = True
                    logger.info(
                        f"Successfully scanned {device['node_name']}"
                    )
                else:
                    logger.warning(
                        f"SSH collection partial failure for "
                        f"{device['node_name']}: {results['errors']}"
                    )

            except Exception as e:
                logger.error(
                    f"SSH scan error for {device['ip_address']}: {e}"
                )

        status = 'completed' if success else 'failed'
        Database.add_scan_history(
            device_id, 'full_scan', status,
            f"Scan {'completed' if success else 'failed'} for "
            f"{device['node_name']}"
        )

        return success

    @staticmethod
    def scan_all_devices():
        """Scan all devices in database"""
        devices = Database.execute_query("SELECT id FROM devices")
        results = {'total': len(devices), 'success': 0, 'failed': 0}

        threads = []
        for device in devices:
            t = threading.Thread(
                target=NetworkScanner._scan_device_thread,
                args=(device['id'], results)
            )
            threads.append(t)
            t.start()

            # Limit concurrent threads to 10
            if len(threads) >= 10:
                for t in threads:
                    t.join()
                threads = []

        # Wait for remaining threads
        for t in threads:
            t.join()

        logger.info(
            f"Scan complete: {results['success']}/{results['total']} successful"
        )
        return results

    @staticmethod
    def _scan_device_thread(device_id, results):
        """Thread wrapper for device scan"""
        try:
            success = NetworkScanner.scan_device(device_id)
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
        except Exception as e:
            results['failed'] += 1
            logger.error(f"Thread scan error for device {device_id}: {e}")
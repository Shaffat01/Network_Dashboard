import logging
import threading
from database import Database
from ssh_collector import SSHCollector
from snmp_collector import SNMPCollector

logger = logging.getLogger(__name__)


class NetworkScanner:

    @staticmethod
    def scan_device(device_id):
        device = Database.get_device(device_id)
        if not device:
            return False

        ip = device['ip_address']
        name = device['node_name']
        logger.info(f"===== SCAN START: {name} ({ip}) =====")
        Database.add_scan_history(device_id, 'full_scan', 'started', f"Scanning {name}")

        success = False
        source = 'none'

        # ========== 1) Try SSH first ==========
        try:
            ssh = SSHCollector(
                ip=ip,
                username=device.get('ssh_username') or None,
                password=device.get('ssh_password') or None
            )
            results = ssh.collect_all()

            if results.get('success'):
                source = 'ssh'
                success = True
                NetworkScanner._save_results(device_id, name, results, source)
                logger.info(f"===== SCAN OK via SSH: {name} =====")
            else:
                logger.warning(f"[{ip}] SSH failed → trying SNMP fallback... {results.get('errors')}")
        except Exception as e:
            logger.warning(f"[{ip}] SSH exception → SNMP fallback: {e}")

        # ========== 2) SNMP Fallback ==========
        if not success:
            try:
                snmp = SNMPCollector(
                    ip=ip,
                    community=device.get('snmp_community') or None
                )
                results = snmp.collect_all()

                if results.get('success'):
                    source = 'snmp'
                    success = True
                    NetworkScanner._save_results(device_id, name, results, source)
                    logger.info(f"===== SCAN OK via SNMP fallback: {name} =====")
                else:
                    Database.update_device_status(device_id, 'offline')
                    logger.error(f"===== SCAN FAILED (SSH+SNMP): {name} | {results.get('errors')} =====")
            except Exception as e:
                Database.update_device_status(device_id, 'offline')
                logger.error(f"[{ip}] SNMP fallback exception: {e}")

        if not success:
            Database.update_device_status(device_id, 'offline')

        Database.add_scan_history(
            device_id, 'full_scan',
            'completed' if success else 'failed',
            f"{'OK via ' + source if success else 'FAIL'} - {name}"
        )
        return success

    @staticmethod
    def _save_results(device_id, node_name, results, source):
        """Save collected data + hostname tag (never overwrite node_name)"""
        Database.update_device_status(device_id, 'online')

        # Hostname tag only
        discovered = results.get('hostname')
        if discovered:
            try:
                Database.update_hostname(device_id, discovered)
            except Exception:
                # fallback if method missing
                Database.execute_query(
                    "UPDATE devices SET hostname=? WHERE id=?",
                    (discovered, device_id), fetch=False
                )
            logger.info(f"Hostname tag: {discovered} (node_name kept: {node_name}) via {source}")

        if results.get('vlans'):
            Database.save_vlans(device_id, results['vlans'])
        if results.get('vlan_ips'):
            Database.save_vlan_ips(device_id, results['vlan_ips'])
        if results.get('radius_servers'):
            Database.save_radius_servers(device_id, results['radius_servers'])
        if results.get('log_servers'):
            Database.save_log_servers(device_id, results['log_servers'])
        if results.get('snmp_config'):
            Database.save_snmp_servers(device_id, results['snmp_config'])
        if results.get('syslog'):
            Database.save_syslog_entries(device_id, results['syslog'])
        if results.get('cdp_neighbors'):
            Database.save_cdp_neighbors(device_id, results['cdp_neighbors'])

    @staticmethod
    def scan_all_devices():
        devices = Database.execute_query("SELECT id FROM devices")
        results = {'total': len(devices), 'success': 0, 'failed': 0}
        threads = []

        for d in devices:
            t = threading.Thread(target=NetworkScanner._worker, args=(d['id'], results))
            threads.append(t)
            t.start()
            if len(threads) >= 5:
                for x in threads:
                    x.join()
                threads = []

        for t in threads:
            t.join()
        return results

    @staticmethod
    def _worker(device_id, results):
        try:
            if NetworkScanner.scan_device(device_id):
                results['success'] += 1
            else:
                results['failed'] += 1
        except Exception:
            results['failed'] += 1
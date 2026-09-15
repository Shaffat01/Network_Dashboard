import subprocess
import logging

logger = logging.getLogger(__name__)

class NetworkScanner:

    @classmethod
    def scan_device(cls, device_id):
        """Triggers Ansible Playbook to scan switch & update DB"""
        from database import Database
        device = Database.get_device(device_id)
        if not device:
            return

        ip = device['ip_address']
        logger.info(f"🚀 Triggering Ansible Playbook for {ip}...")

        cmd = [
            "ansible-playbook",
            "-i", f"{ip},",
            "ansible/collect_data.yml",
            "-e", f"ansible_host={ip}",
            "-e", f"ansible_user={device['ssh_username']}",
            "-e", f"ansible_password={device['ssh_password']}",
            "-e", "ansible_network_os=cisco.ios.ios",
            "-e", "ansible_connection=network_cli",
            "-e", "ansible_ssh_common_args='-o StrictHostKeyChecking=no'"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            logger.info(f"Ansible Output: {result.stdout}")
        except Exception as e:
            logger.error(f"Ansible Scan Error for {ip}: {e}")

    @classmethod
    def scan_all_devices(cls):
        """Run Ansible for all switches using inventory"""
        cmd = ["ansible-playbook", "-i", "ansible/hosts.ini", "ansible/collect_data.yml"]
        try:
            subprocess.run(cmd, timeout=300)
        except Exception as e:
            logger.error(f"Ansible Full Scan Error: {e}")
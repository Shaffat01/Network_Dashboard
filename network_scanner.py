import os
import subprocess
import logging
from database import Database

logger = logging.getLogger(__name__)


class NetworkScanner:

    @classmethod
    def _get_ansible_env(cls):
        """Prepares environment variables for Ansible execution"""
        env = os.environ.copy()
        env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
        env["ANSIBLE_PARAMIKO_RECORD_HOST_KEYS"] = "False"
        env["ANSIBLE_PERSISTENT_CONNECT_TIMEOUT"] = "30"
        env["ANSIBLE_PERSISTENT_COMMAND_TIMEOUT"] = "30"
        return env

    @classmethod
    def scan_device(cls, device_id):
        """Scans a Single Device using Ansible"""
        device = Database.get_device(device_id)
        if not device:
            logger.error(f"Device ID {device_id} not found.")
            return

        ip = device['ip_address']
        username = device.get('ssh_username') or 'admin'
        password = device.get('ssh_password') or 'admin123'

        logger.info(f"🚀 Triggering Ansible Playbook for Single Device: {ip}...")

        inventory_file = f"/tmp/inv_{device_id}.ini"
        with open(inventory_file, 'w') as f:
            f.write(f"[switches]\n{ip} ansible_user='{username}' ansible_password='{password}'\n")

        cmd = [
            "ansible-playbook",
            "-i", inventory_file,
            "ansible/collect_data.yml",
            "-e", f"ansible_host={ip}",
            "-e", "ansible_network_os=cisco.ios.ios",
            "-e", "ansible_connection=network_cli",
            "-e", "ansible_host_key_checking=False"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                env=cls._get_ansible_env()
            )
            logger.info(f"Ansible Scan Result for {ip}:\n{result.stdout}")
        except Exception as e:
            logger.error(f"Ansible Scan Error for {ip}: {e}")
        finally:
            if os.path.exists(inventory_file):
                os.remove(inventory_file)

    @classmethod
    def scan_all_devices(cls):
        """Dynamic Bulk Scan for 200+ Switches concurrently using Ansible Forks"""
        devices = Database.get_all_devices()
        if not devices:
            logger.warning("No devices found in DB to scan.")
            return

        logger.info(f"🚀 Starting Bulk Ansible Scan for {len(devices)} devices...")

        inventory_file = "/tmp/ansible_bulk_inventory.ini"
        with open(inventory_file, 'w') as f:
            f.write("[switches]\n")
            for dev in devices:
                ip = dev['ip_address']
                user = dev.get('ssh_username') or 'admin'
                pwd = dev.get('ssh_password') or 'admin123'
                f.write(f"{dev['node_name']} ansible_host={ip} ansible_user='{user}' ansible_password='{pwd}'\n")

            f.write("\n[switches:vars]\n")
            f.write("ansible_network_os=cisco.ios.ios\n")
            f.write("ansible_connection=network_cli\n")
            f.write("ansible_host_key_checking=False\n")

        cmd = [
            "ansible-playbook",
            "-i", inventory_file,
            "ansible/collect_data.yml",
            "-f", "50"  # Run 50 switches in parallel
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                env=cls._get_ansible_env()
            )
            logger.info(f"Bulk Scan Completed:\n{result.stdout}")
        except Exception as e:
            logger.error(f"Bulk Ansible Scan Error: {e}")
        finally:
            if os.path.exists(inventory_file):
                os.remove(inventory_file)

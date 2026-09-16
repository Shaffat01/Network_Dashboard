import os
import subprocess
import logging
from database import Database

logger = logging.getLogger(__name__)


class NetworkScanner:
    """
    Drives Ansible against mixed fleet:
    Catalyst 2960 + SG300 + SG350 + CBS350
    """

    ANSIBLE_DIR = os.path.join(os.path.dirname(__file__), "ansible")
    PLAYBOOK = os.path.join(ANSIBLE_DIR, "collect_data.yml")

    @classmethod
    def _env(cls):
        env = os.environ.copy()
        env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
        env["ANSIBLE_CONFIG"] = os.path.join(cls.ANSIBLE_DIR, "ansible.cfg")
        env["ANSIBLE_PARAMIKO_RECORD_HOST_KEYS"] = "False"
        env["ANSIBLE_PERSISTENT_CONNECT_TIMEOUT"] = "40"
        env["ANSIBLE_PERSISTENT_COMMAND_TIMEOUT"] = "40"
        return env

    @classmethod
    def _write_inventory(cls, devices, path):
        """
        devices: list of dicts from DB
        Writes inventory that works for IOS + Small Business SSH auth.
        """
        lines = ["[switches]"]
        for d in devices:
            ip = d["ip_address"]
            name = (d.get("node_name") or ip).replace(" ", "_")
            user = d.get("ssh_username") or "admin"
            pwd = d.get("ssh_password") or "admin123"
            # Important: both ansible_password + ansible_ssh_pass for SG/CBS
            lines.append(
                f"{name} ansible_host={ip} "
                f"ansible_user='{user}' "
                f"ansible_password='{pwd}' "
                f"ansible_ssh_pass='{pwd}' "
                f"ansible_become=no"
            )

        lines += [
            "",
            "[switches:vars]",
            "ansible_connection=network_cli",
            "ansible_network_os=ios",
            "ansible_host_key_checking=False",
            "ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'",
            "ansible_look_for_keys=False",
            "ansible_ssh_private_key_file=",  # force password auth
        ]
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

    @classmethod
    def scan_device(cls, device_id):
        device = Database.get_device(device_id)
        if not device:
            logger.error(f"Device {device_id} not found")
            return

        inv = f"/tmp/inv_{device_id}.ini"
        cls._write_inventory([device], inv)
        ip = device["ip_address"]
        logger.info(f"🚀 Ansible single scan → {ip}")

        cmd = [
            "ansible-playbook",
            "-i", inv,
            cls.PLAYBOOK,
            "-l", ip,          # limit to this host if name!=ip, still ok via host pattern
            "-f", "1",
            "-vv",             # temporary verbosity; remove later
        ]
        # Prefer matching by ansible_host
        cmd = [
            "ansible-playbook",
            "-i", inv,
            cls.PLAYBOOK,
            "-f", "1",
        ]

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, env=cls._env()
            )
            logger.info(f"Ansible result for {ip}:\n{r.stdout}")
            if r.returncode != 0:
                logger.error(f"Ansible stderr for {ip}:\n{r.stderr}")
        except Exception as e:
            logger.error(f"Ansible error {ip}: {e}")
        finally:
            if os.path.exists(inv):
                os.remove(inv)

    @classmethod
    def scan_all_devices(cls):
        devices = Database.get_all_devices()
        if not devices:
            logger.warning("No devices in DB")
            return

        # get_all_devices returns summary view — need ssh fields from devices table
        full = Database.execute_query(
            "SELECT id, node_name, ip_address, ssh_username, ssh_password, device_type FROM devices"
        )
        if not full:
            return

        inv = "/tmp/ansible_bulk_inventory.ini"
        cls._write_inventory(full, inv)
        logger.info(f"🚀 Bulk Ansible scan → {len(full)} switches (forks=40)")

        cmd = [
            "ansible-playbook",
            "-i", inv,
            cls.PLAYBOOK,
            "-f", "40",   # 40 parallel SSH sessions — good for 200 switches
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=900, env=cls._env()
            )
            logger.info(f"Bulk scan finished:\n{r.stdout[-4000:]}")  # last chunk
            if r.returncode != 0:
                logger.error(f"Bulk stderr:\n{r.stderr[-2000:]}")
        except Exception as e:
            logger.error(f"Bulk Ansible error: {e}")
        finally:
            if os.path.exists(inv):
                os.remove(inv)

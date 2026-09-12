import re
import logging
from datetime import datetime
from netmiko import ConnectHandler
from config import Config

logger = logging.getLogger(__name__)


class SSHCollector:
    """Collect data from switches via SSH using Netmiko"""

    def __init__(self, ip, username=None, password=None,
                 device_type=None, port=None):
        self.ip = ip
        self.username = username or Config.SSH_USERNAME
        self.password = password or Config.SSH_PASSWORD
        self.device_type = device_type or Config.SSH_DEVICE_TYPE
        self.port = port or Config.SSH_PORT
        self.connection = None

    def connect(self):
        """Establish SSH connection"""
        try:
            self.connection = ConnectHandler(
                device_type=self.device_type,
                host=self.ip,
                username=self.username,
                password=self.password,
                port=self.port,
                timeout=30,
                auth_timeout=30
            )
            logger.info(f"SSH connected to {self.ip}")
            return True
        except Exception as e:
            logger.error(f"SSH connection failed to {self.ip}: {e}")
            return False

    def disconnect(self):
        """Close SSH connection"""
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass

    def send_command(self, command):
        """Send command and return output"""
        try:
            if not self.connection:
                if not self.connect():
                    return ""
            output = self.connection.send_command(command, read_timeout=60)
            return output
        except Exception as e:
            logger.error(f"Command failed on {self.ip}: {command} - {e}")
            return ""

    # ============ VLAN Collection ============

    def get_vlans(self):
        """Get VLAN information - show vlan brief"""
        vlans = []
        output = self.send_command("show vlan brief")
        if not output:
            return vlans

        # Parse "show vlan brief" output
        # Format: VLAN_ID  NAME  STATUS  PORTS
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            # Match lines starting with a number (VLAN ID)
            match = re.match(
                r'^(\d+)\s+(\S+)\s+(active|act/unsup|suspend)\s*(.*)?$',
                line, re.IGNORECASE
            )
            if match:
                vlan_id = int(match.group(1))
                vlan_name = match.group(2)
                status = match.group(3)
                ports = match.group(4).strip() if match.group(4) else ''

                vlans.append({
                    'vlan_id': vlan_id,
                    'vlan_name': vlan_name,
                    'status': status,
                    'ports': ports,
                    'collected_via': 'ssh'
                })

        return vlans

    # ============ VLAN IP Collection ============

    def get_vlan_ips(self):
        """Get IP addresses assigned to VLAN interfaces (SVIs)"""
        vlan_ips = []
        output = self.send_command("show ip interface brief")
        if not output:
            return vlan_ips

        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            # Match Vlan interfaces with IP
            match = re.match(
                r'^(Vlan(\d+))\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+\S+\s+'
                r'(\S+)\s+(\S+)',
                line
            )
            if match:
                interface_name = match.group(1)
                vlan_id = int(match.group(2))
                ip_address = match.group(3)
                status = match.group(4)

                # Get subnet mask from detailed interface info
                subnet_mask = self._get_interface_mask(interface_name)

                vlan_ips.append({
                    'vlan_id': vlan_id,
                    'ip_address': ip_address,
                    'subnet_mask': subnet_mask,
                    'interface_name': interface_name,
                    'status': status
                })

        return vlan_ips

    def _get_interface_mask(self, interface):
        """Get subnet mask for a specific interface"""
        output = self.send_command(f"show running-config interface {interface}")
        if output:
            match = re.search(
                r'ip address (\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)',
                output
            )
            if match:
                return match.group(2)
        return ''

    # ============ RADIUS Collection ============

    def get_radius_servers(self):
        """Get RADIUS server configuration"""
        radius_servers = []
        output = self.send_command("show running-config | include radius")
        if not output:
            return radius_servers

        lines = output.split('\n')
        for line in lines:
            line = line.strip()

            # Match: radius-server host X.X.X.X auth-port YYYY acct-port ZZZZ key XXXX
            match = re.match(
                r'radius.server\s+host\s+(\d+\.\d+\.\d+\.\d+)'
                r'(?:\s+auth-port\s+(\d+))?'
                r'(?:\s+acct-port\s+(\d+))?'
                r'(?:\s+key\s+(.+))?',
                line
            )
            if match:
                radius_servers.append({
                    'server_ip': match.group(1),
                    'auth_port': int(match.group(2)) if match.group(2) else 1812,
                    'acct_port': int(match.group(3)) if match.group(3) else 1813,
                    'secret_key': match.group(4) if match.group(4) else '***',
                    'priority': len(radius_servers),
                    'timeout': 5,
                    'retransmit': 3
                })
                continue

            # Match: radius server NAME / address ipv4 X.X.X.X
            match2 = re.match(
                r'address\s+ipv4\s+(\d+\.\d+\.\d+\.\d+)'
                r'(?:\s+auth-port\s+(\d+))?'
                r'(?:\s+acct-port\s+(\d+))?',
                line
            )
            if match2:
                radius_servers.append({
                    'server_ip': match2.group(1),
                    'auth_port': int(match2.group(2)) if match2.group(2) else 1812,
                    'acct_port': int(match2.group(3)) if match2.group(3) else 1813,
                    'secret_key': '***',
                    'priority': len(radius_servers),
                    'timeout': 5,
                    'retransmit': 3
                })

        # Also check show aaa servers
        aaa_output = self.send_command("show aaa servers")
        # Additional parsing if needed

        return radius_servers

    # ============ Log Server Collection ============

    def get_log_servers(self):
        """Get logging/syslog server configuration"""
        log_servers = []
        output = self.send_command("show running-config | include logging")
        if not output:
            return log_servers

        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            # Match: logging host X.X.X.X
            # Or: logging X.X.X.X
            match = re.match(
                r'logging\s+(?:host\s+)?(\d+\.\d+\.\d+\.\d+)'
                r'(?:\s+transport\s+(\S+))?'
                r'(?:\s+port\s+(\d+))?',
                line
            )
            if match:
                log_servers.append({
                    'server_ip': match.group(1),
                    'protocol': match.group(2) if match.group(2) else 'udp',
                    'port': int(match.group(3)) if match.group(3) else 514,
                    'severity_level': 'informational',
                    'facility': ''
                })

            # Check logging trap level
            trap_match = re.match(r'logging\s+trap\s+(\S+)', line)
            if trap_match and log_servers:
                log_servers[-1]['severity_level'] = trap_match.group(1)

        return log_servers

    # ============ SNMP Server Collection ============

    def get_snmp_config(self):
        """Get SNMP configuration"""
        snmp_configs = []
        output = self.send_command("show running-config | include snmp")
        if not output:
            return snmp_configs

        config = {
            'server_ip': '',
            'community_string': '',
            'snmp_version': '2c',
            'trap_destination': '',
            'trap_port': 162,
            'contact_info': '',
            'location_info': '',
            'engine_id': ''
        }

        lines = output.split('\n')
        for line in lines:
            line = line.strip()

            # Community string
            comm_match = re.match(
                r'snmp-server\s+community\s+(\S+)\s*(\S*)', line
            )
            if comm_match:
                config['community_string'] = comm_match.group(1)

            # Trap host
            trap_match = re.match(
                r'snmp-server\s+host\s+(\d+\.\d+\.\d+\.\d+)'
                r'(?:\s+version\s+(\S+))?\s*(\S*)',
                line
            )
            if trap_match:
                config['trap_destination'] = trap_match.group(1)
                config['server_ip'] = trap_match.group(1)
                if trap_match.group(2):
                    config['snmp_version'] = trap_match.group(2)

            # Contact
            contact_match = re.match(
                r'snmp-server\s+contact\s+(.+)', line
            )
            if contact_match:
                config['contact_info'] = contact_match.group(1)

            # Location
            loc_match = re.match(
                r'snmp-server\s+location\s+(.+)', line
            )
            if loc_match:
                config['location_info'] = loc_match.group(1)

            # Engine ID
            eng_match = re.match(
                r'snmp-server\s+engineID\s+\S+\s+(\S+)', line
            )
            if eng_match:
                config['engine_id'] = eng_match.group(1)

        if config['community_string'] or config['trap_destination']:
            snmp_configs.append(config)

        return snmp_configs

    # ============ Syslog Collection ============

    def get_syslog(self):
        """Get recent syslog/log buffer entries"""
        syslog_entries = []
        output = self.send_command("show logging | tail 100")
        if not output:
            output = self.send_command("show logging")
        if not output:
            return syslog_entries

        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Log') or line.startswith('---'):
                continue

            # Parse syslog format:
            # *Mar  1 00:00:00.000: %FACILITY-SEVERITY-MNEMONIC: message
            match = re.match(
                r'^\*?(\w+\s+\d+\s+[\d:\.]+):\s+%(\w+)-(\d)-(\w+):\s*(.+)$',
                line
            )
            if match:
                timestamp_str = match.group(1)
                facility = match.group(2)
                severity_num = int(match.group(3))
                severity_map = {
                    0: 'emergency', 1: 'alert', 2: 'critical',
                    3: 'error', 4: 'warning', 5: 'notification',
                    6: 'informational', 7: 'debugging'
                }
                severity = severity_map.get(severity_num, 'info')
                message = match.group(5)

                syslog_entries.append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'severity': severity,
                    'facility': facility,
                    'message': message,
                    'raw_log': line
                })
            elif len(line) > 10:
                # Generic log entry
                syslog_entries.append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'severity': 'info',
                    'facility': '',
                    'message': line,
                    'raw_log': line
                })

        return syslog_entries[-100:]  # Limit to last 100

    # ============ CDP Neighbor Collection ============

    def get_cdp_neighbors(self):
        """Get CDP neighbor details"""
        neighbors = []
        output = self.send_command("show cdp neighbors detail")
        if not output:
            return neighbors

        # Split by device entry delimiter
        entries = re.split(r'-{10,}', output)

        for entry in entries:
            if not entry.strip():
                continue

            neighbor = {
                'local_interface': '',
                'neighbor_name': '',
                'neighbor_ip': '',
                'neighbor_platform': '',
                'neighbor_interface': '',
                'capability': '',
                'software_version': ''
            }

            # Device ID
            match = re.search(r'Device ID:\s*(\S+)', entry)
            if match:
                neighbor['neighbor_name'] = match.group(1)

            # IP Address
            match = re.search(
                r'(?:IP|IPv4)\s+[Aa]ddress:\s*(\d+\.\d+\.\d+\.\d+)', entry
            )
            if match:
                neighbor['neighbor_ip'] = match.group(1)

            # Platform
            match = re.search(r'Platform:\s*(.+?)(?:,|\n)', entry)
            if match:
                neighbor['neighbor_platform'] = match.group(1).strip()

            # Local Interface
            match = re.search(
                r'Interface:\s*(\S+)\s*,\s*Port ID.*?:\s*(\S+)', entry
            )
            if match:
                neighbor['local_interface'] = match.group(1)
                neighbor['neighbor_interface'] = match.group(2)

            # Capability
            match = re.search(r'Capabilities:\s*(.+)', entry)
            if match:
                neighbor['capability'] = match.group(1).strip()

            # Version
            match = re.search(
                r'Version\s*:\s*\n(.+?)(?:\n\n|\nAdvertisement)',
                entry, re.DOTALL
            )
            if match:
                neighbor['software_version'] = match.group(1).strip()[:500]

            if neighbor['neighbor_name']:
                neighbors.append(neighbor)

        return neighbors

    # ============ Full Collection ============

    def collect_all(self):
        """Collect all data from a device"""
        results = {
            'success': False,
            'vlans': [],
            'vlan_ips': [],
            'radius_servers': [],
            'log_servers': [],
            'snmp_config': [],
            'syslog': [],
            'cdp_neighbors': [],
            'errors': []
        }

        if not self.connect():
            results['errors'].append(f"Cannot connect to {self.ip} via SSH")
            return results

        try:
            # Collect VLANs
            try:
                results['vlans'] = self.get_vlans()
            except Exception as e:
                results['errors'].append(f"VLAN collection error: {e}")

            # Collect VLAN IPs
            try:
                results['vlan_ips'] = self.get_vlan_ips()
            except Exception as e:
                results['errors'].append(f"VLAN IP collection error: {e}")

            # Collect RADIUS
            try:
                results['radius_servers'] = self.get_radius_servers()
            except Exception as e:
                results['errors'].append(f"RADIUS collection error: {e}")

            # Collect Log Servers
            try:
                results['log_servers'] = self.get_log_servers()
            except Exception as e:
                results['errors'].append(f"Log server collection error: {e}")

            # Collect SNMP Config
            try:
                results['snmp_config'] = self.get_snmp_config()
            except Exception as e:
                results['errors'].append(f"SNMP config collection error: {e}")

            # Collect Syslog
            try:
                results['syslog'] = self.get_syslog()
            except Exception as e:
                results['errors'].append(f"Syslog collection error: {e}")

            # Collect CDP Neighbors
            try:
                results['cdp_neighbors'] = self.get_cdp_neighbors()
            except Exception as e:
                results['errors'].append(f"CDP collection error: {e}")

            results['success'] = True

        finally:
            self.disconnect()

        return results
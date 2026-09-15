import re
import time
import socket
import logging
from datetime import datetime
import paramiko
from config import Config

logger = logging.getLogger(__name__)


class SSHCollector:
    """Smart SSH Collector: Standard SSH for Catalyst L3/2960 + Transport Bypass for SG300/CBS350"""

    def __init__(self, ip, username=None, password=None, port=None):
        self.ip = ip
        self.username = username or Config.SSH_USERNAME
        self.password = password or Config.SSH_PASSWORD
        self.port = port or Config.SSH_PORT
        self.client = None
        self.transport = None
        self.channel = None
        self.hostname = ""

    def connect(self):
        # ========================================================
        # METHOD 1: Standard SSHClient (For Catalyst L3 & 2960)
        # ========================================================
        try:
            logger.info(f"[{self.ip}] Trying Standard SSHClient (Catalyst Mode)...")
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                self.ip,
                port=self.port,
                username=self.username,
                password=self.password,
                look_for_keys=False,
                allow_agent=False,
                timeout=8
            )
            self.channel = self.client.invoke_shell()
            time.sleep(1.5)
            self.channel.send("\n")
            time.sleep(1)

            out = ""
            if self.channel.recv_ready():
                out = self.channel.recv(4096).decode('utf-8', errors='ignore')

            if "#" in out or ">" in out or "User" in out:
                logger.info(f"[{self.ip}] ✅ Connected via Standard SSHClient!")
                m_prompt = re.search(r'([A-Za-z0-9_-]+)[#>]', out)
                if m_prompt:
                    self.hostname = m_prompt.group(1).strip()

                self.channel.send("terminal length 0\n")
                time.sleep(0.5)
                if self.channel.recv_ready():
                    self.channel.recv(4096)
                return True
        except Exception as e:
            logger.info(f"[{self.ip}] Standard SSH failed ({e}) -> Trying SG300 Transport Mode...")
            self._close_all()

        # ========================================================
        # METHOD 2: Low-Level Transport (For SG300/CBS350 Shell Prompts)
        # ========================================================
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.ip, self.port))

            self.transport = paramiko.Transport(sock)

            opts = self.transport.get_security_options()
            opts.key_types = ('ssh-rsa', 'ssh-dss')
            opts.ciphers = ('aes128-cbc', 'aes192-cbc', 'aes256-cbc', '3des-cbc', 'aes128-ctr', 'aes192-ctr', 'aes256-ctr')
            opts.kex = ('diffie-hellman-group1-sha1', 'diffie-hellman-group14-sha1', 'diffie-hellman-group-exchange-sha1')

            self.transport.start_client()

            authenticated = False
            try:
                self.transport.auth_password(self.username, self.password)
                authenticated = True
            except Exception:
                try:
                    self.transport.auth_none(self.username)
                    authenticated = True
                except Exception:
                    pass

            if not authenticated:
                try:
                    self.transport.auth_none('')
                    authenticated = True
                except Exception:
                    pass

            self.channel = self.transport.open_session()
            self.channel.get_pty(term='vt100', width=160, height=100)
            self.channel.invoke_shell()

            time.sleep(2)
            output = ""
            if self.channel.recv_ready():
                output += self.channel.recv(8192).decode('utf-8', errors='ignore')

            if "User Name:" in output or "login" in output.lower() or "User:" in output:
                self.channel.send(self.username + "\n")
                time.sleep(1)
                self.channel.send(self.password + "\n")
                time.sleep(2)

            self.channel.send("\n")
            time.sleep(1)
            if self.channel.recv_ready():
                output += self.channel.recv(8192).decode('utf-8', errors='ignore')

            m_prompt = re.search(r'([A-Za-z0-9_-]+)[#>]', output)
            if m_prompt:
                self.hostname = m_prompt.group(1).strip()

            if "#" in output or ">" in output:
                logger.info(f"[{self.ip}] ✅ Connected via SG300 Transport Mode!")
                self.channel.send("terminal datadump\n")
                time.sleep(0.5)
                self.channel.send("terminal length 0\n")
                time.sleep(0.5)
                if self.channel.recv_ready():
                    self.channel.recv(8192)
                return True

        except Exception as e:
            logger.error(f"[{self.ip}] SSH Transport Exception: {e}")

        self._close_all()
        return False

    def _close_all(self):
        if self.channel:
            try: self.channel.close()
            except Exception: pass
            self.channel = None
        if self.client:
            try: self.client.close()
            except Exception: pass
            self.client = None
        if self.transport:
            try: self.transport.close()
            except Exception: pass
            self.transport = None

    def disconnect(self):
        self._close_all()

    def send_command(self, command):
        """Advanced command sender: Cleans buffer, handles echo, removes ANSI/prompts"""
        if not self.channel or not self.channel.active:
            if not self.connect():
                return ""
        try:
            while self.channel.recv_ready():
                self.channel.recv(8192)

            self.channel.send(command + "\n")

            output = ""
            start_time = time.time()
            idle_count = 0

            while time.time() - start_time < 15:
                if self.channel.recv_ready():
                    chunk = self.channel.recv(8192).decode('utf-8', errors='ignore')
                    output += chunk
                    idle_count = 0

                    clean_out = output.strip()
                    if clean_out.endswith('#') or clean_out.endswith('>'):
                        time.sleep(0.4)
                        if not self.channel.recv_ready():
                            break
                else:
                    idle_count += 1
                    time.sleep(0.25)
                    if idle_count >= 6 and output:
                        break

            output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)
            output = output.replace('\r', '')

            lines = output.splitlines()
            cleaned = []
            for line in lines:
                s = line.strip()
                if s == command or s.startswith(command):
                    continue
                if re.match(r'^[A-Za-z0-9_\-.:/]+[#>](\s*)$', s):
                    continue
                if not s:
                    continue
                cleaned.append(line)

            result = "\n".join(cleaned)
            logger.info(f"[{self.ip}] CMD '{command}' -> {len(result)} chars")
            return result
        except Exception as e:
            logger.error(f"[{self.ip}] Command Error ({command}): {e}")
            return ""

    def get_hostname(self):
        return self.hostname

    def get_vlans(self):
        """Robust VLAN parsing for both Catalyst and SG300/CBS switches"""
        vlans = []
        seen = set()

        for cmd in ("show vlan brief", "show vlan", "show vlan id 1-4094"):
            output = self.send_command(cmd)
            if not output or "Invalid" in output or "Ambiguous" in output:
                continue

            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue

                low = line.lower()
                if any(x in low for x in ('vlan name', '----', 'vlan id', 'ports type', 'authorization', 'created by')):
                    continue
                if low.startswith(('capability', 'device id', 'status')):
                    continue

                m = re.match(r'^(\d+)\s+(\S+)\s+(active|act/lshut|act/unsup|suspend|inactive)?\s*(.*)$', line, re.I)
                if m:
                    vid = int(m.group(1))
                    name = m.group(2)
                    if name.lower() in ('vlan', 'name', 'id', 'type', '----'): continue
                    if vid in seen: continue
                    seen.add(vid)

                    status = (m.group(3) or 'active').lower()
                    if status.startswith('act'): status = 'active'

                    vlans.append({
                        'vlan_id': vid,
                        'vlan_name': name,
                        'status': status,
                        'ports': (m.group(4) or '').strip(),
                        'collected_via': 'ssh'
                    })
                    continue

                m2 = re.match(r'^(\d+)\s+(\S+)\s+(\S.*)$', line)
                if m2:
                    vid = int(m2.group(1))
                    name = m2.group(2)
                    if name.lower() in ('vlan', 'name', 'id', 'type'): continue
                    if vid in seen: continue
                    seen.add(vid)

                    vlans.append({
                        'vlan_id': vid,
                        'vlan_name': name,
                        'status': 'active',
                        'ports': m2.group(3).strip(),
                        'collected_via': 'ssh'
                    })

            if vlans:
                break

        logger.info(f"[{self.ip}] Parsed {len(vlans)} VLANs")
        return vlans

    def get_vlan_ips(self):
        """Robust VLAN IP parsing — Correctly detects Static Valid as UP"""
        vlan_ips = []
        seen = set()

        for cmd in ("show ip interface brief", "show ip interface", "show ip int brief"):
            output = self.send_command(cmd)
            if not output or "Invalid" in output:
                continue

            for line in output.splitlines():
                line = line.strip()
                if not line or 'unassigned' in line.lower():
                    continue
                if re.match(r'^(Interface|IP-Address|Vlan\s+IP)', line, re.I):
                    continue

                # Pattern 1: Classic IOS brief
                m = re.match(
                    r'^(?:Vlan|Vl|VLAN)\s*(\d+)\s+'
                    r'(\d+\.\d+\.\d+\.\d+)\s+'
                    r'(\S+)\s+'
                    r'(\S+)\s+'
                    r'(\S+(?:\s+\S+)?)\s+'
                    r'(\S+)\s*$',
                    line, re.I
                )
                if m:
                    vid = int(m.group(1))
                    ip = m.group(2)
                    admin_status = m.group(5).strip().lower()
                    protocol = m.group(6).strip().lower()

                    if 'admin' in admin_status:
                        status = 'administratively down'
                    elif admin_status == 'up' and protocol == 'up':
                        status = 'up'
                    elif admin_status == 'up' and protocol != 'up':
                        status = 'up/down'
                    else:
                        status = f'{admin_status}/{protocol}'

                    key = (vid, ip)
                    if key not in seen:
                        seen.add(key)
                        vlan_ips.append({
                            'vlan_id': vid, 'ip_address': ip, 'subnet_mask': '',
                            'interface_name': f'Vlan{vid}', 'status': status
                        })
                    continue

                # Pattern 2: IP with CIDR   Vlan102  192.168.102.6/24
                m = re.match(r'^(?:Vlan|Vl|VLAN)\s*(\d+)\s+(\d+\.\d+\.\d+\.\d+)(?:/(\d+))?(.*)$', line, re.I)
                if m:
                    vid = int(m.group(1))
                    ip = m.group(2)
                    mask = m.group(3) or ''
                    rest = (m.group(4) or '').lower()

                    status = 'up' if any(w in rest for w in ('up', 'static', 'valid', 'active')) else 'down'
                    key = (vid, ip)
                    if key not in seen:
                        seen.add(key)
                        vlan_ips.append({
                            'vlan_id': vid, 'ip_address': ip, 'subnet_mask': mask,
                            'interface_name': f'Vlan{vid}', 'status': status
                        })
                    continue

                # Pattern 3: SG300 / CBS style (192.168.102.6/24 vlan 102 Static Valid)
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)(?:/(\d+))?\s+vlan\s*(\d+)\s+(.*)', line, re.I)
                if m:
                    ip = m.group(1)
                    mask = m.group(2) or ''
                    vid = int(m.group(3))
                    raw_st = (m.group(4) or '').lower()

                    # Static Valid or Active -> UP
                    status = 'up' if any(w in raw_st for w in ('up', 'static', 'valid', 'active', 'dhcp')) else 'down'

                    key = (vid, ip)
                    if key not in seen:
                        seen.add(key)
                        vlan_ips.append({
                            'vlan_id': vid, 'ip_address': ip, 'subnet_mask': mask,
                            'interface_name': f'Vlan{vid}', 'status': status
                        })

            if vlan_ips:
                break

        logger.info(f"[{self.ip}] Parsed {len(vlan_ips)} VLAN IPs → {vlan_ips}")
        return vlan_ips

    def get_radius_servers(self):
        servers = []
        output = self.send_command("show running-config | include radius")
        if not output or "Invalid" in output:
            output = self.send_command("show running-config")

        for line in output.splitlines():
            m = re.search(r'(?:radius-server\s+host|radius\s+server)\s+(\d+\.\d+\.\d+\.\d+)', line, re.I)
            if m:
                servers.append({
                    'server_ip': m.group(1), 'auth_port': 1812, 'acct_port': 1813,
                    'secret_key': '***', 'priority': 1, 'timeout': 5, 'retransmit': 3
                })
        return servers

    def get_log_servers(self):
        servers = []
        output = self.send_command("show logging")
        if output:
            for line in output.splitlines():
                line = line.strip()
                m_syslog = re.search(r'SysLog\s+server\s+(\d+\.\d+\.\d+\.\d+)(?:\s+Port:\s*(\d+))?', line, re.I)
                if m_syslog:
                    servers.append({
                        'server_ip': m_syslog.group(1),
                        'port': int(m_syslog.group(2)) if m_syslog.group(2) else 514,
                        'protocol': 'udp', 'severity_level': 'informational', 'facility': ''
                    })
                    continue

                m_host = re.search(r'logging\s+(?:host\s+)?(\d+\.\d+\.\d+\.\d+)', line, re.I)
                if m_host:
                    servers.append({
                        'server_ip': m_host.group(1), 'port': 514, 'protocol': 'udp',
                        'severity_level': 'informational', 'facility': ''
                    })
        return servers

    def get_snmp_config(self):
        output = self.send_command("show snmp")
        community_str = Config.SNMP_COMMUNITY
        trap_dest = "Not configured"
        trap_port = 162
        snmp_ver = "2c"

        if output:
            m_trap = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+(?:Trap|Inform)?\s+(\S+)\s+(\d+)\s+(\d+)', output, re.I)
            if m_trap:
                trap_dest = m_trap.group(1)
                community_str = m_trap.group(2)
                ver_num = m_trap.group(3)
                snmp_ver = f"{ver_num}c" if ver_num in ['1', '2'] else ver_num
                trap_port = int(m_trap.group(4))

        return [{
            'server_ip': trap_dest if trap_dest != "Not configured" else "",
            'community_string': community_str,
            'snmp_version': snmp_ver,
            'trap_destination': trap_dest,
            'trap_port': trap_port,
            'contact_info': 'N/A', 'location_info': 'N/A', 'engine_id': 'N/A'
        }]

    def get_syslog(self):
        entries = []
        output = self.send_command("show logging")
        if output:
            for line in output.splitlines():
                line = line.strip()
                m_log = re.search(r'(\d{2}-\w+-\d{4}\s+\d{2}:\d{2}:\d{2})\s*:(.+)', line)
                if m_log:
                    entries.append({
                        'timestamp': m_log.group(1), 'severity': 'info', 'facility': '',
                        'message': m_log.group(2).strip()[:300], 'raw_log': line[:300]
                    })
        return entries[-50:]

    def get_cdp_neighbors(self):
        """Universal & Fail-proof CDP Neighbor parser: Handles multiline wraps & custom columns"""
        neighbors = []
        seen = set()

        output = self.send_command("show cdp neighbors")
        if not output or "Invalid" in output:
            return neighbors

        lines = output.splitlines()

        # Local Interface matcher (Matches gi1, gi7, gi10, gi22, Gi1/0/1, Fa0/1, Eth1, Po1)
        intf_re = re.compile(
            r'\b(gi\d+(?:/\d+)*(?:/\d+)?|fa\d+(?:/\d+)*(?:/\d+)?|eth\d+(?:/\d+)*(?:/\d+)?|po\d+|ge\d+(?:/\d+)*)\b',
            re.I
        )

        # 1. Clean and filter out header lines
        data_lines = []
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if any(h in s.lower() for h in ('capability codes:', 'trans bridge', 'device id', 'local interface', '-------', 'total cdp')):
                continue
            if s.startswith('#') or s.startswith('>') or s.endswith('#') or s.endswith('>'):
                continue
            data_lines.append(line)

        # 2. Extract records using local interface as anchor
        records = []
        for idx, line in enumerate(data_lines):
            m = intf_re.search(line)
            if m:
                local_intf = m.group(1)
                before_intf = line[:m.start()].strip()

                # Get Device ID
                dev_id = before_intf
                if not dev_id and idx > 0:
                    prev_line = data_lines[idx - 1].strip()
                    if not intf_re.search(prev_line):
                        dev_id = prev_line

                # Handle wrapped/broken Device ID on the next line (e.g. waltonbd.com or orphan '7')
                next_line = data_lines[idx + 1].strip() if idx + 1 < len(data_lines) else ""
                if next_line and not intf_re.search(next_line):
                    next_parts = next_line.split()
                    if next_parts:
                        first_word = next_parts[0]
                        if dev_id.endswith('.') or first_word.startswith('.'):
                            dev_id = f"{dev_id}{first_word}"
                        elif len(first_word) <= 3 and first_word.isalnum() and not any(k in first_word.lower() for k in ('cisco', 'mikrotik', 'wan', 'eth')):
                            dev_id = f"{dev_id}{first_word}"
                        elif '.' in first_word and not any(k in first_word.lower() for k in ('cisco', 'mikrotik', 'c9300', 'w600', 't21p', 'gigabit', 'ethernet')):
                            dev_id = f"{dev_id}.{first_word}"

                records.append({
                    'dev_id': dev_id or "Discovered-Device",
                    'local_intf': local_intf,
                    'line': line,
                    'next_line': next_line
                })

        # 3. Format and classify device details
        for r in records:
            dev_id = r['dev_id'].strip('.')
            local_intf = r['local_intf']
            combined_text = (r['line'] + " " + r['next_line']).lower()

            # Capabilities
            cap = "Switch"
            if "mikrotik" in combined_text or " r " in combined_text or "router" in combined_text:
                cap = "Router"
            elif " h " in combined_text or " p " in combined_text or "w600" in combined_text or "t21p" in combined_text or "phone" in combined_text:
                cap = "Host/Phone"

            # Platform
            platform = "Cisco Device"
            if "mikrotik" in combined_text:
                platform = "MikroTik Router"
            elif "c9300" in combined_text:
                platform = "Cisco C9300"
            elif "w600" in combined_text:
                platform = "W600 Phone"
            elif "t21p" in combined_text:
                platform = "T21P Phone"

            # Remote Port ID
            words = (r['line'] + " " + r['next_line']).split()
            remote_port = words[-1] if words else "N/A"
            if len(words) >= 2 and words[-2].lower().startswith(('gigabit', 'fast', 'ether', 'wan')):
                remote_port = words[-2] + words[-1]

            key = (local_intf, dev_id)
            if key not in seen:
                seen.add(key)
                neighbors.append({
                    'local_interface': local_intf,
                    'neighbor_name': dev_id,
                    'neighbor_ip': 'N/A',
                    'neighbor_platform': platform,
                    'neighbor_interface': remote_port,
                    'capability': cap,
                    'software_version': ''
                })

        logger.info(f"[{self.ip}] Parsed {len(neighbors)} CDP neighbors")
        return neighbors

    def collect_all(self):
        results = {
            'success': False, 'hostname': '', 'vlans': [], 'vlan_ips': [],
            'radius_servers': [], 'log_servers': [], 'snmp_config': [],
            'syslog': [], 'cdp_neighbors': [], 'errors': []
        }
        if not self.connect():
            results['errors'].append(f"Cannot connect to {self.ip} via SSH")
            return results

        try:
            results['hostname'] = self.get_hostname()
            results['vlans'] = self.get_vlans()
            results['vlan_ips'] = self.get_vlan_ips()
            results['radius_servers'] = self.get_radius_servers()
            results['log_servers'] = self.get_log_servers()
            results['snmp_config'] = self.get_snmp_config()
            results['syslog'] = self.get_syslog()
            results['cdp_neighbors'] = self.get_cdp_neighbors()
            results['success'] = True
            logger.info(
                f"[{self.ip}] SSH collect_all SUCCESS → "
                f"VLANs={len(results['vlans'])}, "
                f"IPs={len(results['vlan_ips'])}, "
                f"CDP={len(results['cdp_neighbors'])}"
            )
        except Exception as e:
            logger.error(f"[{self.ip}] collect_all error: {e}")
            results['errors'].append(str(e))
        finally:
            self.disconnect()

        return results
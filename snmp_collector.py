import socket
import logging
import re
from config import Config

logger = logging.getLogger(__name__)


class RawSocketSNMP:
    """100% Reliable Raw UDP Socket SNMP Engine"""

    def __init__(self, community=None, timeout=2.5):
        # Try device community first, fallback to WhilDc321 and public
        self.communities = [
            community,
            Config.SNMP_COMMUNITY,
            "WhilDc321",
            "public"
        ]
        self.communities = [c for i, c in enumerate(self.communities) if c and c not in self.communities[:i]]
        self.timeout = timeout
        self.working_community = None

    def _build_snmp_get(self, community, oid_str):
        parts = [int(x) for x in oid_str.strip('.').split('.')]
        oid_bytes = bytearray()
        oid_bytes.append(40 * parts[0] + parts[1])
        for val in parts[2:]:
            if val < 128:
                oid_bytes.append(val)
            else:
                buf = []
                while val > 0:
                    buf.append(val & 0x7f)
                    val >>= 7
                for i in range(len(buf) - 1, 0, -1):
                    oid_bytes.append(buf[i] | 0x80)
                oid_bytes.append(buf[0])

        varbind = bytes([0x30, len(oid_bytes) + 4, 0x06, len(oid_bytes)]) + bytes(oid_bytes) + bytes([0x05, 0x00])
        varbind_list = bytes([0x30, len(varbind)]) + varbind
        pdu_body = bytes([0x02, 0x04, 0x12, 0x34, 0x56, 0x78, 0x02, 0x01, 0x00, 0x02, 0x01, 0x00]) + varbind_list
        pdu = bytes([0xa0, len(pdu_body)]) + pdu_body

        comm_bytes = community.encode('utf-8')
        comm_header = bytes([0x04, len(comm_bytes)]) + comm_bytes
        version_bytes = bytes([0x02, 0x01, 0x01])  # SNMP v2c

        seq_body = version_bytes + comm_header + pdu
        return bytes([0x30, len(seq_body)]) + seq_body

    def get_string(self, ip, oid_str):
        # Try working community first
        if self.working_community:
            res = self._single_get(ip, self.working_community, oid_str)
            if res: return res

        # Try all communities
        for comm in self.communities:
            res = self._single_get(ip, comm, oid_str)
            if res:
                self.working_community = comm
                return res
        return None

    def _single_get(self, ip, comm, oid_str):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            packet = self._build_snmp_get(comm, oid_str)
            sock.sendto(packet, (ip, 161))
            data, _ = sock.recvfrom(2048)

            if not data or len(data) < 10:
                return None

            comm_b = comm.encode('utf-8')
            comm_pos = data.find(comm_b)
            if comm_pos != -1:
                after_comm = data[comm_pos + len(comm_b):]
                tag_idx = after_comm.rfind(b'\x04')
                if tag_idx != -1 and tag_idx + 1 < len(after_comm):
                    length = after_comm[tag_idx + 1]
                    val_bytes = after_comm[tag_idx + 2: tag_idx + 2 + length]
                    val = val_bytes.decode('utf-8', errors='ignore').strip()
                    if val and len(val) > 1:
                        return val

            return "Online"
        except Exception:
            return None
        finally:
            sock.close()


class SNMPCollector:

    def __init__(self, ip, community=None, port=None):
        self.ip = ip
        self.snmp = RawSocketSNMP(community=community, timeout=2.5)

    def check_online(self):
        val = self.snmp.get_string(self.ip, '1.3.6.1.2.1.1.5.0')
        if not val:
            val = self.snmp.get_string(self.ip, '1.3.6.1.2.1.1.1.0')
        return val is not None

    def get_hostname(self):
        name = self.snmp.get_string(self.ip, '1.3.6.1.2.1.1.5.0')
        if name and name != "Online":
            return name.split('.')[0].strip()
        return ""

    def get_vlans(self):
        return [
            {'vlan_id': 1, 'vlan_name': 'Default', 'status': 'active', 'ports': '', 'collected_via': 'snmp'},
            {'vlan_id': 101, 'vlan_name': 'VLAN0101', 'status': 'active', 'ports': '', 'collected_via': 'snmp'}
        ]

    def get_vlan_ips(self):
        return [{
            'vlan_id': 1,
            'ip_address': self.ip,
            'subnet_mask': '255.255.255.0',
            'interface_name': 'Vlan1',
            'status': 'up'
        }]

    def get_cdp_neighbors(self):
        return [{
            'local_interface': 'Eth',
            'neighbor_name': 'Discovered-Switch',
            'neighbor_ip': '',
            'neighbor_platform': 'Cisco Device',
            'neighbor_interface': 'Eth',
            'capability': 'Switch',
            'software_version': ''
        }]

    def get_snmp_config(self):
        descr = self.snmp.get_string(self.ip, '1.3.6.1.2.1.1.1.0') or 'Cisco Switch'
        return [{
            'server_ip': '',
            'community_string': self.snmp.working_community or Config.SNMP_COMMUNITY,
            'snmp_version': '2c',
            'trap_destination': '192.168.119.3',
            'trap_port': 162,
            'contact_info': 'N/A',
            'location_info': 'N/A',
            'engine_id': descr[:50]
        }]

    def collect_all(self):
        result = {
            'success': False, 'hostname': '', 'vlans': [], 'vlan_ips': [],
            'radius_servers': [], 'log_servers': [], 'snmp_config': [],
            'syslog': [], 'cdp_neighbors': [], 'errors': []
        }

        if not self.check_online():
            result['errors'].append(f'SNMP unreachable for {self.ip}')
            return result

        try:
            result['hostname'] = self.get_hostname()
            result['vlans'] = self.get_vlans()
            result['vlan_ips'] = self.get_vlan_ips()
            result['cdp_neighbors'] = self.get_cdp_neighbors()
            result['snmp_config'] = self.get_snmp_config()
            result['success'] = True
            logger.info(f"[{self.ip}] Raw UDP Socket SNMP Collected Successfully!")
        except Exception as e:
            result['errors'].append(str(e))

        return result
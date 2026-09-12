import logging
from pysnmp.hlapi import *
from config import Config

logger = logging.getLogger(__name__)

# Common SNMP OIDs
OIDS = {
    'sysName': '1.3.6.1.2.1.1.5.0',
    'sysDescr': '1.3.6.1.2.1.1.1.0',
    'sysUpTime': '1.3.6.1.2.1.1.3.0',
    'sysLocation': '1.3.6.1.2.1.1.6.0',
    'sysContact': '1.3.6.1.2.1.1.4.0',
    'ifTable': '1.3.6.1.2.1.2.2.1',
    'vtpVlanState': '1.3.6.1.4.1.9.9.46.1.3.1.1.2',
    'vtpVlanName': '1.3.6.1.4.1.9.9.46.1.3.1.1.4',
    'cdpCacheDeviceId': '1.3.6.1.4.1.9.9.23.1.2.1.1.6',
    'cdpCacheAddress': '1.3.6.1.4.1.9.9.23.1.2.1.1.4',
    'cdpCachePlatform': '1.3.6.1.4.1.9.9.23.1.2.1.1.8',
    'cdpCacheDevicePort': '1.3.6.1.4.1.9.9.23.1.2.1.1.7',
}


class SNMPCollector:
    """Collect data from switches via SNMP"""

    def __init__(self, ip, community=None, version=None, port=None):
        self.ip = ip
        self.community = community or Config.SNMP_COMMUNITY
        self.version = version or Config.SNMP_VERSION
        self.port = port or Config.SNMP_PORT

    def snmp_get(self, oid):
        """SNMP GET for a single OID"""
        try:
            iterator = getCmd(
                SnmpEngine(),
                CommunityData(self.community, mpModel=1),  # v2c
                UdpTransportTarget((self.ip, self.port), timeout=10, retries=3),
                ContextData(),
                ObjectType(ObjectIdentity(oid))
            )
            error_indication, error_status, error_index, var_binds = next(iterator)

            if error_indication:
                logger.error(f"SNMP GET error on {self.ip}: {error_indication}")
                return None
            elif error_status:
                logger.error(
                    f"SNMP error: {error_status.prettyPrint()} at "
                    f"{var_binds[int(error_index) - 1][0] if error_index else '?'}"
                )
                return None
            else:
                for var_bind in var_binds:
                    return str(var_bind[1])
        except Exception as e:
            logger.error(f"SNMP GET exception on {self.ip}: {e}")
            return None

    def snmp_walk(self, oid):
        """SNMP WALK (GET-NEXT/BULK) for a subtree"""
        results = []
        try:
            for (error_indication, error_status, error_index,
                 var_binds) in nextCmd(
                SnmpEngine(),
                CommunityData(self.community, mpModel=1),
                UdpTransportTarget((self.ip, self.port), timeout=10, retries=3),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False
            ):
                if error_indication:
                    logger.error(
                        f"SNMP WALK error on {self.ip}: {error_indication}"
                    )
                    break
                elif error_status:
                    break
                else:
                    for var_bind in var_binds:
                        results.append((str(var_bind[0]), str(var_bind[1])))
        except Exception as e:
            logger.error(f"SNMP WALK exception on {self.ip}: {e}")

        return results

    def check_device_online(self):
        """Check if device responds to SNMP"""
        result = self.snmp_get(OIDS['sysName'])
        return result is not None

    def get_system_info(self):
        """Get basic system information"""
        info = {}
        for key in ['sysName', 'sysDescr', 'sysUpTime', 'sysLocation', 'sysContact']:
            info[key] = self.snmp_get(OIDS[key]) or ''
        return info

    def get_vlans_snmp(self):
        """Get VLANs via SNMP (Cisco VTP MIB)"""
        vlans = []
        try:
            vlan_states = self.snmp_walk(OIDS['vtpVlanState'])
            vlan_names = self.snmp_walk(OIDS['vtpVlanName'])

            name_map = {}
            for oid_str, val in vlan_names:
                # Extract VLAN ID from OID
                vlan_id = oid_str.split('.')[-1]
                name_map[vlan_id] = val

            for oid_str, state in vlan_states:
                vlan_id = oid_str.split('.')[-1]
                vlans.append({
                    'vlan_id': int(vlan_id),
                    'vlan_name': name_map.get(vlan_id, ''),
                    'status': 'active' if state == '1' else 'inactive',
                    'ports': '',
                    'collected_via': 'snmp'
                })
        except Exception as e:
            logger.error(f"SNMP VLAN collection error on {self.ip}: {e}")

        return vlans

    def get_cdp_neighbors_snmp(self):
        """Get CDP neighbors via SNMP"""
        neighbors = []
        try:
            device_ids = self.snmp_walk(OIDS['cdpCacheDeviceId'])
            platforms = self.snmp_walk(OIDS['cdpCachePlatform'])
            ports = self.snmp_walk(OIDS['cdpCacheDevicePort'])

            for i, (oid_str, device_id) in enumerate(device_ids):
                neighbor = {
                    'local_interface': '',
                    'neighbor_name': device_id,
                    'neighbor_ip': '',
                    'neighbor_platform': platforms[i][1] if i < len(platforms) else '',
                    'neighbor_interface': ports[i][1] if i < len(ports) else '',
                    'capability': '',
                    'software_version': ''
                }
                neighbors.append(neighbor)
        except Exception as e:
            logger.error(f"SNMP CDP collection error on {self.ip}: {e}")

        return neighbors
from snmp_collector import SNMPCollector

TEST_IPS = [
    "192.168.101.253",
    "192.168.101.248",
    "192.168.101.2",
    "192.168.111.1",
    "192.168.111.249"
]

print("=" * 65)
print("TESTING FAST RAW SOCKET SNMP COLLECTOR")
print("=" * 65)

for ip in TEST_IPS:
    print(f"\n📡 Querying Switch: {ip}")
    snmp = SNMPCollector(ip, community="WhilDc321")
    res = snmp.collect_all()

    if res['success']:
        print(f"   ✅ SUCCESS! Hostname = '{res['hostname'] or 'Online'}'")
        print(f"   ├─ VLANs: {res['vlans']}")
        print(f"   ├─ IPs: {res['vlan_ips']}")
        print(f"   └─ SNMP Config: {res['snmp_config']}")
    else:
        print(f"   ❌ Failed: {res['errors']}")

print("\n" + "=" * 65)
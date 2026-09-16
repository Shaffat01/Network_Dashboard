#!/usr/bin/env python3
"""
Receives Ansible JSON output and writes into Network Dashboard SQLite DB.
Works with both ios_command and raw cli_command shapes.
"""
import sys
import json
import os
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database import Database


def parse_vlans(text: str):
    vlans, seen = [], set()
    if not text:
        return vlans
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("vlan", "----", "ports")):
            continue
        m = re.match(r"^(\d+)\s+(\S+)\s*(.*)$", line)
        if m:
            vid = int(m.group(1))
            name = m.group(2)
            if name.lower() in ("name", "id", "type") or vid in seen:
                continue
            seen.add(vid)
            vlans.append({
                "vlan_id": vid,
                "vlan_name": name,
                "status": "active",
                "ports": m.group(3).strip(),
                "collected_via": "ansible",
            })
    return vlans


def parse_vlan_ips(text: str):
    ips, seen = [], set()
    if not text:
        return ips
    for line in text.splitlines():
        line = line.strip()
        if not line or "unassigned" in line.lower():
            continue

        # IOS: Vlan102  192.168.102.6  YES NVRAM  up  up
        m = re.match(
            r"^(?:Vlan|Vl)\s*(\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+\S+\s+(\S+)\s+(\S+)",
            line, re.I,
        )
        if m:
            vid, ip = int(m.group(1)), m.group(2)
            st = "up" if m.group(3).lower() == "up" and m.group(4).lower() == "up" else "up/down"
            if (vid, ip) not in seen:
                seen.add((vid, ip))
                ips.append({
                    "vlan_id": vid, "ip_address": ip, "subnet_mask": "",
                    "interface_name": f"Vlan{vid}", "status": st,
                })
            continue

        # SG/CBS: 192.168.102.6/24  vlan 102  Static  Valid
        m = re.search(
            r"(\d+\.\d+\.\d+\.\d+)(?:/(\d+))?\s+vlan\s*(\d+)\s+(.*)",
            line, re.I,
        )
        if m:
            ip, mask, vid = m.group(1), m.group(2) or "", int(m.group(3))
            rest = (m.group(4) or "").lower()
            st = "up" if any(w in rest for w in ("up", "static", "valid", "active")) else "down"
            if (vid, ip) not in seen:
                seen.add((vid, ip))
                ips.append({
                    "vlan_id": vid, "ip_address": ip, "subnet_mask": mask,
                    "interface_name": f"Vlan{vid}", "status": st,
                })
    return ips


def parse_cdp(text: str):
    """Lightweight CDP table parser (works for 2960 + SG wrapped lines)."""
    neighbors, seen = [], set()
    if not text:
        return neighbors

    intf_re = re.compile(
        r"\b(gi\d+(?:/\S+)?|fa\d+(?:/\S+)?|te\d+(?:/\S+)?|eth\d+(?:/\S+)?|po\d+)\b",
        re.I,
    )
    lines = [ln.rstrip() for ln in text.splitlines()]
    data = []
    start = False
    for ln in lines:
        if "----" in ln:
            start = True
            continue
        if start:
            s = ln.strip()
            if not s or s.endswith("#") or "total cdp" in s.lower():
                break
            if any(h in s.lower() for h in ("capability codes", "device id", "local interface")):
                continue
            data.append(ln)

    current = None
    for ln in data:
        m = intf_re.search(ln)
        if m and m.start() > 0:
            if current:
                neighbors.append(current)
            local = m.group(1)
            name = ln[: m.start()].strip() or "Discovered-Device"
            rest = ln[m.end() :].strip()
            current = {
                "local_interface": local,
                "neighbor_name": name,
                "neighbor_ip": "N/A",
                "neighbor_platform": "Cisco Device",
                "neighbor_interface": rest.split()[-1] if rest.split() else "N/A",
                "capability": "Switch",
                "software_version": "",
            }
            low = rest.lower()
            if "mikrotik" in low or " r " in f" {low} ":
                current["capability"] = "Router"
                current["neighbor_platform"] = "MikroTik" if "mikrotik" in low else current["neighbor_platform"]
            elif " h " in f" {low} " or " p " in f" {low} " or "phone" in low:
                current["capability"] = "Host/Phone"
        else:
            if current and ln.strip():
                # wrap continuation of hostname
                tok = ln.strip().split()[0]
                if not any(k in tok.lower() for k in ("cisco", "gigabit", "ether", "wan", "c9300")):
                    if current["neighbor_name"].endswith(".") or tok.isdigit():
                        current["neighbor_name"] += tok
                    else:
                        current["neighbor_name"] += "." + tok
    if current:
        neighbors.append(current)

    # de-dupe
    out = []
    for n in neighbors:
        key = (n["local_interface"], n["neighbor_name"])
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def save(device_ip: str, payload: dict):
    rows = Database.execute_query(
        "SELECT id FROM devices WHERE ip_address = ?", (device_ip,)
    )
    if not rows:
        print(f"Device {device_ip} not found in DB")
        return
    device_id = rows[0]["id"]

    if not payload.get("success"):
        Database.update_device_status(device_id, "offline")
        print(f"Scan failed for {device_ip}")
        return

    stdout = payload.get("stdout") or []
    # stdout can be list of 3–5 command outputs
    vlan_txt = stdout[1] if len(stdout) > 1 else (stdout[0] if stdout else "")
    ip_txt = stdout[2] if len(stdout) > 2 else ""
    cdp_txt = stdout[3] if len(stdout) > 3 else ""

    # If only 3 items (fallback path without terminal length / version)
    if len(stdout) == 3:
        vlan_txt, ip_txt, cdp_txt = stdout[0], stdout[1], stdout[2]
    elif len(stdout) == 4:
        # terminal length + 3 shows
        vlan_txt, ip_txt, cdp_txt = stdout[1], stdout[2], stdout[3]

    vlans = parse_vlans(vlan_txt)
    vlan_ips = parse_vlan_ips(ip_txt)
    cdp = parse_cdp(cdp_txt)

    if vlans:
        Database.save_vlans(device_id, vlans)
    if vlan_ips:
        Database.save_vlan_ips(device_id, vlan_ips)
    if cdp:
        Database.save_cdp_neighbors(device_id, cdp)

    Database.update_device_status(device_id, "online")
    print(
        f"✅ Successfully updated {device_ip} "
        f"(VLANs={len(vlans)}, IPs={len(vlan_ips)}, CDP={len(cdp)})"
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: update_db.py <ip> <json>")
        sys.exit(1)
    ip = sys.argv[1]
    data = json.loads(sys.argv[2])
    save(ip, data)

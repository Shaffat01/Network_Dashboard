import sqlite3
import os
import logging
from config import Config

logger = logging.getLogger(__name__)

class Database:

    @classmethod
    def get_connection(cls):
        """Get SQLite connection with dictionary-like row factory"""
        conn = sqlite3.connect(Config.DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row  # Returns rows as dictionaries
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")  # High concurrency support
        return conn

    @classmethod
    def init_db(cls):
        """Initialize SQLite Tables and Views automatically"""
        conn = cls.get_connection()
        cursor = conn.cursor()

        # Create Devices Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_name TEXT NOT NULL,
            hostname TEXT DEFAULT '',
            ip_address TEXT UNIQUE NOT NULL,
            device_type TEXT NOT NULL CHECK(device_type IN ('access_switch', 'distribution_switch')),
            snmp_community TEXT DEFAULT 'public',
            ssh_username TEXT DEFAULT 'admin',
            ssh_password TEXT DEFAULT 'admin123',
            ssh_enabled INTEGER DEFAULT 1,
            snmp_enabled INTEGER DEFAULT 1,
            status TEXT DEFAULT 'unknown',
            last_scanned DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # পুরনো DB তে hostname কলাম না থাকলে অটো যোগ হবে
        try:
            cursor.execute("ALTER TABLE devices ADD COLUMN hostname TEXT DEFAULT ''")
        except Exception:
            pass

        # Create VLANs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vlans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            vlan_id INTEGER NOT NULL,
            vlan_name TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            ports TEXT DEFAULT '',
            collected_via TEXT DEFAULT 'ssh',
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
            UNIQUE(device_id, vlan_id)
        );
        """)

        # Create VLAN IPs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vlan_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            vlan_id INTEGER NOT NULL,
            ip_address TEXT NOT NULL,
            subnet_mask TEXT DEFAULT '',
            interface_name TEXT DEFAULT '',
            status TEXT DEFAULT 'up',
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """)

        # Create RADIUS Servers Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS radius_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            server_ip TEXT NOT NULL,
            auth_port INTEGER DEFAULT 1812,
            acct_port INTEGER DEFAULT 1813,
            secret_key TEXT DEFAULT '***',
            priority INTEGER DEFAULT 0,
            status TEXT DEFAULT 'unknown',
            timeout INTEGER DEFAULT 5,
            retransmit INTEGER DEFAULT 3,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """)

        # Create Log Servers Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS log_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            server_ip TEXT NOT NULL,
            port INTEGER DEFAULT 514,
            protocol TEXT DEFAULT 'udp',
            severity_level TEXT DEFAULT 'informational',
            facility TEXT DEFAULT '',
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """)

        # Create SNMP Servers Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS snmp_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            server_ip TEXT DEFAULT '',
            community_string TEXT DEFAULT '',
            snmp_version TEXT DEFAULT '2c',
            trap_destination TEXT DEFAULT '',
            trap_port INTEGER DEFAULT 162,
            contact_info TEXT DEFAULT '',
            location_info TEXT DEFAULT '',
            engine_id TEXT DEFAULT '',
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """)

        # Create Syslog Entries Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS syslog_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            severity TEXT DEFAULT 'info',
            facility TEXT DEFAULT '',
            message TEXT,
            raw_log TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """)

        # Create CDP Neighbors Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cdp_neighbors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            local_interface TEXT NOT NULL,
            neighbor_name TEXT DEFAULT '',
            neighbor_ip TEXT DEFAULT '',
            neighbor_platform TEXT DEFAULT '',
            neighbor_interface TEXT DEFAULT '',
            capability TEXT DEFAULT '',
            software_version TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """)

        # Create Scan History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            scan_type TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
        );
        """)

        # Create Device Summary View
        cursor.execute("DROP VIEW IF EXISTS device_summary;")
        cursor.execute("""
        CREATE VIEW device_summary AS
        SELECT
            d.id,
            d.node_name,
            d.hostname,
            d.ip_address,
            d.device_type,
            d.status,
            d.last_scanned,
            COUNT(DISTINCT v.vlan_id) as total_vlans,
            COUNT(DISTINCT vi.id) as total_vlan_ips,
            COUNT(DISTINCT r.id) as total_radius_servers,
            COUNT(DISTINCT l.id) as total_log_servers,
            COUNT(DISTINCT s.id) as total_snmp_configs,
            COUNT(DISTINCT c.id) as total_cdp_neighbors
        FROM devices d
        LEFT JOIN vlans v ON d.id = v.device_id
        LEFT JOIN vlan_ips vi ON d.id = vi.device_id
        LEFT JOIN radius_servers r ON d.id = r.device_id
        LEFT JOIN log_servers l ON d.id = l.device_id
        LEFT JOIN snmp_servers s ON d.id = s.device_id
        LEFT JOIN cdp_neighbors c ON d.id = c.device_id
        GROUP BY d.id;
        """)

        conn.commit()
        conn.close()
        logger.info("SQLite Database Schema Initialized Successfully!")

    @classmethod
    def execute_query(cls, query, params=None, fetch=True):
        conn = None
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            if fetch:
                results = [dict(row) for row in cursor.fetchall()]
                return results
            else:
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"SQLite Query Error: {e}\nQuery: {query}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    @classmethod
    def execute_many(cls, query, params_list):
        conn = None
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"SQLite Execute Many Error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    # ========== DEVICE OPERATIONS ==========

    @classmethod
    def get_all_devices(cls):
        return cls.execute_query("SELECT * FROM device_summary ORDER BY node_name")

    @classmethod
    def get_device(cls, device_id):
        results = cls.execute_query("SELECT * FROM devices WHERE id = ?", (device_id,))
        return results[0] if results else None

    @classmethod
    def get_device_summary(cls, device_id):
        results = cls.execute_query("SELECT * FROM device_summary WHERE id = ?", (device_id,))
        return results[0] if results else None

    @classmethod
    def add_device(cls, node_name, ip_address, device_type='access_switch',
                   snmp_community=None, ssh_username=None, ssh_password=None):
        snmp_community = snmp_community or Config.SNMP_COMMUNITY
        ssh_username = ssh_username or Config.SSH_USERNAME
        ssh_password = ssh_password or Config.SSH_PASSWORD

        query = """
            INSERT INTO devices (node_name, ip_address, device_type, snmp_community, ssh_username, ssh_password)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ip_address) DO UPDATE SET 
                node_name=excluded.node_name,
                device_type=excluded.device_type,
                snmp_community=excluded.snmp_community,
                ssh_username=excluded.ssh_username,
                ssh_password=excluded.ssh_password;
        """
        return cls.execute_query(
            query,
            (node_name, ip_address, device_type, snmp_community, ssh_username, ssh_password),
            fetch=False
        )
        
    @classmethod
    def update_hostname(cls, device_id, hostname):
        """Update discovered switch hostname without changing node_name"""
        return cls.execute_query(
            "UPDATE devices SET hostname=? WHERE id=?",
            (hostname, device_id), fetch=False
        )    

    @classmethod
    def update_device_status(cls, device_id, status):
        return cls.execute_query(
            "UPDATE devices SET status=?, last_scanned=CURRENT_TIMESTAMP WHERE id=?",
            (status, device_id), fetch=False
        )

    @classmethod
    def delete_device(cls, device_id):
        return cls.execute_query("DELETE FROM devices WHERE id=?", (device_id,), fetch=False)

    # ========== VLAN OPERATIONS ==========

    @classmethod
    def get_vlans(cls, device_id):
        return cls.execute_query("SELECT * FROM vlans WHERE device_id=? ORDER BY vlan_id", (device_id,))

    @classmethod
    def save_vlans(cls, device_id, vlans_data):
        cls.execute_query("DELETE FROM vlans WHERE device_id=?", (device_id,), fetch=False)
        query = "INSERT INTO vlans (device_id, vlan_id, vlan_name, status, ports, collected_via) VALUES (?, ?, ?, ?, ?, ?)"
        params_list = [
            (device_id, v['vlan_id'], v.get('vlan_name', ''), v.get('status', 'active'), v.get('ports', ''), v.get('collected_via', 'ssh'))
            for v in vlans_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== VLAN IP OPERATIONS ==========

    @classmethod
    def get_vlan_ips(cls, device_id):
        return cls.execute_query("SELECT * FROM vlan_ips WHERE device_id=? ORDER BY vlan_id", (device_id,))

    @classmethod
    def save_vlan_ips(cls, device_id, vlan_ips_data):
        cls.execute_query("DELETE FROM vlan_ips WHERE device_id=?", (device_id,), fetch=False)
        query = "INSERT INTO vlan_ips (device_id, vlan_id, ip_address, subnet_mask, interface_name, status) VALUES (?, ?, ?, ?, ?, ?)"
        params_list = [
            (device_id, v['vlan_id'], v['ip_address'], v.get('subnet_mask', ''), v.get('interface_name', ''), v.get('status', 'up'))
            for v in vlan_ips_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== RADIUS OPERATIONS ==========

    @classmethod
    def get_radius_servers(cls, device_id):
        return cls.execute_query("SELECT * FROM radius_servers WHERE device_id=? ORDER BY priority", (device_id,))

    @classmethod
    def save_radius_servers(cls, device_id, radius_data):
        cls.execute_query("DELETE FROM radius_servers WHERE device_id=?", (device_id,), fetch=False)
        query = "INSERT INTO radius_servers (device_id, server_ip, auth_port, acct_port, secret_key, priority, timeout, retransmit) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        params_list = [
            (device_id, r['server_ip'], r.get('auth_port', 1812), r.get('acct_port', 1813), r.get('secret_key', '***'), r.get('priority', 0), r.get('timeout', 5), r.get('retransmit', 3))
            for r in radius_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== LOG SERVER OPERATIONS ==========

    @classmethod
    def get_log_servers(cls, device_id):
        return cls.execute_query("SELECT * FROM log_servers WHERE device_id=?", (device_id,))

    @classmethod
    def save_log_servers(cls, device_id, log_data):
        cls.execute_query("DELETE FROM log_servers WHERE device_id=?", (device_id,), fetch=False)
        query = "INSERT INTO log_servers (device_id, server_ip, port, protocol, severity_level, facility) VALUES (?, ?, ?, ?, ?, ?)"
        params_list = [
            (device_id, l['server_ip'], l.get('port', 514), l.get('protocol', 'udp'), l.get('severity_level', 'informational'), l.get('facility', ''))
            for l in log_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== SNMP SERVER OPERATIONS ==========

    @classmethod
    def get_snmp_servers(cls, device_id):
        return cls.execute_query("SELECT * FROM snmp_servers WHERE device_id=?", (device_id,))

    @classmethod
    def save_snmp_servers(cls, device_id, snmp_data):
        cls.execute_query("DELETE FROM snmp_servers WHERE device_id=?", (device_id,), fetch=False)
        query = "INSERT INTO snmp_servers (device_id, server_ip, community_string, snmp_version, trap_destination, trap_port, contact_info, location_info, engine_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        params_list = [
            (device_id, s.get('server_ip', ''), s.get('community_string', ''), s.get('snmp_version', '2c'), s.get('trap_destination', ''), s.get('trap_port', 162), s.get('contact_info', ''), s.get('location_info', ''), s.get('engine_id', ''))
            for s in snmp_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== SYSLOG OPERATIONS ==========

    @classmethod
    def get_syslog_entries(cls, device_id, limit=100):
        return cls.execute_query("SELECT * FROM syslog_entries WHERE device_id=? ORDER BY timestamp DESC LIMIT ?", (device_id, limit))

    @classmethod
    def save_syslog_entries(cls, device_id, syslog_data):
        cls.execute_query("DELETE FROM syslog_entries WHERE device_id=?", (device_id,), fetch=False)
        query = "INSERT INTO syslog_entries (device_id, timestamp, severity, facility, message, raw_log) VALUES (?, ?, ?, ?, ?, ?)"
        params_list = [
            (device_id, s.get('timestamp'), s.get('severity', 'info'), s.get('facility', ''), s.get('message', ''), s.get('raw_log', ''))
            for s in syslog_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== CDP NEIGHBOR OPERATIONS ==========

    @classmethod
    def get_cdp_neighbors(cls, device_id):
        return cls.execute_query("SELECT * FROM cdp_neighbors WHERE device_id=? ORDER BY local_interface", (device_id,))

    @classmethod
    def save_cdp_neighbors(cls, device_id, cdp_data):
        cls.execute_query("DELETE FROM cdp_neighbors WHERE device_id=?", (device_id,), fetch=False)
        query = "INSERT INTO cdp_neighbors (device_id, local_interface, neighbor_name, neighbor_ip, neighbor_platform, neighbor_interface, capability, software_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        params_list = [
            (device_id, c['local_interface'], c.get('neighbor_name', ''), c.get('neighbor_ip', ''), c.get('neighbor_platform', ''), c.get('neighbor_interface', ''), c.get('capability', ''), c.get('software_version', ''))
            for c in cdp_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== SCAN HISTORY ==========

    @classmethod
    def add_scan_history(cls, device_id, scan_type, status, message=''):
        return cls.execute_query("INSERT INTO scan_history (device_id, scan_type, status, message) VALUES (?, ?, ?, ?)", (device_id, scan_type, status, message), fetch=False)

    @classmethod
    def get_scan_history(cls, device_id=None, limit=50):
        if device_id:
            return cls.execute_query("SELECT sh.*, d.node_name, d.ip_address FROM scan_history sh LEFT JOIN devices d ON sh.device_id = d.id WHERE sh.device_id=? ORDER BY sh.started_at DESC LIMIT ?", (device_id, limit))
        return cls.execute_query("SELECT sh.*, d.node_name, d.ip_address FROM scan_history sh LEFT JOIN devices d ON sh.device_id = d.id ORDER BY sh.started_at DESC LIMIT ?", (limit,))

    # ========== DASHBOARD STATS ==========

    @classmethod
    def get_dashboard_stats(cls):
        stats = {}
        result = cls.execute_query("SELECT COUNT(*) as total FROM devices")
        stats['total_devices'] = result[0]['total'] if result else 0

        result = cls.execute_query("SELECT COUNT(*) as c FROM devices WHERE status='online'")
        stats['online_devices'] = result[0]['c'] if result else 0

        result = cls.execute_query("SELECT COUNT(*) as c FROM devices WHERE status='offline'")
        stats['offline_devices'] = result[0]['c'] if result else 0

        result = cls.execute_query("SELECT COUNT(*) as c FROM devices WHERE device_type='access_switch'")
        stats['access_switches'] = result[0]['c'] if result else 0

        result = cls.execute_query("SELECT COUNT(*) as c FROM devices WHERE device_type='distribution_switch'")
        stats['distribution_switches'] = result[0]['c'] if result else 0

        result = cls.execute_query("SELECT COUNT(DISTINCT vlan_id) as c FROM vlans")
        stats['total_vlans'] = result[0]['c'] if result else 0

        result = cls.execute_query("SELECT COUNT(*) as c FROM cdp_neighbors")
        stats['total_cdp_neighbors'] = result[0]['c'] if result else 0

        return stats
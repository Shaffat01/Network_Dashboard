import mysql.connector
from mysql.connector import pooling
from config import Config
import time
import logging
import os

logger = logging.getLogger(__name__)


class Database:
    _pool = None

    @classmethod
    def init_pool(cls, pool_size=10):
        """Initialize connection pool and create tables if missing"""
        retries = 10
        for attempt in range(retries):
            try:
                cls._pool = pooling.MySQLConnectionPool(
                    pool_name="network_pool",
                    pool_size=pool_size,
                    pool_reset_session=True,
                    host=Config.MYSQL_HOST,
                    port=Config.MYSQL_PORT,
                    user=Config.MYSQL_USER,
                    password=Config.MYSQL_PASSWORD,
                    database=Config.MYSQL_DB,
                    charset='utf8mb4',
                    collation='utf8mb4_unicode_ci',
                    autocommit=True
                )
                logger.info("Database connection pool created successfully")
                
                # Auto Initialize Tables
                cls.init_db_schema()
                return True
            except Exception as e:
                logger.warning(
                    f"DB connection attempt {attempt + 1}/{retries} failed: {e}"
                )
                time.sleep(5)
        logger.error("Failed to create database connection pool")
        return False

    @classmethod
    def init_db_schema(cls):
        """Execute init_db.sql to create missing tables"""
        sql_file_path = os.path.join(os.path.dirname(__file__), 'init_db.sql')
        if not os.path.exists(sql_file_path):
            logger.warning("init_db.sql file not found. Skipping schema auto-creation.")
            return

        conn = None
        cursor = None
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()

            # Execute each SQL statement
            statements = sql_script.split(';')
            for statement in statements:
                stmt = statement.strip()
                if stmt:
                    cursor.execute(stmt)
            logger.info("Database schema auto-initialized successfully!")
        except Exception as e:
            logger.error(f"Error auto-creating database schema: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @classmethod
    def get_connection(cls):
        """Get connection from pool"""
        if cls._pool is None:
            cls.init_pool()
        return cls._pool.get_connection()

    @classmethod
    def execute_query(cls, query, params=None, fetch=True):
        """Execute a query and return results"""
        conn = None
        cursor = None
        try:
            conn = cls.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            if fetch:
                results = cursor.fetchall()
                return results
            else:
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Query error: {e}\nQuery: {query}\nParams: {params}")
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @classmethod
    def execute_many(cls, query, params_list):
        """Execute a query with multiple parameter sets"""
        conn = None
        cursor = None
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Execute many error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # ========== DEVICE OPERATIONS ==========

    @classmethod
    def get_all_devices(cls):
        return cls.execute_query("SELECT * FROM device_summary ORDER BY node_name")

    @classmethod
    def get_device(cls, device_id):
        results = cls.execute_query(
            "SELECT * FROM devices WHERE id = %s", (device_id,)
        )
        return results[0] if results else None

    @classmethod
    def get_device_summary(cls, device_id):
        results = cls.execute_query(
            "SELECT * FROM device_summary WHERE id = %s", (device_id,)
        )
        return results[0] if results else None

    @classmethod
    def add_device(cls, node_name, ip_address, device_type, snmp_community='public',
                   ssh_username='admin', ssh_password='admin123'):
        query = """
            INSERT INTO devices (node_name, ip_address, device_type, 
                                snmp_community, ssh_username, ssh_password)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                node_name=VALUES(node_name),
                device_type=VALUES(device_type),
                snmp_community=VALUES(snmp_community),
                ssh_username=VALUES(ssh_username),
                ssh_password=VALUES(ssh_password)
        """
        return cls.execute_query(
            query,
            (node_name, ip_address, device_type, snmp_community,
             ssh_username, ssh_password),
            fetch=False
        )

    @classmethod
    def update_device_status(cls, device_id, status):
        return cls.execute_query(
            "UPDATE devices SET status=%s, last_scanned=NOW() WHERE id=%s",
            (status, device_id), fetch=False
        )

    @classmethod
    def delete_device(cls, device_id):
        return cls.execute_query(
            "DELETE FROM devices WHERE id=%s", (device_id,), fetch=False
        )

    # ========== VLAN OPERATIONS ==========

    @classmethod
    def get_vlans(cls, device_id):
        return cls.execute_query(
            "SELECT * FROM vlans WHERE device_id=%s ORDER BY vlan_id",
            (device_id,)
        )

    @classmethod
    def save_vlans(cls, device_id, vlans_data):
        cls.execute_query(
            "DELETE FROM vlans WHERE device_id=%s", (device_id,), fetch=False
        )
        query = """
            INSERT INTO vlans (device_id, vlan_id, vlan_name, status, ports, collected_via)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (device_id, v['vlan_id'], v.get('vlan_name', ''),
             v.get('status', 'active'), v.get('ports', ''),
             v.get('collected_via', 'ssh'))
            for v in vlans_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== VLAN IP OPERATIONS ==========

    @classmethod
    def get_vlan_ips(cls, device_id):
        return cls.execute_query(
            "SELECT * FROM vlan_ips WHERE device_id=%s ORDER BY vlan_id",
            (device_id,)
        )

    @classmethod
    def save_vlan_ips(cls, device_id, vlan_ips_data):
        cls.execute_query(
            "DELETE FROM vlan_ips WHERE device_id=%s", (device_id,), fetch=False
        )
        query = """
            INSERT INTO vlan_ips (device_id, vlan_id, ip_address, subnet_mask,
                                  interface_name, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (device_id, v['vlan_id'], v['ip_address'],
             v.get('subnet_mask', ''), v.get('interface_name', ''),
             v.get('status', 'up'))
            for v in vlan_ips_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== RADIUS OPERATIONS ==========

    @classmethod
    def get_radius_servers(cls, device_id):
        return cls.execute_query(
            "SELECT * FROM radius_servers WHERE device_id=%s ORDER BY priority",
            (device_id,)
        )

    @classmethod
    def save_radius_servers(cls, device_id, radius_data):
        cls.execute_query(
            "DELETE FROM radius_servers WHERE device_id=%s",
            (device_id,), fetch=False
        )
        query = """
            INSERT INTO radius_servers (device_id, server_ip, auth_port, acct_port,
                                        secret_key, priority, timeout, retransmit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (device_id, r['server_ip'], r.get('auth_port', 1812),
             r.get('acct_port', 1813), r.get('secret_key', '***'),
             r.get('priority', 0), r.get('timeout', 5),
             r.get('retransmit', 3))
            for r in radius_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== LOG SERVER OPERATIONS ==========

    @classmethod
    def get_log_servers(cls, device_id):
        return cls.execute_query(
            "SELECT * FROM log_servers WHERE device_id=%s",
            (device_id,)
        )

    @classmethod
    def save_log_servers(cls, device_id, log_data):
        cls.execute_query(
            "DELETE FROM log_servers WHERE device_id=%s",
            (device_id,), fetch=False
        )
        query = """
            INSERT INTO log_servers (device_id, server_ip, port, protocol,
                                     severity_level, facility)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (device_id, l['server_ip'], l.get('port', 514),
             l.get('protocol', 'udp'), l.get('severity_level', 'informational'),
             l.get('facility', ''))
            for l in log_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== SNMP SERVER OPERATIONS ==========

    @classmethod
    def get_snmp_servers(cls, device_id):
        return cls.execute_query(
            "SELECT * FROM snmp_servers WHERE device_id=%s",
            (device_id,)
        )

    @classmethod
    def save_snmp_servers(cls, device_id, snmp_data):
        cls.execute_query(
            "DELETE FROM snmp_servers WHERE device_id=%s",
            (device_id,), fetch=False
        )
        query = """
            INSERT INTO snmp_servers (device_id, server_ip, community_string,
                                      snmp_version, trap_destination, trap_port,
                                      contact_info, location_info, engine_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (device_id, s.get('server_ip', ''), s.get('community_string', ''),
             s.get('snmp_version', '2c'), s.get('trap_destination', ''),
             s.get('trap_port', 162), s.get('contact_info', ''),
             s.get('location_info', ''), s.get('engine_id', ''))
            for s in snmp_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== SYSLOG OPERATIONS ==========

    @classmethod
    def get_syslog_entries(cls, device_id, limit=100):
        return cls.execute_query(
            "SELECT * FROM syslog_entries WHERE device_id=%s "
            "ORDER BY timestamp DESC LIMIT %s",
            (device_id, limit)
        )

    @classmethod
    def save_syslog_entries(cls, device_id, syslog_data):
        cls.execute_query(
            "DELETE FROM syslog_entries WHERE device_id=%s",
            (device_id,), fetch=False
        )
        query = """
            INSERT INTO syslog_entries (device_id, timestamp, severity,
                                         facility, message, raw_log)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (device_id, s.get('timestamp'), s.get('severity', 'info'),
             s.get('facility', ''), s.get('message', ''),
             s.get('raw_log', ''))
            for s in syslog_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== CDP NEIGHBOR OPERATIONS ==========

    @classmethod
    def get_cdp_neighbors(cls, device_id):
        return cls.execute_query(
            "SELECT * FROM cdp_neighbors WHERE device_id=%s "
            "ORDER BY local_interface",
            (device_id,)
        )

    @classmethod
    def save_cdp_neighbors(cls, device_id, cdp_data):
        cls.execute_query(
            "DELETE FROM cdp_neighbors WHERE device_id=%s",
            (device_id,), fetch=False
        )
        query = """
            INSERT INTO cdp_neighbors (device_id, local_interface, neighbor_name,
                                        neighbor_ip, neighbor_platform,
                                        neighbor_interface, capability,
                                        software_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params_list = [
            (device_id, c['local_interface'], c.get('neighbor_name', ''),
             c.get('neighbor_ip', ''), c.get('neighbor_platform', ''),
             c.get('neighbor_interface', ''), c.get('capability', ''),
             c.get('software_version', ''))
            for c in cdp_data
        ]
        if params_list:
            cls.execute_many(query, params_list)

    # ========== SCAN HISTORY ==========

    @classmethod
    def add_scan_history(cls, device_id, scan_type, status, message=''):
        return cls.execute_query(
            "INSERT INTO scan_history (device_id, scan_type, status, message) "
            "VALUES (%s, %s, %s, %s)",
            (device_id, scan_type, status, message), fetch=False
        )

    @classmethod
    def get_scan_history(cls, device_id=None, limit=50):
        if device_id:
            return cls.execute_query(
                "SELECT sh.*, d.node_name, d.ip_address FROM scan_history sh "
                "LEFT JOIN devices d ON sh.device_id = d.id "
                "WHERE sh.device_id=%s ORDER BY sh.started_at DESC LIMIT %s",
                (device_id, limit)
            )
        return cls.execute_query(
            "SELECT sh.*, d.node_name, d.ip_address FROM scan_history sh "
            "LEFT JOIN devices d ON sh.device_id = d.id "
            "ORDER BY sh.started_at DESC LIMIT %s",
            (limit,)
        )

    # ========== DASHBOARD STATS ==========

    @classmethod
    def get_dashboard_stats(cls):
        stats = {}
        result = cls.execute_query("SELECT COUNT(*) as total FROM devices")
        stats['total_devices'] = result[0]['total'] if result else 0

        result = cls.execute_query(
            "SELECT COUNT(*) as c FROM devices WHERE status='online'"
        )
        stats['online_devices'] = result[0]['c'] if result else 0

        result = cls.execute_query(
            "SELECT COUNT(*) as c FROM devices WHERE status='offline'"
        )
        stats['offline_devices'] = result[0]['c'] if result else 0

        result = cls.execute_query(
            "SELECT COUNT(*) as c FROM devices WHERE device_type='access_switch'"
        )
        stats['access_switches'] = result[0]['c'] if result else 0

        result = cls.execute_query(
            "SELECT COUNT(*) as c FROM devices WHERE device_type='distribution_switch'"
        )
        stats['distribution_switches'] = result[0]['c'] if result else 0

        result = cls.execute_query(
            "SELECT COUNT(DISTINCT vlan_id) as c FROM vlans"
        )
        stats['total_vlans'] = result[0]['c'] if result else 0

        result = cls.execute_query(
            "SELECT COUNT(*) as c FROM cdp_neighbors"
        )
        stats['total_cdp_neighbors'] = result[0]['c'] if result else 0

        return stats
-- Create Database
CREATE DATABASE IF NOT EXISTS network_dashboard
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE network_dashboard;

-- Devices table (from CSV import)
CREATE TABLE IF NOT EXISTS devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    node_name VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    device_type ENUM('access_switch', 'distribution_switch') NOT NULL,
    snmp_community VARCHAR(255) DEFAULT 'public',
    ssh_username VARCHAR(255) DEFAULT 'admin',
    ssh_password VARCHAR(255) DEFAULT 'admin123',
    ssh_enabled TINYINT(1) DEFAULT 1,
    snmp_enabled TINYINT(1) DEFAULT 1,
    status ENUM('online', 'offline', 'unknown') DEFAULT 'unknown',
    last_scanned DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_ip (ip_address),
    INDEX idx_device_type (device_type),
    INDEX idx_status (status)
);

-- VLANs table
CREATE TABLE IF NOT EXISTS vlans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    vlan_id INT NOT NULL,
    vlan_name VARCHAR(255) DEFAULT '',
    status VARCHAR(50) DEFAULT 'active',
    ports TEXT,
    collected_via ENUM('snmp', 'ssh') DEFAULT 'ssh',
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    UNIQUE KEY unique_device_vlan (device_id, vlan_id),
    INDEX idx_vlan_id (vlan_id)
);

-- VLAN IP Addresses (SVI interfaces)
CREATE TABLE IF NOT EXISTS vlan_ips (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    vlan_id INT NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    subnet_mask VARCHAR(45) DEFAULT '',
    interface_name VARCHAR(100) DEFAULT '',
    status VARCHAR(50) DEFAULT 'up',
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_device_vlan_ip (device_id, vlan_id)
);

-- RADIUS Server details
CREATE TABLE IF NOT EXISTS radius_servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    server_ip VARCHAR(45) NOT NULL,
    auth_port INT DEFAULT 1812,
    acct_port INT DEFAULT 1813,
    secret_key VARCHAR(255) DEFAULT '***',
    priority INT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'unknown',
    timeout INT DEFAULT 5,
    retransmit INT DEFAULT 3,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_device_radius (device_id)
);

-- Log Server (syslog destination) details
CREATE TABLE IF NOT EXISTS log_servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    server_ip VARCHAR(45) NOT NULL,
    port INT DEFAULT 514,
    protocol VARCHAR(20) DEFAULT 'udp',
    severity_level VARCHAR(50) DEFAULT 'informational',
    facility VARCHAR(50) DEFAULT '',
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_device_log (device_id)
);

-- SNMP Server configuration details
CREATE TABLE IF NOT EXISTS snmp_servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    server_ip VARCHAR(45) DEFAULT '',
    community_string VARCHAR(255) DEFAULT '',
    snmp_version VARCHAR(10) DEFAULT '2c',
    trap_destination VARCHAR(45) DEFAULT '',
    trap_port INT DEFAULT 162,
    contact_info VARCHAR(255) DEFAULT '',
    location_info VARCHAR(255) DEFAULT '',
    engine_id VARCHAR(255) DEFAULT '',
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_device_snmp (device_id)
);

-- Syslog entries from device
CREATE TABLE IF NOT EXISTS syslog_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    severity VARCHAR(20) DEFAULT 'info',
    facility VARCHAR(50) DEFAULT '',
    message TEXT,
    raw_log TEXT,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_device_syslog (device_id),
    INDEX idx_severity (severity),
    INDEX idx_timestamp (timestamp)
);

-- CDP Neighbors
CREATE TABLE IF NOT EXISTS cdp_neighbors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    local_interface VARCHAR(100) NOT NULL,
    neighbor_name VARCHAR(255) DEFAULT '',
    neighbor_ip VARCHAR(45) DEFAULT '',
    neighbor_platform VARCHAR(255) DEFAULT '',
    neighbor_interface VARCHAR(100) DEFAULT '',
    capability VARCHAR(255) DEFAULT '',
    software_version TEXT,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_device_cdp (device_id)
);

-- Scan History
CREATE TABLE IF NOT EXISTS scan_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT,
    scan_type VARCHAR(50) NOT NULL,
    status ENUM('started', 'completed', 'failed') NOT NULL,
    message TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL,
    INDEX idx_scan_status (status)
);

-- Create default admin view
CREATE OR REPLACE VIEW device_summary AS
SELECT
    d.id,
    d.node_name,
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
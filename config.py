import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'network-dashboard-secret-key-2024')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    # MySQL Database
    MYSQL_HOST = os.getenv('MYSQL_HOST', 'mysql-db')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
    MYSQL_USER = os.getenv('MYSQL_USER', 'netadmin')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'NetAdmin@2024')
    MYSQL_DB = os.getenv('MYSQL_DB', 'network_dashboard')

    # SNMP Defaults
    SNMP_COMMUNITY = os.getenv('SNMP_COMMUNITY', 'public')
    SNMP_VERSION = os.getenv('SNMP_VERSION', '2c')
    SNMP_PORT = int(os.getenv('SNMP_PORT', 161))

    # SSH Defaults
    SSH_USERNAME = os.getenv('SSH_USERNAME', 'admin')
    SSH_PASSWORD = os.getenv('SSH_PASSWORD', 'admin123')
    SSH_PORT = int(os.getenv('SSH_PORT', 22))
    SSH_DEVICE_TYPE = os.getenv('SSH_DEVICE_TYPE', 'cisco_ios')

    # Upload folder
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', '/tmp/uploads')
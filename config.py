import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'network-dashboard-secret-key-2024')
    DEBUG = True

    # SQLite
    DB_PATH = os.path.join(BASE_DIR, 'network_dashboard.db')
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads'))

    # ========== GLOBAL DEFAULT CREDENTIALS FOR ALL SWITCHES ==========
    SSH_USERNAME = os.getenv('SSH_USERNAME', 'root')
    SSH_PASSWORD = os.getenv('SSH_PASSWORD', 'WhqAcc*&^8u7y')
    SSH_PORT = int(os.getenv('SSH_PORT', 22))

    SNMP_COMMUNITY = os.getenv('SNMP_COMMUNITY', 'WhilDc321')
    SNMP_PORT = int(os.getenv('SNMP_PORT', 161))
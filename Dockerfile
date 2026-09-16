FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py

WORKDIR /app

# Install system dependencies + sshpass & ansible requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    pkg-config \
    iputils-ping \
    net-tools \
    curl \
    sshpass \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements + Ansible
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir ansible

# Install Cisco Ansible Collection
RUN ansible-galaxy collection install cisco.ios

# Copy App code
COPY . .

# Directories
RUN mkdir -p /app/uploads /app/data /tmp/uploads /app/ansible

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--timeout", "120", "app:app"]

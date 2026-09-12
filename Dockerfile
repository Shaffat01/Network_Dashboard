# Debian Bookworm বেস ইমেজ ব্যবহার করা হচ্ছে (Stable)
FROM python:3.11-slim-bookworm

# debconf এর Interactive Warning বন্ধ করতে DEBIAN_FRONTEND সেট করা হয়েছে
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py

WORKDIR /app

# সিস্টেম ডিপেন্ডেন্সি ইনস্টল (curl সহ অন্যান্য প্রয়োজনীয় প্যাকেজ)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    iputils-ping \
    net-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python Packages install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code copy
COPY . .

# Upload Directory তৈরি
RUN mkdir -p /tmp/uploads

EXPOSE 5000

# Gunicorn দিয়ে অ্যাপ রান করা
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:app"]
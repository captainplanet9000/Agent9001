FROM python:3.11-slim

WORKDIR /app

# Install necessary system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Create Python virtual environment and install dependencies
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip wheel setuptools \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip install gunicorn==21.2.0

# Copy application files
COPY . .

# Make scripts executable
RUN chmod +x ./initialize.py ./run_ui.py ./run_cli.py ./run_tunnel.py

# Create necessary directories
RUN mkdir -p /app/memory /app/logs /app/tmp

# Default command
CMD ["python3", "-u", "railway_app.py"]
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy both minimal and full requirements
COPY requirements-minimal.txt .
COPY requirements.txt .

# Install minimal dependencies first
RUN pip install --no-cache-dir -r requirements-minimal.txt

# Then install the full requirements for Agent Zero
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Make scripts executable
RUN chmod +x ./initialize.py ./run_ui.py ./run_cli.py ./run_tunnel.py

# Create necessary directories
RUN mkdir -p /app/memory /app/logs /app/tmp

# Default command - run our railway proxy application
CMD ["python3", "-u", "railway_app.py"]
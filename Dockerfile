FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy only the minimal requirements for our railway app
COPY requirements-minimal.txt .

# Install minimal dependencies first
RUN pip install --no-cache-dir -r requirements-minimal.txt

# Download and extract agent-zero v0.8.4
RUN wget https://github.com/frdel/agent-zero/archive/refs/tags/v0.8.4.tar.gz \
    && tar -xzf v0.8.4.tar.gz \
    && rm v0.8.4.tar.gz \
    && mv agent-zero-0.8.4/* . \
    && rm -rf agent-zero-0.8.4

# Install agent-zero requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy our railway app
COPY railway_app.py .
COPY railway.toml .

# Make scripts executable
RUN chmod +x ./initialize.py ./run_ui.py ./run_cli.py ./run_tunnel.py

# Create necessary directories
RUN mkdir -p /app/memory /app/logs /app/tmp

# Default command - run our railway proxy application
CMD ["python3", "-u", "railway_app.py"]
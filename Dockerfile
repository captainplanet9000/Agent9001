# Use Python 3.11 as base - the version used for agent-zero development
FROM python:3.11-slim

WORKDIR /app

# Install essential system dependencies 
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Create directories needed by agent-zero
RUN mkdir -p /app/memory /app/logs /app/tmp

# Download and extract agent-zero v0.8.4 directly from GitHub
RUN wget https://github.com/frdel/agent-zero/archive/refs/tags/v0.8.4.tar.gz \
    && tar -xzf v0.8.4.tar.gz \
    && rm v0.8.4.tar.gz \
    && mv agent-zero-0.8.4/* . \
    && rm -rf agent-zero-0.8.4

# Install flask for the proxy and requirements from the agent-zero repo
RUN pip install --no-cache-dir flask==3.0.0 requests==2.31.0 gunicorn==21.2.0
RUN pip install --no-cache-dir -r requirements.txt

# Make scripts executable
RUN chmod +x initialize.py run_ui.py run_cli.py run_tunnel.py

# Add our Railway proxy app
COPY railway_app.py .

# Default command - run the proxy application
CMD ["python3", "-u", "railway_app.py"]
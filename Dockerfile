# Use the latest slim version of Debian
FROM debian:bookworm-slim

# Set environment variables for non-interactive installation
ENV DEBIAN_FRONTEND=noninteractive
ENV BRANCH=main
ENV PATH="/opt/venv/bin:$PATH"

# Set locale to en_US.UTF-8 and timezone to UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales tzdata supervisor git python3 python3-pip python3-venv python3-full \
    nodejs npm curl wget build-essential ca-certificates lsb-release \
    gnupg software-properties-common openssh-client sudo htop procps \
    && sed -i -e 's/# \(en_US\.UTF-8 .*\)/\1/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=en_US.UTF-8 LANGUAGE=en_US:en LC_ALL=en_US.UTF-8 \
    && ln -sf /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone \
    && dpkg-reconfigure -f noninteractive tzdata

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV TZ=UTC

# Create working directory and setup directories
WORKDIR /app

# Copy all files to the container
COPY . .

# Create and activate virtual environment
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip wheel setuptools \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip install gunicorn==21.2.0

# Make scripts executable
RUN chmod +x ./initialize.py ./run_ui.py ./run_cli.py ./run_tunnel.py

# Setup directories needed by the agent
RUN mkdir -p /app/memory /app/logs /app/tmp

# Setup environment for Railway
ENV PORT=80
ENV WEB_UI_PORT=80
ENV MEMORY_DIR=/app/memory

# Expose ports for web UI
EXPOSE 80

# Initialize the agent and run the UI
CMD ["sh", "-c", "python3 ./initialize.py && python3 ./run_ui.py --host 0.0.0.0 --port 80"]
# Use the latest slim version of Debian
FROM debian:bookworm-slim

# Set environment variable for non-interactive installation
ENV DEBIAN_FRONTEND=noninteractive
ENV BRANCH=main

# Set locale to en_US.UTF-8 and timezone to UTC
RUN apt-get update && apt-get install -y locales tzdata supervisor git python3 python3-pip python3-venv nodejs npm curl wget
RUN sed -i -e 's/# \(en_US\.UTF-8 .*\)/\1/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=en_US.UTF-8 LANGUAGE=en_US:en LC_ALL=en_US.UTF-8
RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV TZ=UTC

# Create working directory
WORKDIR /app

# Copy all files to the container
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose web UI port
EXPOSE 8080

# Command to run the application
CMD ["python3", "run_ui.py"]
FROM python:3.11-slim

WORKDIR /app

# Copy minimal requirements first
COPY requirements-minimal.txt .

# Install minimal dependencies
RUN pip install --no-cache-dir -r requirements-minimal.txt

# Copy just the application file needed for health checks
COPY railway_app.py .

# Default command
CMD ["python3", "-u", "railway_app.py"]
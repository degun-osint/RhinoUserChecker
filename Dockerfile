# Use Python 3.11 slim as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/data /app/results /app/modules

# Copy application files
COPY run.py .
COPY modules/proxy.py modules/
COPY modules/rpuc.py modules/
COPY modules/date_extractor.py modules/
COPY modules/link_analyzer.py modules/
COPY modules/profile_extractor.py modules/

# Make scripts executable
RUN chmod +x run.py
RUN chmod +x modules/proxy.py
RUN chmod +x modules/rpuc.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV WMN_JSON_URL=https://raw.githubusercontent.com/degun-osint/WhatsMyName/main/wmn-data.json
ENV PROXY_URL=http://127.0.0.1:8000/proxy

# Create a volume for persistent data
VOLUME ["/app/data", "/app/results"]

# Run application
CMD ["python", "run.py"]
# Use Python 3.11 Slim Image For Smaller Size
FROM python:3.11-slim

# Set Environment Variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set Working Directory
WORKDIR /app

# Install System Dependencies
RUN apt-get update && apt-get install -y \
    curl \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy Requirements First For Better Caching
COPY Requirements.txt .

# Install Python Dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r Requirements.txt

# Copy Application Code
COPY . .

# Create Non-Root User For Security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Create Logs Directory
RUN mkdir -p logs

# Expose Port
EXPOSE 5000

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=5)" || exit 1

# Run The Application
CMD ["python", "Bot.py"]

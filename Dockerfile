# Use Python 3.9 slim (stabile come il Dockerfile funzionante)
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install minimal system dependencies (come il Dockerfile funzionante)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application files (invece di clonare)
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and system dependencies
RUN python -m playwright install chromium && \
    python -m playwright install firefox && \
    python -m playwright install-deps

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Expose port
EXPOSE 5072

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
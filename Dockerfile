FROM python:3.11-slim

WORKDIR /app

# Install system deps (curl for bandwidth test)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY main.py .
# Use safe default config (template, not real data)
COPY config.default.json config.json
COPY templates/ templates/
COPY run.sh .
RUN chmod +x run.sh

# Data volume for persistence
VOLUME ["/app/data"]

EXPOSE 6006

ENTRYPOINT ["./run.sh"]

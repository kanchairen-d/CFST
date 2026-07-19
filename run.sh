#!/bin/bash
set -e

cd /app

# Initialize data directory if first run
if [ ! -d "/app/data" ]; then
    mkdir -p /app/data
fi

# Always ensure data/config.json has all default fields from the image
# This guarantees fresh machines get the complete configuration
cp /app/config.json /app/data/config.default.json 2>/dev/null || true

# Copy image defaults to data/config.json (fresh install) or merge
if [ ! -f "/app/data/config.json" ]; then
    cp /app/config.json /app/data/config.json 2>/dev/null || true
fi

# Ensure symlink exists so main.py can find config.json
ln -sf /app/data/config.json /app/config.json

# Initialize results database
python3 -c "
import sqlite3, os
os.makedirs('/app/data', exist_ok=True)
conn = sqlite3.connect('/app/data/results.db')
conn.execute('''CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    completed_at TEXT,
    status TEXT DEFAULT 'running',
    mode TEXT,
    total_nodes INTEGER DEFAULT 0,
    passed_nodes INTEGER DEFAULT 0,
    best_bandwidth REAL DEFAULT 0,
    best_latency REAL DEFAULT 0,
    log TEXT DEFAULT '',
    results_json TEXT DEFAULT ''
)''')
conn.commit()
conn.close()
print('Database initialized.')
"

# Start gunicorn
# workers=1 防止调度器线程被多个worker重复启动
exec gunicorn --bind 0.0.0.0:6006 --workers 1 --threads 8 --timeout 120 app:app

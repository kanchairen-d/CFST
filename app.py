#!/usr/bin/env python3
"""
CFST Web Dashboard - Cloudflare IP优选 Web 管理界面
"""

import json
import os
import sys
import subprocess
import time
import threading
import sqlite3
import queue
import re
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify, Response, send_file, stream_with_context
)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
DB_PATH = os.path.join(DATA_DIR, "results.db")
MAIN_PY = os.path.join(BASE_DIR, "main.py")
EDGETUNNEL_CONFIG_PATH = os.path.join(DATA_DIR, "edgetunnel_config.json")
SCHEDULE_CONFIG_PATH = os.path.join(DATA_DIR, "schedule.json")

DEFAULT_CONFIG_PATH = os.path.join(DATA_DIR, "config.default.json")

os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT,
        completed_at TEXT,
        status TEXT DEFAULT 'running',
        mode TEXT DEFAULT '',
        total_nodes INTEGER DEFAULT 0,
        passed_nodes INTEGER DEFAULT 0,
        best_bandwidth REAL DEFAULT 0,
        best_latency REAL DEFAULT 0,
        log TEXT DEFAULT '',
        results_json TEXT DEFAULT ''
    )""")
    conn.commit()
    conn.close()

init_db()

# Save a copy of the original config as factory defaults
if not os.path.exists(DEFAULT_CONFIG_PATH) and os.path.exists(CONFIG_PATH):
    import shutil
    shutil.copy2(CONFIG_PATH, DEFAULT_CONFIG_PATH)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config():
    defaults = load_defaults()
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {}
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    # Critical fields: ensure they are never empty
    if not cfg.get("AVAILABILITY_CHECK_API") or not isinstance(cfg["AVAILABILITY_CHECK_API"], list):
        cfg["AVAILABILITY_CHECK_API"] = ["https://api.090227.xyz/check"]
    return cfg

def load_defaults():
    """Return the full defaults dict (same as load_config's internal defaults)."""
    return {
        "_comment": "Cloudflare IP 优选工具配置文件",
        "USE_GLOBAL_MODE": True,
        "GLOBAL_TOP_N": 15,
        "PER_COUNTRY_TOP_N": 1,
        "BANDWIDTH_CANDIDATES": 150,
        "TCP_PROBES": 1,
        "MIN_SUCCESS_RATE": 1.0,
        "TCP_LATENCY_WEIGHT": 0.0,
        "TIMEOUT": 2.0,
        "SOCKET_DEFAULT_TIMEOUT": 3,
        "PROGRESS_PRINT_INTERVAL": 1,
        "FILTER_COUNTRIES_ENABLED": False,
        "ALLOWED_COUNTRIES": ["US"],
        "PRE_FILTER_BLOCKED_ENABLED": True,
        "PRE_FILTER_BLOCKED_COUNTRIES": ["CN"],
        "PRE_FILTER_PORT_ENABLED": True,
        "PRE_FILTER_PORTS": [443],
        "ENABLE_WXPUSHER": False,
        "ENABLE_PUSHPLUS": False,
        "PUSHPLUS_TOKEN": "",
        "WXPUSHER_APP_TOKEN": "",
        "WXPUSHER_UIDS": [],
        "WXPUSHER_API_URL": "https://wxpusher.zjiecode.com/api/send/message",
        "NOTIFY_TIMEOUT": 3,
        "NOTIFY_CONNECT_TIMEOUT": 3,
        "CF_ENABLED": True,
        "CF_API_TOKEN": "",
        "CF_ZONE_ID": "",
        "CF_DNS_RECORD_NAME": "",
        "CF_TTL": 60,
        "CF_PROXIED": False,
        "CF_DNS_CONNECT_TIMEOUT": 3,
        "CF_DNS_READ_TIMEOUT": 3,
        "DNS_RECORD_TYPE": "TXT",
        "ADDITIONAL_SOURCES": [
            {"url": "https://zip.cm.edu.kg/all.txt", "enabled": True},
            {"url": "https://countrymerge.pages.dev/all.txt", "enabled": True}
        ],
        "FETCH_MAX_RETRIES": 3,
        "FETCH_RETRY_DELAY": 3,
        "FETCH_TIMEOUT": 3,
        "FETCH_CONNECT_TIMEOUT": 3,
        "IP_CALIBRATION_ENABLED": False,
        "IP_CALIBRATION_TOKENS": [],
        "IP_CALIBRATION_MIN_INTERVAL": 0.1,
        "IP_CALIBRATION_CONCURRENCY": 300,
        "OUTPUT_FILE": "ip.txt",
        "ENABLE_LOGGING": False,
        "LOG_FILE": "cfnb.log",
        "FORCE_DIRECT": True,
        "TEST_AVAILABILITY": True,
        "AVAILABILITY_CHECK_API": ["https://api.090227.xyz/check"],
        "AVAILABILITY_TIMEOUT": 3,
        "AVAILABILITY_CONNECT_TIMEOUT": 3,
        "AVAILABILITY_RETRY_MAX": 2,
        "AVAILABILITY_RETRY_DELAY": 3,
        "AVAILABILITY_INNER_RETRY_ENABLED": True,
        "AVAILABILITY_INNER_RETRY_MAX": 2,
        "AVAILABILITY_INNER_RETRY_DELAY": 3,
        "HTTP_TEST_ENABLED": True,
        "HTTP_TEST_TIMEOUT": 3,
        "HTTP_TEST_CONNECT_TIMEOUT": 3,
        "HTTP_TEST_MAX_ROUNDS": 2,
        "HTTP_TEST_ROUND_DELAY": 3,
        "HTTP_TEST_INNER_RETRY_ENABLED": True,
        "HTTP_TEST_MAX_RETRIES": 2,
        "HTTP_TEST_RETRY_DELAY": 3,
        "HTTP_TEST_METHOD": "HEAD",
        "HTTP_LATENCY_WEIGHT": 3.0,
        "JITTER_WEIGHT": 3.0,
        "HTTP_JITTER_SAMPLES": 3,
        "FILTER_IPV6_AVAILABILITY": True,
        "FILTER_BLOCKED_COUNTRIES_ENABLED": True,
        "BLOCKED_COUNTRIES": [
            "BD", "BI", "BY", "CD", "CF", "CN", "CU", "DE", "ET", "HK",
            "IR", "KP", "LY", "MO", "NG", "NL", "PK", "RU", "SD", "SO",
            "SY", "TH", "TW", "UA", "VE", "VN", "YE", "ZW"
        ],
        "DNS_IP_RISK_FILTER_ENABLED": False,
        "DNS_IP_RISK_MAX_LEVEL": "高风险",
        "DNS_UPDATE_TARGET_COUNT": 15,
        "BANDWIDTH_SIZE_MB": 1.0,
        "BANDWIDTH_TIMEOUT": 3,
        "BANDWIDTH_RETRY_MAX": 2,
        "BANDWIDTH_RETRY_DELAY": 3,
        "BANDWIDTH_URL_TEMPLATE": "https://speed.cloudflare.com/__down?bytes={bytes}",
        "BANDWIDTH_PROCESS_BUFFER": 2,
        "BANDWIDTH_CONNECT_TIMEOUT": 3,
        "SPEED_WEIGHT": 3.0,
        "MAX_WORKERS": 300,
        "AVAILABILITY_WORKERS": 32,
        "FALLBACK_WORKERS": 32,
        "HTTP_TEST_WORKERS": 32,
        "BANDWIDTH_WORKERS": 3,
        "DNS_UPDATE_MAX_RETRIES": 3,
        "DNS_UPDATE_RETRY_DELAY": 3,
        "GITHUB_SYNC_MAX_RETRIES": 3,
        "GITHUB_SYNC_RETRY_DELAY": 3,
        "GITHUB_SYNC_ENABLED": False,
        "GITHUB_TOKEN": "",
        "GITHUB_USERNAME": "",
        "GITHUB_REPO": "",
        "GITHUB_BRANCH": "main",
        "GIT_SYNC_PROCESS_TIMEOUT": 180,
        "AD_HEADER_ENABLED": False,
        "AD_HEADER_LINES": [],
        "AD_FOOTER_ENABLED": False,
        "AD_FOOTER_LINES": [],
        "AD_PERLINE_ENABLED": False,
        "AD_PERLINE_TEXT": "",
        "IP_TXT_SHOW_BANDWIDTH": False,
        "IP_TXT_SHOW_HTTP_LATENCY": False,
        "IP_TXT_SHOW_HTTP_JITTER": False,
        "IP_TXT_SHOW_LATENCY": False,
        "IP_CALIBRATION_TOKEN_FILE": "valid_tokens.txt",
        "IP_CALIBRATION_CACHE_FILE": "ipinfo_cache.txt"
    }


def save_config(cfg):
    # Merge with existing config to avoid losing other groups' settings
    existing = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    existing.update(cfg)
    # Fill in any missing defaults so saved file is always complete
    defaults = load_defaults()
    for k, v in defaults.items():
        existing.setdefault(k, v)
    # Critical fields: ensure they are never empty
    if not existing.get('AVAILABILITY_CHECK_API') or not isinstance(existing['AVAILABILITY_CHECK_API'], list):
        existing['AVAILABILITY_CHECK_API'] = ['https://api.090227.xyz/check']
    # Remove internal comments before saving
    clean = {k: v for k, v in existing.items() if not k.startswith("_")}
    # Keep _comment fields for readability
    for k, v in existing.items():
        if k.startswith("_comment"):
            clean[k] = v
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=4, ensure_ascii=False)

def ensure_config_symlink():
    """Ensure config.json in BASE_DIR is a symlink to data/config.json"""
    target = os.path.join(BASE_DIR, "config.json")
    try:
        if not os.path.islink(target):
            if os.path.isfile(target):
                # Back up real file and replace with symlink
                bak = target + ".bak"
                if not os.path.exists(bak):
                    os.rename(target, bak)
                else:
                    os.remove(target)
            os.symlink(CONFIG_PATH, target)
    except (OSError, PermissionError):
        pass

# ---------------------------------------------------------------------------
# Speed test runner (background thread with SSE)
# ---------------------------------------------------------------------------

class SpeedTestRunner:
    def __init__(self):
        self._process = None
        self._log_queue = queue.Queue()
        self._running = False
        self._run_id = None
        self._thread = None
        self._lock = threading.Lock()

    @property
    def is_running(self):
        return self._running

    def start(self):
        with self._lock:
            if self._running:
                return False
            self._running = True

        ensure_config_symlink()
        self._log_queue = queue.Queue()

        # Create a run record
        conn = get_db()
        now = datetime.now().isoformat()
        cur = conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
            (now,)
        )
        self._run_id = cur.lastrowid
        conn.commit()
        conn.close()

        self._log_queue.put(f"[系统] 测速开始: {now}\n")

        self._thread = threading.Thread(target=self._run_process, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._log_queue.put("[系统] 测速已手动停止\n")
        # Update run status
        if self._run_id:
            conn = get_db()
            conn.execute("UPDATE runs SET status='stopped' WHERE id=?", (self._run_id,))
            conn.commit()
            conn.close()

    def _run_process(self):
        log_lines = []
        try:
            self._process = subprocess.Popen(
                [sys.executable, MAIN_PY],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=BASE_DIR,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )

            for line in iter(self._process.stdout.readline, ""):
                if not self._running:
                    self._process.kill()
                    break
                line = line.rstrip("\n")
                log_lines.append(line)
                self._log_queue.put(line + "\n")

            self._process.wait()
            finished_ok = self._process.returncode == 0

            conn = get_db()
            # Try to parse results from log
            results_json = self._parse_results_from_log(log_lines)
            total_nodes = results_json.get("total_nodes", 0)
            passed_nodes = results_json.get("passed_nodes", 0)
            best_bandwidth = results_json.get("best_bandwidth", 0)
            best_latency = results_json.get("best_latency", 0)
            mode = results_json.get("mode", "")
            completed_at = datetime.now().isoformat()

            conn.execute("""UPDATE runs SET
                status=?, completed_at=?, total_nodes=?, passed_nodes=?,
                best_bandwidth=?, best_latency=?, mode=?, log=?, results_json=?
                WHERE id=?""", (
                "completed" if finished_ok else "failed",
                completed_at,
                total_nodes,
                passed_nodes,
                best_bandwidth,
                best_latency,
                mode,
                "\n".join(log_lines[-500:]),
                json.dumps(results_json, ensure_ascii=False),
                self._run_id
            ))
            conn.commit()
            conn.close()

            self._log_queue.put(f"[系统] 测速{'完成' if finished_ok else '失败'}\n")

        except Exception as e:
            self._log_queue.put(f"[错误] {str(e)}\n")
            if self._run_id:
                conn = get_db()
                conn.execute("UPDATE runs SET status='failed', log=? WHERE id=?",
                             ("\n".join(log_lines[-200:]), self._run_id))
                conn.commit()
                conn.close()
        finally:
            self._running = False

    def _parse_results_from_log(self, log_lines):
        result = {
            "total_nodes": 0,
            "passed_nodes": 0,
            "best_bandwidth": 0,
            "best_latency": 999,
            "mode": "",
            "nodes": []
        }
        text = "\n".join(log_lines)

        # Mode
        m = re.search(r'当前模式：(.+?)，', text)
        if m:
            result["mode"] = m.group(1)

        # Total nodes
        m = re.search(r'合并后总计 (\d+) 个节点', text)
        if m:
            result["total_nodes"] = int(m.group(1))

        # Passed nodes (from final output)
        m = re.search(r'结果已保存到 .+（共 (\d+) 个节点）', text)
        if m:
            result["passed_nodes"] = int(m.group(1))

        # Final node details
        final_section = re.findall(
            r'\d+\.\s+([\d.]+:\d+#\S+)\s+速度\s+([\d.]+)\s*Mbps\s+延迟\s+([\d.]+)\s*ms\s+抖动\s+([\d.]+)\s*ms',
            text
        )
        if not final_section:
            final_section = re.findall(
                r'\d+\.\s+(\S+)\s+速度\s+([\d.]+)\s*Mbps',
                text
            )

        for entry in final_section:
            node_info = {
                "node": entry[0],
                "bandwidth": float(entry[1]),
            }
            if len(entry) >= 3:
                node_info["latency"] = float(entry[2])
            if len(entry) >= 4:
                node_info["jitter"] = float(entry[3])
            result["nodes"].append(node_info)
            bw = float(entry[1])
            if bw > result["best_bandwidth"]:
                result["best_bandwidth"] = bw
            if len(entry) >= 3:
                lat = float(entry[2])
                if lat < result["best_latency"]:
                    result["best_latency"] = lat

        return result

    def get_log_queue(self):
        return self._log_queue

    def get_run_id(self):
        return self._run_id


runner = SpeedTestRunner()

# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/speedtest")
def speedtest():
    return render_template("speedtest.html")

@app.route("/history")
def history():
    return render_template("history.html")

@app.route("/settings")
def settings():
    return render_template("settings.html")

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    return jsonify({
        "running": runner.is_running,
        "run_id": runner.get_run_id()
    })

@app.route("/api/stats")
def api_stats():
    conn = get_db()
    row = conn.execute("""
        SELECT
            COUNT(*) as total_runs,
            COALESCE(SUM(passed_nodes), 0) as total_passed,
            COALESCE(MAX(best_bandwidth), 0) as max_bw,
            COALESCE(MIN(CASE WHEN best_latency > 0 THEN best_latency ELSE NULL END), 0) as min_latency
        FROM runs WHERE status = 'completed'
    """).fetchone()
    conn.close()

    latest_run = None
    conn2 = get_db()
    row2 = conn2.execute(
        "SELECT * FROM runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn2.close()
    if row2:
        latest_run = dict(row2)

    return jsonify({
        "total_runs": row["total_runs"],
        "total_passed": row["total_passed"],
        "max_bandwidth": round(row["max_bw"], 2),
        "min_latency": round(row["min_latency"], 2),
        "latest_run": latest_run,
        "running": runner.is_running
    })

@app.route("/api/runs")
def api_runs():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    conn = get_db()
    rows = conn.execute(
        """SELECT *, ROW_NUMBER() OVER (ORDER BY id) as display_num
           FROM runs ORDER BY id DESC LIMIT ? OFFSET ?""",
        (per_page, offset)
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) as c FROM runs").fetchone()["c"]
    conn.close()
    return jsonify({
        "runs": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page)
    })

@app.route("/api/runs/<int:run_id>")
def api_run_detail(run_id):
    conn = get_db()
    row = conn.execute(
        """SELECT *, (SELECT COUNT(*) FROM runs WHERE id <= ?) as display_num
           FROM runs WHERE id=?""", (run_id, run_id)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(row))

@app.route("/api/runs/<int:run_id>", methods=["DELETE"])
def api_delete_run(run_id):
    conn = get_db()
    conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/runs/clear", methods=["POST"])
def api_clear_runs():
    conn = get_db()
    conn.execute("DELETE FROM runs")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/runs/export")
def api_export_runs():
    fmt = request.args.get("format", "json")
    ids_param = request.args.get("ids", "")

    conn = get_db()
    if ids_param:
        ids = [int(x.strip()) for x in ids_param.split(",") if x.strip().isdigit()]
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(f"SELECT * FROM runs WHERE id IN ({placeholders}) ORDER BY id DESC", ids).fetchall()
    else:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    conn.close()

    # Collect nodes from selected runs
    all_nodes = []
    for r in rows:
        if r["status"] != "completed":
            continue
        try:
            results = json.loads(r["results_json"]) if r["results_json"] else {}
        except (json.JSONDecodeError, TypeError):
            results = {}
        nodes = results.get("nodes", [])
        all_nodes.extend(nodes)

    if fmt == "csv":
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["IP", "Port", "Label", "Bandwidth(Mbps)", "Latency(ms)", "Jitter(ms)"])
        seen = set()
        for n in all_nodes:
            node_str = n.get("node", "")
            ip_port = node_str.split("#")[0] if "#" in node_str else node_str
            label = node_str.split("#", 1)[1] if "#" in node_str else ""
            ip = ip_port.split(":")[0] if ":" in ip_port else ip_port
            port = ip_port.split(":")[1] if ":" in ip_port else ""
            key = ip_port
            if key in seen:
                continue
            seen.add(key)
            writer.writerow([
                ip, port, label,
                f'{n.get("bandwidth", 0):.2f}',
                f'{n.get("latency", 0):.2f}',
                f'{n.get("jitter", 0):.2f}'
            ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=cfst_export.csv"}
        )

    # JSON: deduplicate by node string
    seen = set()
    out_nodes = []
    for n in all_nodes:
        key = n.get("node", "")
        if key in seen:
            continue
        seen.add(key)
        out_nodes.append(n)
    return jsonify(out_nodes)

# ---------------------------------------------------------------------------
# Config API
# ---------------------------------------------------------------------------

@app.route("/api/config")
def api_get_config():
    cfg = load_config()
    return jsonify(cfg)

@app.route("/api/config", methods=["POST"])
def api_save_config():
    data = request.get_json()
    if data is None:
        return jsonify({"error": "no data"}), 400

    save_config(data)
    return jsonify({"ok": True})

@app.route("/api/config/restore", methods=["POST"])
def api_restore_defaults():
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        return jsonify({"error": "没有默认配置备份"}), 400
    import shutil
    shutil.copy2(DEFAULT_CONFIG_PATH, CONFIG_PATH)
    ensure_config_symlink()
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# Speed Test API
# ---------------------------------------------------------------------------

@app.route("/api/speedtest/start", methods=["POST"])
def api_speedtest_start():
    if runner.is_running:
        return jsonify({"error": "already running"}), 400
    ok = runner.start()
    if not ok:
        return jsonify({"error": "failed to start"}), 500
    return jsonify({"ok": True, "run_id": runner.get_run_id()})

@app.route("/api/speedtest/stop", methods=["POST"])
def api_speedtest_stop():
    runner.stop()
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# SSE Log Stream
# ---------------------------------------------------------------------------

@app.route("/stream")
def stream():
    def generate():
        q = runner.get_log_queue()
        run_id = runner.get_run_id()
        # Send initial event
        yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"
        while runner.is_running or not q.empty():
            try:
                line = q.get(timeout=2)
                yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip()})}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        # Drain remaining
        while not q.empty():
            try:
                line = q.get_nowait()
                yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip()})}\n\n"
            except queue.Empty:
                break
        yield f"data: {json.dumps({'type': 'done', 'run_id': run_id})}\n\n"
        # Auto sync to Edgetunnel after test completes
        try:
            print("[AutoSync] Starting sync after test complete...")
            _auto_sync_edgetunnel()
            print("[AutoSync] Sync completed")
        except Exception as e:
            print(f"[AutoSync] Error: {e}")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.route("/api/speedtest/logs")
def api_speedtest_logs():
    """Return full log for the current/last run"""
    run_id = request.args.get("run_id", type=int)
    if run_id:
        conn = get_db()
        row = conn.execute("SELECT log FROM runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        if row:
            return jsonify({"log": row["log"]})
    return jsonify({"log": ""})

# ---------------------------------------------------------------------------
# Edgetunnel Config API
# ---------------------------------------------------------------------------

def load_edgetunnel_config():
    defaults = {
        "EDGETUNNEL_ENABLED": False,
        "AUTO_SYNC": False,
        "EDGETUNNEL_URL": "",
        "EDGETUNNEL_API_KEY": "",
        "EDGETUNNEL_SYNC_INTERVAL_MIN": 60,
        "SYNC_TAG": "",
        "EDGETUNNEL_ENDPOINTS": [],
        "EDGETUNNEL_KV_MODE": False,
        "CF_ACCOUNT_ID": "",
        "KV_NAMESPACE_ID": "",
        "CF_API_TOKEN": "",
        "KV_TAG": "",
    }
    if os.path.exists(EDGETUNNEL_CONFIG_PATH):
        with open(EDGETUNNEL_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    else:
        cfg = {}

    # Migrate old single-format to new array format
    if not cfg.get("EDGETUNNEL_ENDPOINTS") and cfg.get("EDGETUNNEL_URL"):
        cfg["EDGETUNNEL_ENDPOINTS"] = [{
            "url": cfg.get("EDGETUNNEL_URL", "").rstrip("/"),
            "password": cfg.get("EDGETUNNEL_API_KEY", ""),
            "enabled": cfg.get("EDGETUNNEL_ENABLED", False),
            "tag": cfg.get("SYNC_TAG", ""),
        }]

    for k, v in defaults.items():
        cfg.setdefault(k, v)
    return cfg

def save_edgetunnel_config(cfg):
    with open(EDGETUNNEL_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

@app.route("/api/edgetunnel/config")
def api_get_edgetunnel():
    return jsonify(load_edgetunnel_config())

@app.route("/api/edgetunnel/config", methods=["POST"])
def api_save_edgetunnel():
    data = request.get_json()
    if data is None:
        return jsonify({"error": "no data"}), 400
    save_edgetunnel_config(data)
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# Schedule config
# ---------------------------------------------------------------------------

def load_schedule():
    defaults = {
        "enabled": False,
        "type": "daily",
        "time": "08:00",
        "days": [],
        "interval_hours": 4,
        "last_run": None,
        "collect_sync_after_test": False,
        "auto_sync_after_test": False
    }
    if os.path.exists(SCHEDULE_CONFIG_PATH):
        with open(SCHEDULE_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    else:
        cfg = {}
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    return cfg

def save_schedule(cfg):
    with open(SCHEDULE_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

@app.route("/api/schedule")
def api_get_schedule():
    return jsonify(load_schedule())

@app.route("/api/schedule", methods=["POST"])
def api_save_schedule():
    data = request.get_json()
    if data is None:
        return jsonify({"error": "no data"}), 400
    save_schedule(data)
    return jsonify({"ok": True})

@app.route("/api/schedule/status")
def api_schedule_status():
    from datetime import datetime
    cfg = load_schedule()
    return jsonify({
        "enabled": cfg.get("enabled", False),
        "description": describe_schedule(cfg),
        "last_run": cfg.get("last_run"),
    })

def describe_schedule(cfg):
    if not cfg.get("enabled"):
        return "未启用"
    t = cfg.get("type", "daily")
    tm = cfg.get("time", "08:00")
    days = cfg.get("days", [])
    weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
    if t == "daily":
        return f"每天 {tm}"
    elif t == "weekly" and days:
        ds = ",".join(weekdays[d] for d in sorted(days) if d < 7)
        return f"每周 {ds} {tm}"
    elif t == "interval":
        ih = cfg.get("interval_hours", 4)
        return f"每 {ih} 小时"
    return "未知"

# ===== Schedule runner (background thread) =====
import time as _time
from datetime import datetime as _dt, timedelta

_scheduler_running = False

def start_scheduler():
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()

def _scheduler_loop():
    while _scheduler_running:
        try:
            cfg = load_schedule()
            if cfg.get("enabled"):
                _check_and_run(cfg)
        except Exception:
            pass
        _time.sleep(60)

def _check_and_run(cfg):
    now = _dt.now()
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    schedule_type = cfg.get("type", "daily")
    schedule_time = cfg.get("time", "08:00")
    last_run = cfg.get("last_run")

    should_run = False

    if schedule_type == "daily":
        # Run once per day at the specified time
        if time_str == schedule_time and (not last_run or not last_run.startswith(today_str)):
            should_run = True

    elif schedule_type == "weekly":
        days = cfg.get("days", [])
        if now.weekday() in days and time_str == schedule_time:
            # Check if already ran today
            if not last_run or not last_run.startswith(today_str):
                should_run = True

    elif schedule_type == "interval":
        interval_h = cfg.get("interval_hours", 4)
        if last_run:
            try:
                last = _dt.fromisoformat(last_run)
                if (_dt.now() - last) >= timedelta(hours=interval_h):
                    should_run = True
            except:
                should_run = True
        else:
            should_run = True

    if should_run:
        _trigger_auto_test(cfg)

def _trigger_auto_test(cfg):
    if runner.is_running:
        return  # Already running, skip
    ok = runner.start()
    if ok:
        # Mark last_run
        cfg["last_run"] = _dt.now().isoformat()
        save_schedule(cfg)

        # Wait for test to complete (poll every 5s, max 30min)
        for _ in range(360):
            _time.sleep(5)
            if not runner.is_running:
                break

        # 测速后操作（受测速配置开关控制）
        s_cfg = load_schedule()
        if s_cfg.get("auto_sync_after_test"):
            _auto_sync_edgetunnel()
            _auto_sync_github()

        # 合并历史检测并同步
        if s_cfg.get("collect_sync_after_test"):
            import threading as _t
            _t.Thread(target=_run_collect_sync, daemon=True).start()

def _auto_sync_edgetunnel():
    """Sync latest results to all enabled Edgetunnel endpoints"""
    import requests
    e_cfg = load_edgetunnel_config()
    if not e_cfg.get("EDGETUNNEL_ENABLED"):
        return
    endpoints = e_cfg.get("EDGETUNNEL_ENDPOINTS", [])
    # Separate KV endpoints from HTTP endpoints
    kv_eps = [e for e in endpoints if e.get("enabled") and e.get("type") == "kv" and e.get("account_id") and e.get("namespace_id") and e.get("api_token")]
    http_eps = [e for e in endpoints if e.get("enabled") and e.get("type") != "kv"]
    # Also check old top-level KV fields (backward compat)
    has_kv_old = e_cfg.get("EDGETUNNEL_KV_MODE") and e_cfg.get("CF_ACCOUNT_ID") and e_cfg.get("KV_NAMESPACE_ID") and e_cfg.get("CF_API_TOKEN")
    if not endpoints and not has_kv_old and not kv_eps:
        return
    # Get IPs from latest run
    conn = get_db()
    row = conn.execute(
        "SELECT results_json FROM runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return
    results = json.loads(row["results_json"])
    nodes = results.get("nodes", [])
    ip_lines = []
    for n in nodes:
        node_str = n.get("node") or n.get("ip") or ""
        ip_part = node_str.split(":")[0].split("#")[0].strip()
        if ip_part:
            ip_lines.append(node_str.split("#")[0].strip())
    if not ip_lines:
        return
    # Build base IP text
    tagged = list(ip_lines)
    kv_tag = e_cfg.get("KV_TAG", "")
    sync_tag = e_cfg.get("SYNC_TAG", "")
    tag = kv_tag or sync_tag
    if tag:
        tagged = [f"{l}#{tag}" for l in tagged]
    body_text = "\n".join(tagged)
    auto_results = []
    # ===== KV 直写（遍历所有 KV 端点） =====
    for kv_ep in kv_eps:
        try:
            kv_tag = kv_ep.get("tag", "") or e_cfg.get("KV_TAG", "") or e_cfg.get("SYNC_TAG", "")
            kv_lines = [f"{l}#{kv_tag}" for l in ip_lines] if kv_tag else list(ip_lines)
            kv_body = "\n".join(kv_lines)
            kv_url = f"https://api.cloudflare.com/client/v4/accounts/{kv_ep['account_id'].strip()}/storage/kv/namespaces/{kv_ep['namespace_id'].strip()}/values/ADD.txt"
            kv_headers = {"Authorization": f"Bearer {kv_ep['api_token'].strip()}", "Content-Type": "text/plain; charset=utf-8"}
            kv_r = requests.put(kv_url, data=kv_body.encode('utf-8'), headers=kv_headers, timeout=15)
            auto_results.append(f"KV直写({kv_ep['namespace_id'][:8]}...): {'✅' if kv_r.ok else '❌'}")
        except:
            auto_results.append("KV直写: ❌")
    # 旧版兼容：顶层 KV 字段
    if has_kv_old:
        try:
            kv_url = f"https://api.cloudflare.com/client/v4/accounts/{e_cfg['CF_ACCOUNT_ID'].strip()}/storage/kv/namespaces/{e_cfg['KV_NAMESPACE_ID'].strip()}/values/ADD.txt"
            kv_headers = {"Authorization": f"Bearer {e_cfg['CF_API_TOKEN'].strip()}", "Content-Type": "text/plain; charset=utf-8"}
            kv_r = requests.put(kv_url, data=body_text.encode('utf-8'), headers=kv_headers, timeout=15)
            auto_results.append(f"KV直写(旧): {'✅' if kv_r.ok else '❌'}")
        except:
            auto_results.append("KV直写(旧): ❌")
    # ===== HTTP POST 模式 =====
    for ep in http_eps:
        url = ep.get("url", "").rstrip("/")
        pw = ep.get("password", "")
        if not url or not pw:
            continue
        ep_text = body_text
        ep_tag = ep.get("tag", "")
        if ep_tag:
            ep_lines = [f"{l}#{ep_tag}" for l in ip_lines]
            ep_text = "\n".join(ep_lines)
        try:
            sess = requests.Session()
            sess.post(f"{url}/login", data={"password": pw},
                      headers={"User-Agent": "CFST-AutoSync/1.0",
                               "Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            r = sess.post(f"{url}/admin/ADD.txt", data=ep_text.encode('utf-8'),
                      headers={"Content-Type": "text/plain; charset=utf-8",
                               "User-Agent": "CFST-AutoSync/1.0"}, timeout=15)
            auto_results.append(f"{url}: {'✅' if r.ok else '❌'}")
        except:
            auto_results.append(f"{url}: ❌")
    # 自动同步通知
    try:
        cfg = load_config()
        ewxp = cfg.get("ENABLE_WXPUSHER", False)
        epp = cfg.get("ENABLE_PUSHPLUS", False)
        if ewxp or epp:
            content = "\n".join(auto_results)
            title = "Edgetunnel 同步"
            if ewxp and cfg.get("WXPUSHER_APP_TOKEN"):
                try:
                    p = {"appToken": cfg["WXPUSHER_APP_TOKEN"], "content": content, "summary": title, "uids": cfg.get("WXPUSHER_UIDS", [])}
                    requests.post(cfg.get("WXPUSHER_API_URL", "https://wxpusher.zjiecode.com/api/send/message"), json=p, timeout=5)
                except: pass
            if epp and cfg.get("PUSHPLUS_TOKEN"):
                try:
                    requests.post("https://www.pushplus.plus/send", json={"token": cfg["PUSHPLUS_TOKEN"], "title": title, "content": content, "template": "text"}, timeout=5)
                except: pass
    except: pass


def _auto_sync_github():
    """Sync latest completed run's IPs to GitHub"""
    cfg = load_config()
    if not cfg.get("GITHUB_SYNC_ENABLED"):
        return
    token = cfg.get("GITHUB_TOKEN", "").strip()
    username = cfg.get("GITHUB_USERNAME", "").strip()
    repo = cfg.get("GITHUB_REPO", "").strip()
    branch = cfg.get("GITHUB_BRANCH", "main").strip()
    if not token or not username or not repo:
        return
    conn = get_db()
    row = conn.execute(
        "SELECT results_json FROM runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return
    try:
        results = json.loads(row["results_json"])
        nodes = results.get("nodes", [])
        ip_lines = []
        for n in nodes:
            node_str = n.get("node") or n.get("ip") or ""
            ip_clean = node_str.split("#")[0].strip()
            if ip_clean:
                ip_lines.append(ip_clean)
        if not ip_lines:
            return
        output_file = os.path.join(BASE_DIR, cfg.get("OUTPUT_FILE", "ip.txt"))
        with open(output_file, "w") as f:
            f.write("\n".join(ip_lines) + "\n")
        repo_url = f"https://{username}:{token}@github.com/{username}/{repo}.git"
        subprocess.run(["git", "-C", BASE_DIR, "add", output_file], capture_output=True, timeout=180, check=True)
        subprocess.run(["git", "-C", BASE_DIR, "commit", "-m", f"Auto-sync {len(ip_lines)} IPs [{datetime.now().strftime('%Y-%m-%d %H:%M')}]", "--allow-empty"], capture_output=True, timeout=180, check=True)
        subprocess.run(["git", "-C", BASE_DIR, "remote", "set-url", "origin", repo_url], capture_output=True, timeout=30, check=True)
        subprocess.run(["git", "-C", BASE_DIR, "push", "origin", branch], capture_output=True, timeout=180, check=True)
    except:
        pass


@app.route("/api/edgetunnel/sync", methods=["POST"])
def api_edgetunnel_sync():
    """Trigger Edgetunnel sync with latest results"""
    cfg = load_edgetunnel_config()

    # Accept config data in POST body (for "sync without save first" flow)
    body = request.get_json() or {}
    if body.get("EDGETUNNEL_ENABLED") is not None:
        cfg.update(body)
        save_edgetunnel_config(cfg)

    if not cfg.get("EDGETUNNEL_ENABLED"):
        return jsonify({"error": "Edgetunnel not enabled"}), 400

    # Collect enabled endpoints
    endpoints = cfg.get("EDGETUNNEL_ENDPOINTS", [])
    if not endpoints:
        # fallback: old single-format
        u = cfg.get("EDGETUNNEL_URL", "").rstrip("/")
        p = cfg.get("EDGETUNNEL_API_KEY", "")
        if u and p:
            endpoints = [{"url": u, "password": p, "enabled": True}]

    enabled_eps = [e for e in endpoints if e.get("enabled")]
    kv_eps = [e for e in enabled_eps if e.get("type") == "kv" and e.get("account_id") and e.get("namespace_id") and e.get("api_token")]
    http_eps = [e for e in enabled_eps if e.get("type") != "kv"]
    # Also check old top-level KV fields (backward compat)
    has_kv_old = cfg.get("EDGETUNNEL_KV_MODE") and cfg.get("CF_ACCOUNT_ID") and cfg.get("KV_NAMESPACE_ID") and cfg.get("CF_API_TOKEN")

    if not enabled_eps and not has_kv_old and not kv_eps:
        return jsonify({"error": "没有启用的同步方式，请添加 Edgetunnel 端点或启用 KV 直写"}), 400

    # Get latest completed run's IP results
    conn = get_db()
    row = conn.execute(
        "SELECT results_json FROM runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        # Fallback: read ip.txt
        ip_txt_path = os.path.join(BASE_DIR, cfg.get("OUTPUT_FILE", "ip.txt"))
        if not os.path.exists(ip_txt_path):
            return jsonify({"error": "没有已完成的结果，请先跑一次测速"}), 400
        with open(ip_txt_path, "r") as f:
            ip_lines = [l.strip().split("#")[0].strip() for l in f if l.strip()]
    else:
        results = json.loads(row["results_json"])
        nodes = results.get("nodes", [])
        ip_lines = []
        for n in nodes:
            node_str = n.get("node") or n.get("ip") or ""
            # format: ip:port#region or ip:port
            ip_part = node_str.split(":")[0].split("#")[0].strip()
            if ip_part:
                # Edgetunnel expects ip:port without #region suffix
                ip_clean = node_str.split("#")[0].strip()
                ip_lines.append(ip_clean)

    if not ip_lines:
        return jsonify({"error": "没有有效的 IP 结果"}), 400

    # Build IP text
    tagged = list(ip_lines)
    kv_tag = cfg.get("KV_TAG", "")
    sync_tag = cfg.get("SYNC_TAG", "")
    tag = kv_tag or sync_tag
    if tag:
        tagged = [f"{l}#{tag}" for l in tagged]
    body_text = "\n".join(tagged)

    import requests
    results = []

    # ===== KV 直写模式（遍历所有 KV 端点） =====
    for kv_ep in kv_eps:
        kv_tag = kv_ep.get("tag", "") or cfg.get("KV_TAG", "") or cfg.get("SYNC_TAG", "")
        kv_lines = [f"{l}#{kv_tag}" for l in ip_lines] if kv_tag else list(ip_lines)
        kv_body = "\n".join(kv_lines)
        account_id = kv_ep.get("account_id", "").strip()
        namespace_id = kv_ep.get("namespace_id", "").strip()
        api_token = kv_ep.get("api_token", "").strip()
        try:
            kv_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/ADD.txt"
            kv_headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "text/plain; charset=utf-8",
            }
            kv_resp = requests.put(kv_url, data=kv_body.encode('utf-8'), headers=kv_headers, timeout=15)
            if kv_resp.ok:
                results.append(f"☁️ KV({namespace_id[:8]}...) ✅")
            else:
                err = kv_resp.json() if kv_resp.headers.get('content-type','').startswith('application/json') else {}
                msg = err.get('errors',[{}])[0].get('message','') or kv_resp.text[:100]
                results.append(f"☁️ KV({namespace_id[:8]}...) ❌ {kv_resp.status_code}: {msg}")
        except requests.exceptions.Timeout:
            results.append("☁️ KV 直写 ❌ 超时")
        except requests.exceptions.ConnectionError:
            results.append("☁️ KV 直写 ❌ 无法连接")
        except Exception as e:
            results.append(f"☁️ KV 直写 ❌ {str(e)}")

    # 旧版兼容：顶层 KV 字段
    if has_kv_old:
        account_id = cfg.get("CF_ACCOUNT_ID", "").strip()
        namespace_id = cfg.get("KV_NAMESPACE_ID", "").strip()
        api_token = cfg.get("CF_API_TOKEN", "").strip()
        try:
            kv_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/ADD.txt"
            kv_headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "text/plain; charset=utf-8",
            }
            kv_resp = requests.put(kv_url, data=body_text.encode('utf-8'), headers=kv_headers, timeout=15)
            if kv_resp.ok:
                results.append("☁️ KV(旧) ✅")
            else:
                err = kv_resp.json() if kv_resp.headers.get('content-type','').startswith('application/json') else {}
                msg = err.get('errors',[{}])[0].get('message','') or kv_resp.text[:100]
                results.append(f"☁️ KV(旧) ❌ {kv_resp.status_code}: {msg}")
        except requests.exceptions.Timeout:
            results.append("☁️ KV(旧) ❌ 超时")
        except requests.exceptions.ConnectionError:
            results.append("☁️ KV(旧) ❌ 无法连接")
        except Exception as e:
            results.append(f"☁️ KV(旧) ❌ {str(e)}")

    # ===== URL+密码模式 (HTTP POST) =====
    for ep in http_eps:
        ep_url = ep.get("url", "").rstrip("/")
        ep_pass = ep.get("password", "")
        if not ep_url or not ep_pass:
            results.append(f"{ep_url or '(空地址)'} ❌ 地址或密码为空")
            continue
        # Per-endpoint tag overrides global tag
        ep_text = body_text
        ep_tag = ep.get("tag", "")
        if ep_tag:
            ep_lines = [f"{l}#{ep_tag}" for l in ip_lines]
            ep_text = "\n".join(ep_lines)
        try:
            sess = requests.Session()
            login_resp = sess.post(f"{ep_url}/login",
                                   data={"password": ep_pass},
                                   headers={"User-Agent": "CFST-Sync/1.0",
                                            "Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            if login_resp.status_code not in (200, 302) and "success" not in login_resp.text:
                results.append(f"{ep_url} ❌ 登录失败")
                continue
            resp = sess.post(f"{ep_url}/admin/ADD.txt", data=ep_text.encode('utf-8'),
                             headers={"Content-Type": "text/plain; charset=utf-8",
                                      "User-Agent": "CFST-Sync/1.0"}, timeout=15)
            if resp.status_code in (200, 201):
                results.append(f"{ep_url} ✅")
            else:
                results.append(f"{ep_url} ❌ HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            results.append(f"{ep_url} ❌ 超时")
        except requests.exceptions.ConnectionError:
            results.append(f"{ep_url} ❌ 无法连接")
        except Exception as e:
            results.append(f"{ep_url} ❌ {str(e)}")

    total_targets = len(http_eps) + len(kv_eps) + (1 if has_kv_old else 0)
    success_count = sum(1 for r in results if "✅" in r)
    msg = f"同步完成 {success_count}/{total_targets} 个目标"

    # 发送同步通知
    try:
        _send_edgetunnel_notification(success_count, total_targets, results, kv_eps or has_kv_old)
    except:
        pass

    return jsonify({"ok": success_count > 0, "message": msg, "details": results})

def _send_edgetunnel_notification(success_count, total, details, has_kv):
    """发送 Edgetunnel 同步通知"""
    import requests
    cfg = load_config()
    ewxp = cfg.get("ENABLE_WXPUSHER", False)
    epp = cfg.get("ENABLE_PUSHPLUS", False)
    if not ewxp and not epp:
        return
    dedup = set()
    succ = []
    fail = []
    for d in details:
        if d in dedup: continue
        dedup.add(d)
        if "✅" in d: succ.append(d)
        else: fail.append(d)
    lines = []
    if has_kv:
        kv_ok = any("✅" in d for d in succ)
        lines.append(f"KV直写: {'✅' if kv_ok else '❌'}")
    if succ:
        lines.append(f"HTTP同步: {len(succ)}/{total}")
    if fail:
        for f in fail[:3]:
            lines.append(f"  {f}")
    content = "\n".join(lines) if lines else "无详细信息"
    # WxPusher
    if ewxp and cfg.get("WXPUSHER_APP_TOKEN"):
        try:
            payload = {"appToken": cfg["WXPUSHER_APP_TOKEN"], "content": content, "summary": "Edgetunnel 同步", "uids": cfg.get("WXPUSHER_UIDS", [])}
            requests.post(cfg.get("WXPUSHER_API_URL", "https://wxpusher.zjiecode.com/api/send/message"), json=payload, timeout=5)
        except:
            pass
    # PushPlus
    if epp and cfg.get("PUSHPLUS_TOKEN"):
        try:
            requests.post("https://www.pushplus.plus/send", json={"token": cfg["PUSHPLUS_TOKEN"], "title": "Edgetunnel 同步", "content": content, "template": "text"}, timeout=5)
        except:
            pass

# ---------------------------------------------------------------------------
# Collect all historical IPs, re-test TCP, and sync
# ---------------------------------------------------------------------------

def _run_collect_sync():
    """Run collect+retest+sync for both Edgetunnel and GitHub (called after auto test)"""
    import requests
    live = _collect_and_retest_ips()
    if not live:
        return

    # Edgetunnel sync
    e_cfg = load_edgetunnel_config()
    if e_cfg.get("EDGETUNNEL_ENABLED"):
        endpoints = e_cfg.get("EDGETUNNEL_ENDPOINTS", [])
        kv_eps = [e for e in endpoints if e.get("enabled") and e.get("type") == "kv" and e.get("account_id") and e.get("namespace_id") and e.get("api_token")]
        http_eps = [e for e in endpoints if e.get("enabled") and e.get("type") != "kv"]
        has_kv_old = e_cfg.get("EDGETUNNEL_KV_MODE") and e_cfg.get("CF_ACCOUNT_ID") and e_cfg.get("KV_NAMESPACE_ID") and e_cfg.get("CF_API_TOKEN")
        for kv_ep in kv_eps:
            try:
                kv_tag = kv_ep.get("tag", "") or e_cfg.get("KV_TAG", "") or e_cfg.get("SYNC_TAG", "")
                kv_lines = [f"{l}#{kv_tag}" for l in live] if kv_tag else list(live)
                kv_url = f"https://api.cloudflare.com/client/v4/accounts/{kv_ep['account_id'].strip()}/storage/kv/namespaces/{kv_ep['namespace_id'].strip()}/values/ADD.txt"
                kv_headers = {"Authorization": f"Bearer {kv_ep['api_token'].strip()}", "Content-Type": "text/plain; charset=utf-8"}
                requests.put(kv_url, data="\n".join(kv_lines).encode('utf-8'), headers=kv_headers, timeout=15)
            except:
                pass
        if has_kv_old:
            try:
                kv_url = f"https://api.cloudflare.com/client/v4/accounts/{e_cfg['CF_ACCOUNT_ID'].strip()}/storage/kv/namespaces/{e_cfg['KV_NAMESPACE_ID'].strip()}/values/ADD.txt"
                kv_headers = {"Authorization": f"Bearer {e_cfg['CF_API_TOKEN'].strip()}", "Content-Type": "text/plain; charset=utf-8"}
                requests.put(kv_url, data="\n".join(live).encode('utf-8'), headers=kv_headers, timeout=15)
            except:
                pass
        for ep in http_eps:
            try:
                ep_url = ep.get("url", "").rstrip("/")
                ep_pass = ep.get("password", "")
                if not ep_url or not ep_pass: continue
                ep_tag = ep.get("tag", "")
                ep_lines = [f"{l}#{ep_tag}" for l in live] if ep_tag else list(live)
                sess = requests.Session()
                sess.post(f"{ep_url}/login", data={"password": ep_pass},
                          headers={"User-Agent": "CFST-Sync/1.0", "Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
                sess.post(f"{ep_url}/admin/ADD.txt", data="\n".join(ep_lines).encode('utf-8'),
                          headers={"Content-Type": "text/plain; charset=utf-8", "User-Agent": "CFST-Sync/1.0"}, timeout=15)
            except:
                pass

    # GitHub sync
    cfg = load_config()
    if cfg.get("GITHUB_SYNC_ENABLED"):
        token = cfg.get("GITHUB_TOKEN", "").strip()
        username = cfg.get("GITHUB_USERNAME", "").strip()
        repo = cfg.get("GITHUB_REPO", "").strip()
        branch = cfg.get("GITHUB_BRANCH", "main").strip()
        if token and username and repo:
            output_file = os.path.join(BASE_DIR, cfg.get("OUTPUT_FILE", "ip.txt"))
            try:
                with open(output_file, "w") as f:
                    f.write("\n".join(live) + "\n")
                repo_url = f"https://{username}:{token}@github.com/{username}/{repo}.git"
                subprocess.run(["git", "-C", BASE_DIR, "add", output_file], capture_output=True, timeout=180, check=True)
                subprocess.run(["git", "-C", BASE_DIR, "commit", "-m", f"Auto-sync {len(live)} live IPs [{datetime.now().strftime('%Y-%m-%d %H:%M')}]", "--allow-empty"], capture_output=True, timeout=180, check=True)
                subprocess.run(["git", "-C", BASE_DIR, "remote", "set-url", "origin", repo_url], capture_output=True, timeout=30, check=True)
                subprocess.run(["git", "-C", BASE_DIR, "push", "origin", branch], capture_output=True, timeout=180, check=True)
            except:
                pass


def _collect_and_retest_ips():
    """Collect all unique IPs from historical runs, TCP re-check, return live IPs."""
    conn = get_db()
    rows = conn.execute("SELECT results_json FROM runs WHERE status='completed'").fetchall()
    conn.close()
    if not rows:
        return []
    all_ips = set()
    for r in rows:
        try:
            results = json.loads(r["results_json"])
            for n in results.get("nodes", []):
                ns = n.get("node") or n.get("ip") or ""
                ip_clean = ns.split("#")[0].strip()
                if ip_clean:
                    all_ips.add(ip_clean)
        except:
            pass
    if not all_ips:
        return []
    # TCP re-check with 3s timeout
    import socket
    live = []
    total = len(all_ips)
    for idx, ipstr in enumerate(sorted(all_ips)):
        parts = ipstr.split(":")
        ip = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 443
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((ip, port))
            sock.close()
            live.append(ipstr)
        except:
            pass
        if (idx + 1) % 500 == 0:
            pass  # progress marker
    return live


@app.route("/api/edgetunnel/collect-sync", methods=["POST"])
def api_edgetunnel_collect_sync():
    """Collect all historical IPs, re-test TCP, sync live ones to Edgetunnel"""
    cfg = load_edgetunnel_config()
    if not cfg.get("EDGETUNNEL_ENABLED"):
        return jsonify({"ok": False, "error": "Edgetunnel 未启用"}), 400

    live = _collect_and_retest_ips()
    if not live:
        return jsonify({"ok": False, "error": "没有有效的历史记录或全部离线"}), 400

    import requests
    endpoints = cfg.get("EDGETUNNEL_ENDPOINTS", [])
    kv_eps = [e for e in endpoints if e.get("enabled") and e.get("type") == "kv" and e.get("account_id") and e.get("namespace_id") and e.get("api_token")]
    http_eps = [e for e in endpoints if e.get("enabled") and e.get("type") != "kv"]
    has_kv_old = cfg.get("EDGETUNNEL_KV_MODE") and cfg.get("CF_ACCOUNT_ID") and cfg.get("KV_NAMESPACE_ID") and cfg.get("CF_API_TOKEN")

    if not kv_eps and not http_eps and not has_kv_old:
        return jsonify({"ok": False, "error": "没有可用的同步端点"}), 400

    results = []
    # KV 直写
    for kv_ep in kv_eps:
        try:
            kv_tag = kv_ep.get("tag", "") or cfg.get("KV_TAG", "") or cfg.get("SYNC_TAG", "")
            kv_lines = [f"{l}#{kv_tag}" for l in live] if kv_tag else list(live)
            kv_body = "\n".join(kv_lines)
            kv_url = f"https://api.cloudflare.com/client/v4/accounts/{kv_ep['account_id'].strip()}/storage/kv/namespaces/{kv_ep['namespace_id'].strip()}/values/ADD.txt"
            kv_headers = {"Authorization": f"Bearer {kv_ep['api_token'].strip()}", "Content-Type": "text/plain; charset=utf-8"}
            kv_r = requests.put(kv_url, data=kv_body.encode('utf-8'), headers=kv_headers, timeout=15)
            results.append(f"☁️ KV({kv_ep['namespace_id'][:8]}...): {'✅' if kv_r.ok else '❌'}")
        except Exception as e:
            results.append(f"☁️ KV({kv_ep['namespace_id'][:8]}...): ❌ {str(e)[:50]}")
    if has_kv_old:
        try:
            kv_url = f"https://api.cloudflare.com/client/v4/accounts/{cfg['CF_ACCOUNT_ID'].strip()}/storage/kv/namespaces/{cfg['KV_NAMESPACE_ID'].strip()}/values/ADD.txt"
            kv_headers = {"Authorization": f"Bearer {cfg['CF_API_TOKEN'].strip()}", "Content-Type": "text/plain; charset=utf-8"}
            kv_r = requests.put(kv_url, data=body_text if 'body_text' in dir() else "\n".join(live).encode('utf-8'), headers=kv_headers, timeout=15)
            results.append(f"☁️ KV(旧): {'✅' if kv_r.ok else '❌'}")
        except Exception as e:
            results.append(f"☁️ KV(旧): ❌ {str(e)[:50]}")
    # HTTP POST
    for ep in http_eps:
        ep_url = ep.get("url", "").rstrip("/")
        ep_pass = ep.get("password", "")
        if not ep_url or not ep_pass:
            continue
        ep_tag = ep.get("tag", "")
        ep_lines = [f"{l}#{ep_tag}" for l in live] if ep_tag else list(live)
        ep_body = "\n".join(ep_lines)
        try:
            sess = requests.Session()
            sess.post(f"{ep_url}/login", data={"password": ep_pass},
                      headers={"User-Agent": "CFST-Sync/1.0", "Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            r = sess.post(f"{ep_url}/admin/ADD.txt", data=ep_body.encode('utf-8'),
                          headers={"Content-Type": "text/plain; charset=utf-8", "User-Agent": "CFST-Sync/1.0"}, timeout=15)
            results.append(f"{ep_url}: {'✅' if r.ok else '❌'}")
        except Exception as e:
            results.append(f"{ep_url}: ❌ {str(e)[:50]}")

    return jsonify({"ok": True, "live_count": len(live), "details": results})


@app.route("/api/github/collect-sync", methods=["POST"])
def api_github_collect_sync():
    """Collect all historical IPs, re-test TCP, sync live ones to GitHub"""
    cfg = load_config()
    if not cfg.get("GITHUB_SYNC_ENABLED"):
        return jsonify({"ok": False, "error": "GitHub 同步未启用"}), 400

    live = _collect_and_retest_ips()
    if not live:
        return jsonify({"ok": False, "error": "没有有效的历史记录或全部离线"}), 400

    # Write ip.txt
    output_file = os.path.join(BASE_DIR, cfg.get("OUTPUT_FILE", "ip.txt"))
    with open(output_file, "w") as f:
        f.write("\n".join(live) + "\n")

    # Git push
    token = cfg.get("GITHUB_TOKEN", "").strip()
    username = cfg.get("GITHUB_USERNAME", "").strip()
    repo = cfg.get("GITHUB_REPO", "").strip()
    branch = cfg.get("GITHUB_BRANCH", "main").strip()
    max_retries = cfg.get("GITHUB_SYNC_MAX_RETRIES", 3)
    retry_delay = cfg.get("GITHUB_SYNC_RETRY_DELAY", 3)
    process_timeout = cfg.get("GIT_SYNC_PROCESS_TIMEOUT", 180)

    if not token or not username or not repo:
        return jsonify({"ok": False, "error": "GitHub 配置不完整", "live_count": len(live)}), 400

    # Configure git remote with token
    repo_url = f"https://{username}:{token}@github.com/{username}/{repo}.git"
    for attempt in range(max_retries):
        try:
            subprocess.run(["git", "-C", BASE_DIR, "add", output_file],
                         capture_output=True, timeout=process_timeout, check=True)
            subprocess.run(["git", "-C", BASE_DIR, "commit", "-m", f"Auto-sync {len(live)} live IPs from historical check [{datetime.now().strftime('%Y-%m-%d %H:%M')}]", "--allow-empty"],
                         capture_output=True, timeout=process_timeout, check=True)
            subprocess.run(["git", "-C", BASE_DIR, "remote", "set-url", "origin", repo_url],
                         capture_output=True, timeout=30, check=True)
            subprocess.run(["git", "-C", BASE_DIR, "push", "origin", branch],
                         capture_output=True, timeout=process_timeout, check=True)
            return jsonify({"ok": True, "live_count": len(live), "details": [f"GitHub ✅ 推送 {len(live)} 个IP到 {username}/{repo} ({branch})"]})
        except subprocess.CalledProcessError as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return jsonify({"ok": False, "error": f"Git push 失败: {e.stderr.decode() if e.stderr else str(e)[:100]}", "live_count": len(live)}), 500
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return jsonify({"ok": False, "error": f"Git push 异常: {str(e)[:100]}", "live_count": len(live)}), 500

    return jsonify({"ok": False, "error": "Git push 超过重试次数", "live_count": len(live)}), 500


@app.route("/api/github/sync-latest", methods=["POST"])
def api_github_sync_latest():
    """Sync latest completed run's IPs to GitHub"""
    cfg = load_config()
    if not cfg.get("GITHUB_SYNC_ENABLED"):
        return jsonify({"ok": False, "error": "GitHub 同步未启用"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT results_json FROM runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        ip_txt_path = os.path.join(BASE_DIR, cfg.get("OUTPUT_FILE", "ip.txt"))
        if not os.path.exists(ip_txt_path):
            return jsonify({"ok": False, "error": "没有已完成的历史记录，请先跑一次测速"}), 400
        with open(ip_txt_path, "r") as f:
            ip_lines = [l.strip().split("#")[0].strip() for l in f if l.strip()]
    else:
        results = json.loads(row["results_json"])
        nodes = results.get("nodes", [])
        ip_lines = []
        for n in nodes:
            node_str = n.get("node") or n.get("ip") or ""
            ip_clean = node_str.split("#")[0].strip()
            if ip_clean:
                ip_lines.append(ip_clean)

    if not ip_lines:
        return jsonify({"ok": False, "error": "没有有效的 IP 结果"}), 400

    output_file = os.path.join(BASE_DIR, cfg.get("OUTPUT_FILE", "ip.txt"))
    with open(output_file, "w") as f:
        f.write("\n".join(ip_lines) + "\n")

    token = cfg.get("GITHUB_TOKEN", "").strip()
    username = cfg.get("GITHUB_USERNAME", "").strip()
    repo = cfg.get("GITHUB_REPO", "").strip()
    branch = cfg.get("GITHUB_BRANCH", "main").strip()
    max_retries = cfg.get("GITHUB_SYNC_MAX_RETRIES", 3)
    retry_delay = cfg.get("GITHUB_SYNC_RETRY_DELAY", 3)
    process_timeout = cfg.get("GIT_SYNC_PROCESS_TIMEOUT", 180)

    if not token or not username or not repo:
        return jsonify({"ok": False, "error": "GitHub 配置不完整"}), 400

    repo_url = f"https://{username}:{token}@github.com/{username}/{repo}.git"
    for attempt in range(max_retries):
        try:
            subprocess.run(["git", "-C", BASE_DIR, "add", output_file],
                         capture_output=True, timeout=process_timeout, check=True)
            subprocess.run(["git", "-C", BASE_DIR, "commit", "-m", f"Auto-sync {len(ip_lines)} IPs [{datetime.now().strftime('%Y-%m-%d %H:%M')}]", "--allow-empty"],
                         capture_output=True, timeout=process_timeout, check=True)
            subprocess.run(["git", "-C", BASE_DIR, "remote", "set-url", "origin", repo_url],
                         capture_output=True, timeout=30, check=True)
            subprocess.run(["git", "-C", BASE_DIR, "push", "origin", branch],
                         capture_output=True, timeout=process_timeout, check=True)
            return jsonify({"ok": True, "details": [f"GitHub ✅ 推送 {len(ip_lines)} 个IP到 {username}/{repo} ({branch})"]})
        except subprocess.CalledProcessError as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return jsonify({"ok": False, "error": f"Git push 失败: {e.stderr.decode() if e.stderr else str(e)[:100]}"}), 500
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return jsonify({"ok": False, "error": f"Git push 异常: {str(e)[:100]}"}), 500

    return jsonify({"ok": False, "error": "Git push 超过重试次数"}), 500


# ---------------------------------------------------------------------------
# Run Detail Page
# ---------------------------------------------------------------------------

@app.route("/run/<int:run_id>")
def run_detail(run_id):
    return render_template("run_detail.html", run_id=run_id)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"* CFST Dashboard starting on http://0.0.0.0:6006")
    print(f"* Config: {CONFIG_PATH}")
    print(f"* Database: {DB_PATH}")
    ensure_config_symlink()
    start_scheduler()
    app.run(host="0.0.0.0", port=6006, debug=True, threaded=True)

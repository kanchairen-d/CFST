# cfnb 可用性检测 API 服务
# Python Flask 版，部署在任何有网络的机器上
# pip install flask requests
# python3 check_api.py

from flask import Flask, request, jsonify
import requests
import time
import socket
import ssl
import concurrent.futures

app = Flask(__name__)

@app.route("/check")
def check():
    proxy_ip = request.args.get("proxyip")
    if not proxy_ip:
        return jsonify({"error": "Missing proxyip"}), 400

    port = int(request.args.get("port", "443"))
    result = probe_ip(proxy_ip, port)

    resp = jsonify(result)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

def probe_ip(ip, port):
    start = time.time()
    result = {
        "candidate": ip,
        "success": False,
        "proxyIP": ip,
        "portRemote": port,
        "inferred_stack": "unknown",
        "supports_ipv4": False,
        "supports_ipv6": False,
        "dual_stack": False,
        "responseTime": 0,
        "colo": None,
        "probe_results": {
            "ipv4": {"candidate": ip, "connect_ms": None, "tls_ms": None, "http_ms": None, "status_code": None, "ok": False},
            "ipv6": {"candidate": None, "connect_ms": None, "tls_ms": None, "http_ms": None, "status_code": None, "ok": False},
        },
    }

    # TCP 连接探测
    t0 = time.time()
    try:
        sock = socket.create_connection((ip, port), timeout=5)
        connect_ms = int((time.time() - t0) * 1000)
        result["probe_results"]["ipv4"]["connect_ms"] = connect_ms
        result["responseTime"] = connect_ms
    except Exception as e:
        result["responseTime"] = int((time.time() - t0) * 1000)
        return result

    # TLS 握手
    t1 = time.time()
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls_sock = context.wrap_socket(sock, server_hostname="cloudflare.com")
        tls_ms = int((time.time() - t1) * 1000)
        result["probe_results"]["ipv4"]["tls_ms"] = tls_ms

        # HTTP 请求
        t2 = time.time()
        tls_sock.sendall(
            b"GET /cdn-cgi/trace HTTP/1.1\r\n"
            b"Host: cloudflare.com\r\n"
            b"User-Agent: curl/8.0\r\n"
            b"Connection: close\r\n\r\n"
        )
        data = b""
        while True:
            chunk = tls_sock.recv(4096)
            if not chunk:
                break
            data += chunk
        tls_sock.close()

        http_ms = int((time.time() - t2) * 1000)
        result["probe_results"]["ipv4"]["http_ms"] = http_ms

        # 解析响应
        body = data.split(b"\r\n\r\n", 1)
        status_line = data.split(b"\r\n")[0]
        status_code = int(status_line.split(b" ")[1]) if b" " in status_line else 0
        result["probe_results"]["ipv4"]["status_code"] = status_code

        if len(body) > 1:
            trace_text = body[1].decode("utf-8", errors="replace")
            # 提取 colo
            for line in trace_text.split("\n"):
                if line.startswith("colo="):
                    result["colo"] = line.split("=", 1)[1].strip()
                if line.startswith("tls="):
                    result["inferred_stack"] = "ipv4"

            if "colo=" in trace_text:
                result["success"] = True
                result["supports_ipv4"] = True
    except Exception as e:
        pass

    # 总耗时
    result["totalTime"] = int((time.time() - start) * 1000)
    return result

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
"""通知渠道实现"""
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Callable, Dict, Optional

import requests

logger = logging.getLogger("cfst.channels")

# 超时配置
TIMEOUT = 10


def _fmt_msg(title: str, content: str, level: str) -> str:
    """格式化消息文本 - title 已含事件专属 emoji"""
    return f"{title}\n\n{content}"


def _fmt_markdown(title: str, content: str, level: str) -> str:
    """格式化 Markdown 消息 - title 已含事件专属 emoji"""
    return f"# {title}\n\n{content}"


# ─── 企业微信 ───

def send_wechat(config: Dict, title: str, content: str, level: str) -> bool:
    url = config.get("webhook_url", "").strip()
    if not url:
        return False
    text = _fmt_msg(title, content, level)
    payload = {"msgtype": "markdown", "markdown": {"content": text}}
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── 钉钉 ───

def send_dingtalk(config: Dict, title: str, content: str, level: str) -> bool:
    url = config.get("webhook_url", "").strip()
    secret = config.get("secret", "").strip()
    if not url:
        return False
    if secret:
        timestamp = str(int(time.time() * 1000))
        sign_str = f"{timestamp}\n{secret}"
        sign = hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).digest()
        sign_b64 = __import__("base64").b64encode(sign).decode()
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={timestamp}&sign={sign_b64}"
    text = _fmt_msg(title, content, level)
    payload = {"msgtype": "text", "text": {"content": text}}
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── 飞书 ───

def send_feishu(config: Dict, title: str, content: str, level: str) -> bool:
    url = config.get("webhook_url", "").strip()
    if not url:
        return False
    text = _fmt_msg(title, content, level)
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": [[{"tag": "text", "text": content}]]
                }
            }
        }
    }
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── Bark ───

def send_bark(config: Dict, title: str, content: str, level: str) -> bool:
    key = config.get("key", "").strip()
    base_url = config.get("base_url", "https://api.day.app").strip().rstrip("/")
    if not key:
        return False
    url = f"{base_url}/{key}"
    payload = {
        "title": title,
        "body": content,
        "group": "NAS",
        "sound": "push" if level == "error" else "minuet",
        "icon": "https://cdn.jsdelivr.net/gh/homarr-labs/homarr/public/images/logo.png",
    }
    if level == "warning":
        payload["level"] = "timeSensitive"
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── PushPlus ───

def send_pushplus(config: Dict, title: str, content: str, level: str) -> bool:
    token = config.get("token", "").strip()
    if not token:
        return False
    template = config.get("template", "html")
    channel = config.get("channel", "wechat")
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": template,
        "channel": channel,
    }
    try:
        r = requests.post("http://www.pushplus.plus/send", json=payload, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── 魔法推送 ───

def send_magic_push(config: Dict, title: str, content: str, level: str) -> bool:
    url = config.get("base_url", "").strip().rstrip("/")
    token = config.get("token", "").strip()
    if not url or not token:
        return False
    payload = {"title": title, "content": content}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.post(f"{url}/api/push", json=payload, headers=headers, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── WxPusher ───

def send_wxpusher(config: Dict, title: str, content: str, level: str) -> bool:
    app_token = config.get("appToken", "").strip()
    uids = config.get("uids", [])
    if not app_token or not uids:
        logger.warning("WxPusher 配置缺失: appToken=%s uids=%s", bool(app_token), uids)
        return False
    payload = {
        "appToken": app_token,
        "content": f"{title}\n\n{content}",
        "contentType": 1,
        "uids": uids if isinstance(uids, list) else [str(uids)],
    }
    try:
        r = requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=TIMEOUT)
        ok = r.status_code == 200
        logger.info("WxPusher 发送结果: status=%s ok=%s", r.status_code, ok)
        if not ok:
            logger.warning("WxPusher 响应: %s", r.text[:200])
        return ok
    except Exception as e:
        logger.error("WxPusher 异常: %s", e)
        return False


# ─── Telegram ───

def send_telegram(config: Dict, title: str, content: str, level: str) -> bool:
    bot_token = config.get("bot_token", "").strip()
    chat_id = config.get("chat_id", "").strip()
    if not bot_token or not chat_id:
        return False
    text = _fmt_msg(title, content, level)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── Discord ───

def send_discord(config: Dict, title: str, content: str, level: str) -> bool:
    url = config.get("webhook_url", "").strip()
    if not url:
        return False
    color = {"info": 5814783, "warning": 16766720, "error": 15548997}.get(level, 5814783)
    embed = {
        "embeds": [{
            "title": title,
            "description": content,
            "color": color,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }]
    }
    try:
        r = requests.post(url, json=embed, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── Server酱 ───

def send_serverchan(config: Dict, title: str, content: str, level: str) -> bool:
    send_key = config.get("send_key", "").strip()
    if not send_key:
        return False
    text = f"{title} {content}"
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{send_key}.send",
                          data={"title": title, "desp": text}, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── 自定义 Webhook ───

def send_custom_webhook(config: Dict, title: str, content: str, level: str) -> bool:
    url = config.get("url", "").strip()
    template = config.get("template", "json")
    if not url:
        return False

    text = _fmt_msg(title, content, level)
    if template == "json":
        payload = {"title": title, "content": text, "level": level}
        try:
            r = requests.post(url, json=payload, timeout=TIMEOUT)
            return r.status_code == 200
        except Exception:
            return False
    elif template == "text":
        try:
            r = requests.post(url, data=text, timeout=TIMEOUT)
            return r.status_code == 200
        except Exception:
            return False
    return False


# ─── 企业微信应用消息 ───

def send_wechat_app(config: Dict, title: str, content: str, level: str) -> bool:
    """通过企业微信应用发送消息（需要获取 access_token）。"""
    corp_id = config.get("corp_id", "").strip()
    corp_secret = config.get("corp_secret", "").strip()
    agent_id = config.get("agent_id", "").strip()
    to_user = config.get("to_user", "@all").strip()
    if not corp_id or not corp_secret or not agent_id:
        return False

    try:
        # 获取 token
        r = requests.get(f"https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                         params={"corpid": corp_id, "corpsecret": corp_secret},
                         timeout=TIMEOUT)
        if r.status_code != 200:
            return False
        body = r.json()
        if body.get("errcode") != 0:
            return False
        token = body["access_token"]

        # 发送消息
        text = _fmt_msg(title, content, level)
        payload = {
            "touser": to_user,
            "msgtype": "text",
            "agentid": int(agent_id),
            "text": {"content": text},
            "safe": 0,
        }
        r = requests.post(f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                          json=payload, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ─── SMTP 邮件 ───

def send_smtp(config: Dict, title: str, content: str, level: str) -> bool:
    server = config.get("server", "").strip()
    port = int(config.get("port", 465))
    username = config.get("username", "").strip()
    password = config.get("password", "").strip()
    to_addr = config.get("to_addr", "").strip()
    if not server or not username or not password or not to_addr:
        return False

    try:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = f"[CFST] {title}"
        msg["From"] = username
        msg["To"] = to_addr
        msg.set_content(_fmt_msg(title, content, level))

        if port == 465:
            import ssl
            with smtplib.SMTP_SSL(server, port, timeout=15,
                                  context=ssl.create_default_context()) as client:
                client.login(username, password)
                client.send_message(msg)
        else:
            with smtplib.SMTP(server, port, timeout=15) as client:
                client.starttls()
                client.login(username, password)
                client.send_message(msg)
        return True
    except Exception:
        return False


# ─── 渠道注册表 ───

channel_senders: Dict[str, Callable] = {
    "wechat": send_wechat,
    "dingtalk": send_dingtalk,
    "feishu": send_feishu,
    "bark": send_bark,
    "pushplus": send_pushplus,
    "magic_push": send_magic_push,
    "wxpusher": send_wxpusher,
    "telegram": send_telegram,
    "discord": send_discord,
    "serverchan": send_serverchan,
    "custom_webhook": send_custom_webhook,
    "wechat_app": send_wechat_app,
    "smtp": send_smtp,
}

CHANNEL_INFO = {
    "wechat": {"label": "企业微信", "fields": [{"key": "webhook_url", "label": "Webhook URL", "type": "text"}]},
    "dingtalk": {"label": "钉钉", "fields": [
        {"key": "webhook_url", "label": "Webhook URL", "type": "text"},
        {"key": "secret", "label": "加签密钥（可选）", "type": "text"},
    ]},
    "feishu": {"label": "飞书", "fields": [{"key": "webhook_url", "label": "Webhook URL", "type": "text"}]},
    "bark": {"label": "Bark", "fields": [
        {"key": "key", "label": "推送 Key", "type": "text"},
        {"key": "base_url", "label": "自建服务器地址（可选）", "type": "text"},
    ]},
    "pushplus": {"label": "PushPlus", "fields": [
        {"key": "token", "label": "Token", "type": "text"},
        {"key": "template", "label": "消息模板", "type": "select", "options": ["html", "txt", "markdown"]},
        {"key": "channel", "label": "推送渠道", "type": "select", "options": ["wechat", "webhook", "cp", "mail", "sms"]},
    ]},
    "magic_push": {"label": "魔法推送", "fields": [
        {"key": "base_url", "label": "服务器地址", "type": "text"},
        {"key": "token", "label": "Token", "type": "text"},
    ]},
    "wxpusher": {"label": "WxPusher", "fields": [
        {"key": "appToken", "label": "AppToken", "type": "text"},
        {"key": "uids", "label": "UID（多个用逗号分隔）", "type": "text"},
    ]},
    "telegram": {"label": "Telegram", "fields": [
        {"key": "bot_token", "label": "Bot Token", "type": "text"},
        {"key": "chat_id", "label": "Chat ID", "type": "text"},
    ]},
    "discord": {"label": "Discord", "fields": [{"key": "webhook_url", "label": "Webhook URL", "type": "text"}]},
    "serverchan": {"label": "Server酱", "fields": [{"key": "send_key", "label": "SendKey", "type": "text"}]},
    "custom_webhook": {"label": "自定义 Webhook", "fields": [
        {"key": "url", "label": "URL", "type": "text"},
        {"key": "template", "label": "消息格式", "type": "select", "options": ["json", "text"]},
    ]},
    "wechat_app": {"label": "企业微信应用", "fields": [
        {"key": "corp_id", "label": "企业 ID", "type": "text"},
        {"key": "corp_secret", "label": "应用 Secret", "type": "text"},
        {"key": "agent_id", "label": "AgentID", "type": "text"},
        {"key": "to_user", "label": "接收人(@all 或 UserID)", "type": "text"},
    ]},
    "smtp": {"label": "SMTP 邮件", "fields": [
        {"key": "server", "label": "SMTP 服务器", "type": "text"},
        {"key": "port", "label": "端口", "type": "text"},
        {"key": "username", "label": "用户名", "type": "text"},
        {"key": "password", "label": "密码", "type": "password"},
        {"key": "to_addr", "label": "接收邮箱", "type": "text"},
    ]},
}
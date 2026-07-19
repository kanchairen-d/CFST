# CFST · Cloudflare IP 优选工具

Cloudflare CDN 节点自动优选工具，带 Web 管理面板。从多个公开数据源聚合节点，通过 TCP 延迟筛选 → IP 可用性二次检测 → HTTP 延迟及抖动检测 → 真实带宽测速 多重机制，筛选出当前网络环境下最快的 Cloudflare IP，并支持自动更新至 Cloudflare DNS 及同步至 GitHub。

## 功能

- **多模式筛选** — 全局最优 TopN / 分国家最优 TopN
- **TCP 连接测试** — 并发测延迟，可设成功率阈值
- **可用性二次检测** — API 验证代理能力
- **HTTP 延迟与抖动检测** — 多次探测 HTTP 响应，计算平均延迟与抖动（标准差）
- **真实带宽测速** — curl 下载测速，实测吞吐量
- **综合加权排序** — 带宽、TCP 延迟、HTTP 延迟与抖动，四个权重可自由调整
- **多源自适应聚合** — 支持多个数据源，自动识别并解析任意格式（标准代码、中文名、emoji 国旗、JSON 等）
- **前置过滤** — 端口过滤 → 黑名单过滤 → 白名单过滤（均可开关）
- **DNS 黑名单** — DNS 更新时剔除指定国家节点
- **IPv6 落地过滤** — 过滤落地仅 IPv6 的节点
- **IP 风险等级过滤** — 仅允许低风险节点，高危自动回退
- **IP 地区校准** — 基于 ipinfo.io 异步并发查询，自动校正节点国家代码
- **Cloudflare DNS 更新** — 原子批量替换同名 A/TXT 记录
- **微信实时通知** — 集成 WxPusher / PushPlus，异常/结果推送
- **定时自动运行** — 内置调度器，支持 cron 表达式
- **GitHub 自动同步** — `ip.txt` 推送至仓库，方便订阅
- **Web 管理面板** — 仪表盘、测速控制、历史记录、配置管理

## 部署

### 方式一：Docker Compose（推荐）

```yaml
services:
  cfst:
    image: ghcr.io/kanchairen-d/cfst:latest
    container_name: cfst
    ports:
      - "6006:6006"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
```

启动：

```bash
docker compose up -d
```

### 方式二：直接拉取镜像

```bash
docker pull ghcr.io/kanchairen-d/cfst:latest

docker run -d \
  --name cfst \
  -p 6006:6006 \
  -v ./data:/app/data \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  ghcr.io/kanchairen-d/cfst:latest
```

### 方式三：源码构建

```bash
git clone https://github.com/kanchairen-d/CFST.git
cd CFST
docker compose up -d
```

## 访问

- Web 管理面板：`http://localhost:6006`
- 配置管理：`http://localhost:6006/settings`
- 测速运行：`http://localhost:6006/speedtest`
- 历史记录：`http://localhost:6006/history`

## 配置

数据目录 `./data/` 挂载后可持久化配置，主要文件：

- `config.json` — 核心配置文件（测速参数、权重、通知等）
- `schedule.json` — 定时调度配置
- `results.db` — 测速结果数据库
- `ip.txt` — 优选 IP 结果

### 核心配置参数

| 参数 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `USE_GLOBAL_MODE` | 全局模式（false 为分国家模式） | `true` |
| `GLOBAL_TOP_N` | 全局最优数量 | `15` |
| `PER_COUNTRY_TOP_N` | 每国最优数量 | `1` |
| `BANDWIDTH_CANDIDATES` | 带宽测速候选数 | `150` |
| `TCP_PROBES` | TCP 探测次数 | `1` |
| `TIMEOUT` | 超时时间（秒） | `2.0` |
| `TCP_LATENCY_WEIGHT` | TCP 延迟权重 | `0.0` |
| `BANDWIDTH_WEIGHT` | 带宽权重 | `0.4` |
| `HTTP_LATENCY_WEIGHT` | HTTP 延迟权重 | `0.3` |
| `HTTP_JITTER_WEIGHT` | HTTP 抖动权重 | `0.3` |

## 技术栈

- **后端** — Python / Flask / Gunicorn
- **数据库** — SQLite
- **前端** — Tailwind CSS / Alpine.js
- **部署** — Docker / GitHub Actions

## 许可证

MIT
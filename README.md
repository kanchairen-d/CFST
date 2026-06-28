# Cloudflare IP 优选工具

[![GitHub stars](https://img.shields.io/github/stars/xinyitang3/cfnb?style=social)](https://github.com/xinyitang3/cfnb/stargazers)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-blue)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()
[![Last Commit](https://img.shields.io/github/last-commit/xinyitang3/cfnb?label=Last%20Commit)](https://github.com/xinyitang3/cfnb/commits)
[![Repo Size](https://img.shields.io/github/repo-size/xinyitang3/cfnb?label=Repo%20Size)](https://github.com/xinyitang3/cfnb)
[![Telegram](https://img.shields.io/badge/Telegram-@MiaChatChannel-26A5E4?logo=telegram)](https://t.me/MiaChatChannel)

> ⭐ **如果觉得好用，点个 Star 支持一下～**

这是一个全自动的 **Cloudflare CDN 节点优选工具docker版**。它通过 **TCP 延迟筛选** + **IP 可用性二次检测** + **HTTP 延迟及抖动检测** + **真实带宽测速** 多重机制，从多个公开数据源中聚合节点，自动识别并解析任意格式（标准代码、中文名、emoji国旗、JSON等），筛选出当前网络环境下速度最快、延迟最低、抖动最小的 Cloudflare IP，并支持**自动更新至 Cloudflare DNS** 以及**同步至 GitHub 仓库**，同时支持微信实时通知。

> [!IMPORTANT]
> 本项目基于https://github.com/kanchairen-d/cfnb，DOCKER化改造
> 新增自动同步edt等等功能，带界面更直观！

---

## ✨ 功能特性

| 模块 | 说明 |
| :--- | :--- |
| 🌐 **多模式筛选** | 全局最优 TopN / 分国家最优 TopN |
| ⚡ **TCP 连接测试** | 并发测延迟，可设成功率阈值 |
| 🔍 **可用性二次检测** | API 验证代理能力 |
| 🔍 **HTTP 延迟与抖动检测** | 多次探测 HTTP 响应，计算平均延迟与抖动（标准差），过滤非 Cloudflare 节点，提升代理兼容性 |
| 📶 **真实带宽测速** | curl 下载测速，实测吞吐量 |
| ⚖️ **综合加权排序** | 同时考虑带宽、TCP 延迟、HTTP 延迟与抖动，四个权重可自由调整，选出综合体验最优的节点 |
| 🧩 **多源自适应聚合** | 支持多个数据源，自动识别并解析任意格式（标准代码、中文名、emoji国旗、JSON等），统一转换为标准格式 |
| ⚙️ **前置过滤（按序执行）** | TCP 测试前按序：端口过滤 → 黑名单过滤 → 白名单过滤（均可开关） |
| 🚫 **DNS 黑名单** | DNS 更新时剔除指定国家节点（**仅作用于 DNS 更新环节**） |
| 🛡️ **IPv6 落地过滤** | 过滤落地仅 IPv6 的节点，保留 IPv4/双栈节点（**仅作用于 DNS 更新环节**） |
| 🔍 **IP 风险等级过滤** | 仅允许低风险节点，高危自动回退（**仅作用于 DNS 更新环节**） |
| 🗺️ **IP 地区校准** | 基于 ipinfo.io 异步并发查询，自动校正节点国家代码，结果缓存复用 |
| 🔒 **强制直连模式** | 可配置开关，一键清除系统代理，确保所有测试流量走直连 |
| ☁️ **Cloudflare DNS 更新** | 原子批量替换同名 A/TXT 记录 |
| 📬 **微信实时通知** | 集成 WxPusher，异常/结果推送 |
| 🔄 **定时自动运行** | Windows 计划任务 / Linux cron，每 5 分钟 |
| 🚀 **一键部署** | `setup.ps1` / `setup.sh` 自动安装依赖并配置 |
| 📤 **GitHub 自动同步** | `ip.txt` 推送至仓库，方便订阅 |
| 🔒 **隐私保护** | `.gitignore` 忽略敏感文件 |
| 🖥️ **跨平台兼容** | 同时支持 Windows 和 Linux |
| 🔧 **Fork 修复** | 内置 `update_fork.ps1` / `update_fork.sh`，解决 fork 后的历史冲突与认证问题 |

---
## 🙏 致谢

- 节点数据源 & 检测 API：[cmliussss](https://github.com/cmliussss)
- IP 风险检测 API：[ipapi.is](https://ipapi.is/)
- IP 地区校准：[ipinfo.io](https://ipinfo.io/)
- 微信通知服务：[WxPusher](https://wxpusher.zjiecode.com/)

---

**许可证**：本项目采用 [MIT License](https://opensource.org/licenses/MIT) 开源。

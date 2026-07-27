"""统一通知接口 - CFST 适配版"""
import logging
from typing import Dict, List, Optional

from .channels import channel_senders

logger = logging.getLogger("cfst.notifier")


class Notifier:
    """统一通知器。通过 channels 字典列表驱动所有渠道。"""

    def __init__(self, channels: Optional[List[Dict]] = None):
        self._channels: List[Dict] = channels or []

    @property
    def enabled(self) -> bool:
        return bool(self._channels)

    @property
    def channel_count(self) -> int:
        return len(self._channels)

    def reload(self, channels: List[Dict]):
        """重载渠道配置"""
        self._channels = channels

    def send(self, title: str, content: str, level: str = "info") -> Dict[str, bool]:
        """发送通知到所有已配置的渠道。返回 {channel_name: success}"""
        if not self._channels:
            logger.debug("未配置通知渠道，跳过")
            return {}

        results = {}
        for ch in self._channels:
            ch_type = ch.get("type", "")
            ch_config = ch.get("config", {})
            sender = channel_senders.get(ch_type)
            if not sender:
                logger.warning(f"未知渠道类型: {ch_type}")
                results[ch_type] = False
                continue

            try:
                ok = sender(ch_config, title, content, level)
                results[ch_type] = ok
                if ok:
                    logger.info("通知渠道 %s 发送成功: %s", ch_type, title[:40])
                else:
                    logger.warning(f"通知渠道 {ch_type} 发送失败")
            except Exception as e:
                logger.error(f"通知渠道 {ch_type} 异常: {e}")
                results[ch_type] = False

        return results

    def send_test(self, channel_type: str, channel_config: Dict, custom_message: str = "") -> bool:
        """发送测试消息到指定渠道"""
        sender = channel_senders.get(channel_type)
        if not sender:
            return False
        try:
            content = custom_message or "这是一条来自 CFST 的测试消息"
            return sender(channel_config, "测试消息", content, "info")
        except Exception as e:
            logger.error(f"测试发送失败 {channel_type}: {e}")
            return False
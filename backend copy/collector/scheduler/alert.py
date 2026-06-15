#!/usr/bin/env python3
"""
告警机制 - 支持多渠道告警
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header

from utils.logger import setup_logger
from utils.config import config

logger = setup_logger('alert_manager')


class AlertChannel(ABC):
    """告警渠道抽象类"""
    
    @abstractmethod
    def send(self, title: str, message: str, level: str = "warning") -> bool:
        """发送告警"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查渠道是否可用"""
        pass


class DingTalkChannel(AlertChannel):
    """钉钉机器人告警"""
    
    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        self.webhook_url = webhook_url
        self.secret = secret
    
    def send(self, title: str, message: str, level: str = "warning") -> bool:
        try:
            # 根据等级设置颜色
            color_map = {
                "info": "#3498db",
                "warning": "#f39c12",
                "error": "#e74c3c",
                "critical": "#c0392b"
            }
            color = color_map.get(level, "#f39c12")
            
            # 构建消息
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"""**<font color="{color}">{title}</font>**
---
{message}
---
发送时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
                }
            }
            
            # 如果有 secret，需要加签（简化版，暂不实现）
            response = requests.post(self.webhook_url, json=data, timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"钉钉告警发送成功: {title}")
                return True
            else:
                logger.error(f"钉钉告警失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"钉钉告警异常: {str(e)}")
            return False
    
    def is_available(self) -> bool:
        return bool(self.webhook_url)


class EmailChannel(AlertChannel):
    """邮件告警"""
    
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        sender: str,
        password: str,
        receivers: List[str],
        use_ssl: bool = True
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.receivers = receivers
        self.use_ssl = use_ssl
    
    def send(self, title: str, message: str, level: str = "warning") -> bool:
        try:
            # 构建邮件
            msg = MIMEText(message, 'plain', 'utf-8')
            msg['From'] = Header(f"量化系统 <{self.sender}>", 'utf-8')
            msg['To'] = Header(', '.join(self.receivers), 'utf-8')
            
            # 根据等级设置标题前缀
            prefix_map = {
                "info": "[INFO]",
                "warning": "[WARNING]",
                "error": "[ERROR]",
                "critical": "[CRITICAL]"
            }
            prefix = prefix_map.get(level, "[WARNING]")
            msg['Subject'] = Header(f"{prefix} {title}", 'utf-8')
            
            # 发送
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.receivers, msg.as_string())
            server.quit()
            
            logger.info(f"邮件告警发送成功: {title}")
            return True
            
        except Exception as e:
            logger.error(f"邮件告警异常: {str(e)}")
            return False
    
    def is_available(self) -> bool:
        return all([
            self.smtp_server,
            self.smtp_port,
            self.sender,
            self.password,
            self.receivers
        ])


class ConsoleChannel(AlertChannel):
    """控制台告警（用于测试）"""
    
    def send(self, title: str, message: str, level: str = "warning") -> bool:
        level_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🔥"
        }
        emoji = level_emoji.get(level, "⚠️")
        print(f"\n{emoji} [{level.upper()}] {title}")
        print(f"  {message}\n")
        return True
    
    def is_available(self) -> bool:
        return True


class AlertManager:
    """告警管理器"""
    
    def __init__(self, channels: Optional[List[AlertChannel]] = None):
        self.channels = channels or []
        # 告警去重：记录最近发送的告警，避免重复轰炸
        self.recent_alerts: Dict[str, float] = {}
        self.dedup_window = 300  # 5分钟内不重复发送相同告警
    
    def add_channel(self, channel: AlertChannel):
        """添加告警渠道"""
        if channel.is_available():
            self.channels.append(channel)
            logger.info(f"添加告警渠道: {type(channel).__name__}")
        else:
            logger.warning(f"告警渠道不可用: {type(channel).__name__}")
    
    def alert(
        self,
        title: str,
        message: str,
        level: str = "warning",
        dedup_key: Optional[str] = None
    ):
        """发送告警到所有渠道"""
        import time
        
        # 去重检查
        if dedup_key:
            now = time.time()
            if dedup_key in self.recent_alerts:
                if now - self.recent_alerts[dedup_key] < self.dedup_window:
                    logger.debug(f"告警去重跳过: {title}")
                    return
            self.recent_alerts[dedup_key] = now
        
        # 清理过期的去重记录
        self._cleanup_old_dedup()
        
        logger.info(f"发送告警 [{level}]: {title}")
        
        # 发送到所有渠道
        success_count = 0
        for channel in self.channels:
            try:
                if channel.send(title, message, level):
                    success_count += 1
            except Exception as e:
                logger.error(f"告警渠道 {type(channel).__name__} 发送失败: {e}")
        
        if success_count == 0:
            logger.error("所有告警渠道发送失败")
    
    def _cleanup_old_dedup(self):
        """清理过期的去重记录"""
        import time
        now = time.time()
        expired_keys = [
            k for k, t in self.recent_alerts.items()
            if now - t > self.dedup_window * 2
        ]
        for k in expired_keys:
            del self.recent_alerts[k]


def create_alert_manager_from_config() -> AlertManager:
    """从配置文件创建告警管理器"""
    manager = AlertManager()
    
    # 总是添加控制台告警
    manager.add_channel(ConsoleChannel())
    
    # 从配置加载钉钉
    dingtalk_config = config.get('alert', {}).get('dingtalk', {})
    if dingtalk_config.get('webhook_url'):
        manager.add_channel(DingTalkChannel(
            webhook_url=dingtalk_config['webhook_url'],
            secret=dingtalk_config.get('secret')
        ))
    
    # 从配置加载邮件
    email_config = config.get('alert', {}).get('email', {})
    if email_config.get('smtp_server'):
        manager.add_channel(EmailChannel(
            smtp_server=email_config['smtp_server'],
            smtp_port=email_config.get('smtp_port', 465),
            sender=email_config['sender'],
            password=email_config['password'],
            receivers=email_config.get('receivers', []),
            use_ssl=email_config.get('use_ssl', True)
        ))
    
    return manager

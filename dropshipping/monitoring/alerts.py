"""
알림 시스템
오류 및 중요 이벤트 알림
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from collections import defaultdict
import json

import httpx
from loguru import logger as loguru_logger

from dropshipping.config import settings


class AlertLevel(str, Enum):
    """알림 레벨"""
    
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    """알림 채널"""
    
    LOG = "log"
    SLACK = "slack"
    EMAIL = "email"
    WEBHOOK = "webhook"


class Alert:
    """알림 객체"""
    
    def __init__(
        self,
        title: str,
        message: str,
        level: AlertLevel,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None
    ):
        self.id = f"{datetime.now().timestamp()}_{source}"
        self.title = title
        self.message = message
        self.level = level
        self.source = source
        self.metadata = metadata or {}
        self.error = error
        self.timestamp = datetime.now()
        self.sent_channels: List[AlertChannel] = []
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "level": self.level.value,
            "source": self.source,
            "metadata": self.metadata,
            "error": str(self.error) if self.error else None,
            "timestamp": self.timestamp.isoformat(),
            "sent_channels": [ch.value for ch in self.sent_channels]
        }


class AlertRule:
    """알림 규칙"""
    
    def __init__(
        self,
        name: str,
        condition: Callable[[Alert], bool],
        channels: List[AlertChannel],
        cooldown_minutes: int = 5
    ):
        self.name = name
        self.condition = condition
        self.channels = channels
        self.cooldown_minutes = cooldown_minutes
        self.last_sent: Dict[str, datetime] = {}
    
    def should_send(self, alert: Alert) -> bool:
        """알림 전송 여부 결정"""
        if not self.condition(alert):
            return False
        
        # 쿨다운 확인
        key = f"{alert.source}:{alert.title}"
        if key in self.last_sent:
            time_since_last = datetime.now() - self.last_sent[key]
            if time_since_last < timedelta(minutes=self.cooldown_minutes):
                return False
        
        return True
    
    def mark_sent(self, alert: Alert):
        """전송 완료 표시"""
        key = f"{alert.source}:{alert.title}"
        self.last_sent[key] = datetime.now()


class AlertManager:
    """알림 관리자"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.rules: List[AlertRule] = []
        self.alert_history: List[Alert] = []
        self.channels: Dict[AlertChannel, Callable] = {}
        
        # 기본 채널 설정
        self._setup_channels()
        
        # 기본 규칙 설정
        self._setup_default_rules()
        
        # 알림 큐
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task = None
    
    def _setup_channels(self):
        """채널 설정"""
        # 로그 채널 (항상 활성화)
        self.channels[AlertChannel.LOG] = self._send_to_log
        
        # Slack 채널
        if settings.monitoring.slack_webhook_url:
            self.channels[AlertChannel.SLACK] = self._send_to_slack
        
        # 이메일 채널 (설정 시)
        if self.config.get("email_enabled"):
            self.channels[AlertChannel.EMAIL] = self._send_to_email
        
        # 웹훅 채널 (설정 시)
        if self.config.get("webhook_url"):
            self.channels[AlertChannel.WEBHOOK] = self._send_to_webhook
    
    def _setup_default_rules(self):
        """기본 규칙 설정"""
        # 모든 CRITICAL 알림은 모든 채널로
        self.add_rule(
            "critical_alerts",
            lambda alert: alert.level == AlertLevel.CRITICAL,
            list(self.channels.keys()),
            cooldown_minutes=1
        )
        
        # ERROR 알림은 로그와 Slack으로
        self.add_rule(
            "error_alerts",
            lambda alert: alert.level == AlertLevel.ERROR,
            [AlertChannel.LOG, AlertChannel.SLACK],
            cooldown_minutes=5
        )
        
        # WARNING 알림은 로그로만
        self.add_rule(
            "warning_alerts",
            lambda alert: alert.level == AlertLevel.WARNING,
            [AlertChannel.LOG],
            cooldown_minutes=10
        )
        
        # 특정 소스의 알림 규칙
        self.add_rule(
            "api_errors",
            lambda alert: alert.source.startswith("api.") and alert.level >= AlertLevel.ERROR,
            [AlertChannel.LOG, AlertChannel.SLACK],
            cooldown_minutes=5
        )
        
        self.add_rule(
            "order_alerts",
            lambda alert: alert.source.startswith("order."),
            [AlertChannel.LOG, AlertChannel.SLACK],
            cooldown_minutes=3
        )
    
    def add_rule(
        self,
        name: str,
        condition: Callable[[Alert], bool],
        channels: List[AlertChannel],
        cooldown_minutes: int = 5
    ):
        """규칙 추가"""
        rule = AlertRule(name, condition, channels, cooldown_minutes)
        self.rules.append(rule)
        loguru_logger.info(f"알림 규칙 추가: {name}")
    
    async def send(
        self,
        title: str,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None
    ):
        """알림 전송"""
        alert = Alert(title, message, level, source, metadata, error)
        
        # 이력 저장
        self.alert_history.append(alert)
        
        # 큐에 추가
        await self._queue.put(alert)
    
    def send_sync(
        self,
        title: str,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None
    ):
        """동기 알림 전송"""
        asyncio.create_task(
            self.send(title, message, level, source, metadata, error)
        )
    
    async def _process_alerts(self):
        """알림 처리 루프"""
        while self._running:
            try:
                # 타임아웃으로 큐에서 가져오기
                alert = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                # 규칙에 따라 전송
                for rule in self.rules:
                    if rule.should_send(alert):
                        await self._send_to_channels(alert, rule.channels)
                        rule.mark_sent(alert)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                loguru_logger.error(f"알림 처리 오류: {str(e)}")
    
    async def _send_to_channels(self, alert: Alert, channels: List[AlertChannel]):
        """채널로 전송"""
        tasks = []
        
        for channel in channels:
            if channel in self.channels and channel not in alert.sent_channels:
                sender = self.channels[channel]
                tasks.append(sender(alert))
                alert.sent_channels.append(channel)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_to_log(self, alert: Alert):
        """로그로 전송"""
        level_map = {
            AlertLevel.INFO: loguru_logger.info,
            AlertLevel.WARNING: loguru_logger.warning,
            AlertLevel.ERROR: loguru_logger.error,
            AlertLevel.CRITICAL: loguru_logger.critical
        }
        
        log_func = level_map.get(alert.level, loguru_logger.info)
        log_func(
            f"[{alert.source}] {alert.title}: {alert.message}",
            extra={"alert": alert.to_dict()}
        )
    
    async def _send_to_slack(self, alert: Alert):
        """Slack으로 전송"""
        if not settings.monitoring.slack_webhook_url:
            return
        
        # 이모지 매핑
        emoji_map = {
            AlertLevel.INFO: ":information_source:",
            AlertLevel.WARNING: ":warning:",
            AlertLevel.ERROR: ":x:",
            AlertLevel.CRITICAL: ":rotating_light:"
        }
        
        # 색상 매핑
        color_map = {
            AlertLevel.INFO: "#36a64f",
            AlertLevel.WARNING: "#ff9800",
            AlertLevel.ERROR: "#f44336",
            AlertLevel.CRITICAL: "#d32f2f"
        }
        
        # Slack 메시지 구성
        payload = {
            "attachments": [{
                "color": color_map.get(alert.level, "#36a64f"),
                "title": f"{emoji_map.get(alert.level, '')} {alert.title}",
                "text": alert.message,
                "fields": [
                    {"title": "Source", "value": alert.source, "short": True},
                    {"title": "Level", "value": alert.level.value, "short": True},
                    {"title": "Time", "value": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"), "short": True}
                ],
                "footer": "Dropshipping Alert System",
                "ts": int(alert.timestamp.timestamp())
            }]
        }
        
        # 메타데이터 추가
        if alert.metadata:
            for key, value in alert.metadata.items():
                payload["attachments"][0]["fields"].append({
                    "title": key,
                    "value": str(value),
                    "short": True
                })
        
        # 에러 정보 추가
        if alert.error:
            payload["attachments"][0]["fields"].append({
                "title": "Error",
                "value": f"```{str(alert.error)}```",
                "short": False
            })
        
        # 전송
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.monitoring.slack_webhook_url,
                    json=payload,
                    timeout=10
                )
                response.raise_for_status()
                
        except Exception as e:
            loguru_logger.error(f"Slack 알림 전송 실패: {str(e)}")
    
    async def _send_to_email(self, alert: Alert):
        """이메일로 전송"""
        # TODO: 이메일 전송 구현
        loguru_logger.info(f"이메일 알림: {alert.title}")
    
    async def _send_to_webhook(self, alert: Alert):
        """웹훅으로 전송"""
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            return
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=alert.to_dict(),
                    timeout=10
                )
                response.raise_for_status()
                
        except Exception as e:
            loguru_logger.error(f"웹훅 알림 전송 실패: {str(e)}")
    
    def start(self):
        """알림 매니저 시작"""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._process_alerts())
            loguru_logger.info("알림 매니저 시작됨")
    
    async def stop(self):
        """알림 매니저 중지"""
        if self._running:
            self._running = False
            if self._task:
                await self._task
            loguru_logger.info("알림 매니저 중지됨")
    
    def get_alert_history(
        self,
        level: Optional[AlertLevel] = None,
        source: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Alert]:
        """알림 이력 조회"""
        filtered = self.alert_history
        
        if level:
            filtered = [a for a in filtered if a.level == level]
        
        if source:
            filtered = [a for a in filtered if a.source.startswith(source)]
        
        if since:
            filtered = [a for a in filtered if a.timestamp >= since]
        
        # 최신순 정렬
        filtered.sort(key=lambda a: a.timestamp, reverse=True)
        
        return filtered[:limit]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """알림 요약"""
        now = datetime.now()
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)
        
        # 레벨별 카운트
        level_counts = defaultdict(int)
        source_counts = defaultdict(int)
        
        for alert in self.alert_history:
            level_counts[alert.level.value] += 1
            source_counts[alert.source] += 1
        
        # 시간별 카운트
        hour_alerts = [a for a in self.alert_history if a.timestamp >= last_hour]
        day_alerts = [a for a in self.alert_history if a.timestamp >= last_day]
        
        return {
            "total_alerts": len(self.alert_history),
            "last_hour": len(hour_alerts),
            "last_day": len(day_alerts),
            "by_level": dict(level_counts),
            "by_source": dict(source_counts),
            "recent_alerts": [a.to_dict() for a in self.get_alert_history(limit=10)]
        }


# 전역 알림 매니저
alert_manager = AlertManager()
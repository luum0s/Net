"""
Sentinel Agent - 感知Agent
职责: 多源告警聚合、事件降噪、初始定级
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, List
from datetime import datetime
from core.bus import bus, Event, EventType
from core.state_machine import state_manager, HealingState

logger = logging.getLogger(__name__)

class SentinelAgent:
    """感知Agent: 网络监控的前哨"""

    def __init__(self):
        self.name = "Sentinel"
        self._alert_buffer: List[Dict[str, Any]] = []
        self._buffer_window = 300  # 5分钟聚合窗口

    async def on_alert(self, raw_alert: Dict[str, Any]):
        """接收原始告警入口"""
        correlation_id = str(uuid.uuid4())[:8]

        # 1. 告警标准化
        normalized = self._normalize(raw_alert)
        normalized["correlation_id"] = correlation_id

        # 2. 聚合降噪
        similar = self._find_similar(normalized)
        if similar:
            logger.info(f"[{self.name}] 告警聚合: {correlation_id} 合并到现有事件")
            return  # 合并到已有事件

        # 3. 严重度定级
        severity = self._classify_severity(normalized)
        normalized["severity"] = severity

        # 4. 创建自愈上下文
        ctx = state_manager.create(correlation_id, normalized)

        # 5. 发布事件到总线
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ALERT,
            source=self.name,
            payload={
                "summary": f"[{severity}] {normalized.get('title', 'Unknown')}",
                "alert": normalized,
                "scope": normalized.get("affected_ips", [])
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )

        await bus.publish(event)

        # 6. 如果是P1/P2，立即触发诊断
        if severity in ["P1", "P2"]:
            await asyncio.sleep(0.5)  # 短暂等待确保上下文就绪
            await self._trigger_diagnosis(correlation_id, normalized)

    def _normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """标准化不同来源的告警格式"""
        return {
            "title": raw.get("alertname", raw.get("title", "Unknown Alert")),
            "source_system": raw.get("source", "zabbix"),
            "device": raw.get("device", "unknown"),
            "affected_ips": raw.get("ips", []),
            "metric": raw.get("metric", ""),
            "threshold": raw.get("threshold", ""),
            "current_value": raw.get("value", ""),
            "raw_data": raw
        }

    def _find_similar(self, alert: Dict[str, Any]) -> bool:
        """查找相似告警进行聚合（简化版）"""
        # MVP: 简单基于IP和指标名聚合
        return False  # 暂不实现复杂聚合

    def _classify_severity(self, alert: Dict[str, Any]) -> str:
        """严重度定级规则"""
        title = alert.get("title", "").lower()

        if any(k in title for k in ["down", "unreachable", "loop", "storm"]):
            return "P1"
        if any(k in title for k in ["high latency", "packet loss", "bgp flap"]):
            return "P2"
        if any(k in title for k in ["warning", "threshold"]):
            return "P3"
        return "P4"

    async def _trigger_diagnosis(self, correlation_id: str, alert: Dict[str, Any]):
        """触发诊断阶段"""
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.DIAGNOSIS_START,
            source=self.name,
            payload={
                "summary": f"触发诊断流程",
                "target_device": alert.get("device"),
                "initial_symptom": alert.get("title")
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(event)
        logger.info(f"[{self.name}] 已触发诊断: {correlation_id}")

# 全局实例
sentinel = SentinelAgent()

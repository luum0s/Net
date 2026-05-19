"""
NetHealer Message Bus
支持Agent间异步通信，MVP使用内存队列，生产环境可替换为Kafka
"""
import asyncio
import json
import logging
from typing import Dict, List, Callable, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class EventType(Enum):
    ALERT = "alert"
    DIAGNOSIS_START = "diagnosis_start"
    DIAGNOSIS_RESULT = "diagnosis_result"
    DECISION = "decision"
    EXECUTION_START = "execution_start"
    EXECUTION_RESULT = "execution_result"
    VALIDATION_START = "validation_start"
    VALIDATION_RESULT = "validation_result"
    ROLLBACK = "rollback"
    HUMAN_ESCALATION = "human_escalation"
    CLOSED = "closed"

@dataclass
class Event:
    event_id: str
    event_type: EventType
    source: str  # Agent名称
    payload: Dict[str, Any]
    timestamp: str
    correlation_id: str  # 关联同一故障的ID

    def to_json(self) -> str:
        data = asdict(self)
        data['event_type'] = self.event_type.value
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        data = json.loads(json_str)
        data['event_type'] = EventType(data['event_type'])
        return cls(**data)

class MessageBus:
    """内存消息总线，模拟Kafka Topic"""

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._history: List[Event] = []
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, callback: Callable):
        """订阅特定事件类型"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.info(f"订阅者注册: {event_type.value}")

    async def publish(self, event: Event):
        """发布事件到总线"""
        async with self._lock:
            self._history.append(event)

        logger.info(f"[总线] {event.source} -> {event.event_type.value} | {event.correlation_id}")

        # 异步分发
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(event))
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"事件分发失败: {e}")

    def get_history(self, correlation_id: str = None) -> List[Event]:
        """获取事件历史，支持按correlation_id过滤"""
        if correlation_id:
            return [e for e in self._history if e.correlation_id == correlation_id]
        return self._history.copy()

    def get_chain_of_thought(self, correlation_id: str) -> str:
        """获取指定故障的完整思维链（用于审计）"""
        events = self.get_history(correlation_id)
        lines = []
        for e in events:
            ts = e.timestamp.split('T')[1][:8]
            lines.append(f"[{ts}] {e.source}: {e.event_type.value}")
            if 'summary' in e.payload:
                lines.append(f"       └─ {e.payload['summary']}")
        return "\n".join(lines)

# 全局总线实例
bus = MessageBus()

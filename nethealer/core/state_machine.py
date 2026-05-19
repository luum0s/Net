"""
自愈状态机 - 管理故障从发现到闭环的完整生命周期
"""
from enum import Enum, auto
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class HealingState(Enum):
    IDLE = "idle"
    DETECTED = "detected"           # 感知Agent已发现
    DIAGNOSING = "diagnosing"       # 诊断Agent工作中
    DIAGNOSED = "diagnosed"         # 诊断完成
    DECIDING = "deciding"           # 决策Agent评估中
    DECIDED = "decided"             # 决策完成
    EXECUTING = "executing"         # 执行Agent下发中
    EXECUTED = "executed"           # 执行完成
    VALIDATING = "validating"     # 验证Agent确认中
    VALIDATED = "validated"         # 验证通过，闭环
    ROLLING_BACK = "rolling_back"   # 回滚中
    ROLLED_BACK = "rolled_back"     # 回滚完成
    ESCALATED = "escalated"         # 升级人工
    CLOSED = "closed"               # 最终关闭

@dataclass
class HealingContext:
    """自愈上下文，贯穿整个长链推理"""
    correlation_id: str
    state: HealingState = HealingState.IDLE

    # 感知阶段数据
    alert_data: Dict[str, Any] = field(default_factory=dict)
    severity: str = "P3"

    # 诊断阶段数据（长链推理结果）
    diagnosis_report: Dict[str, Any] = field(default_factory=dict)
    root_cause: str = ""
    affected_devices: list = field(default_factory=list)
    affected_scope: str = ""

    # 决策阶段数据
    selected_action: str = ""
    risk_level: str = "low"
    rollback_plan: str = ""
    human_required: bool = False

    # 执行阶段数据
    execution_log: list = field(default_factory=list)
    config_snapshot: str = ""

    # 验证阶段数据
    validation_result: bool = False
    validation_metrics: Dict[str, Any] = field(default_factory=dict)

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 审计
    state_history: list = field(default_factory=list)

    def transition(self, new_state: HealingState, reason: str = ""):
        """状态转移并记录"""
        old_state = self.state
        self.state = new_state
        self.updated_at = datetime.now().isoformat()
        self.state_history.append({
            "from": old_state.value,
            "to": new_state.value,
            "at": self.updated_at,
            "reason": reason
        })
        logger.info(f"[状态机] {self.correlation_id}: {old_state.value} -> {new_state.value} | {reason}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "state": self.state.value,
            "severity": self.severity,
            "root_cause": self.root_cause,
            "selected_action": self.selected_action,
            "risk_level": self.risk_level,
            "human_required": self.human_required,
            "validation_result": self.validation_result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state_history": self.state_history
        }

class StateMachineManager:
    """状态机管理器 - 管理所有进行中的自愈流程"""

    def __init__(self):
        self._contexts: Dict[str, HealingContext] = {}

    def create(self, correlation_id: str, alert_data: Dict[str, Any]) -> HealingContext:
        """创建新的自愈上下文"""
        ctx = HealingContext(correlation_id=correlation_id, alert_data=alert_data)
        ctx.transition(HealingState.DETECTED, "告警触发")
        self._contexts[correlation_id] = ctx
        return ctx

    def get(self, correlation_id: str) -> Optional[HealingContext]:
        return self._contexts.get(correlation_id)

    def transition(self, correlation_id: str, new_state: HealingState, reason: str = ""):
        """推动状态转移"""
        ctx = self._contexts.get(correlation_id)
        if not ctx:
            raise ValueError(f"未知流程: {correlation_id}")
        ctx.transition(new_state, reason)

        # 如果到达终态，可选归档
        if new_state in [HealingState.VALIDATED, HealingState.ROLLED_BACK, 
                        HealingState.ESCALATED, HealingState.CLOSED]:
            logger.info(f"[状态机] 流程 {correlation_id} 到达终态: {new_state.value}")

    def get_active_count(self) -> int:
        """获取活跃流程数"""
        terminal = {HealingState.VALIDATED, HealingState.ROLLED_BACK, 
                   HealingState.ESCALATED, HealingState.CLOSED}
        return sum(1 for ctx in self._contexts.values() if ctx.state not in terminal)

    def list_active(self) -> list:
        """列出所有活跃流程"""
        terminal = {HealingState.VALIDATED, HealingState.ROLLED_BACK, 
                   HealingState.ESCALATED, HealingState.CLOSED}
        return [ctx.to_dict() for ctx in self._contexts.values() if ctx.state not in terminal]

# 全局状态机管理器
state_manager = StateMachineManager()

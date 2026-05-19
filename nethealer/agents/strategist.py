"""
Strategist Agent - 决策Agent
职责: 风险评估、方案排序、回滚策略生成、人工升级判断
核心难点: 网络变更的"双锁机制"（规则引擎校验 + 风险分级）
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, List
from datetime import datetime
from core.bus import bus, Event, EventType
from core.state_machine import state_manager, HealingState

logger = logging.getLogger(__name__)

class StrategistAgent:
    """决策Agent: 自愈方案的智能裁决者"""

    def __init__(self):
        self.name = "Strategist"
        self._risk_rules = {
            "single_port": "low",
            "single_peer": "medium", 
            "subnet": "high",
            "core_link": "high",
            "multi_device": "high"
        }

    async def on_diagnosis_result(self, event: Event):
        """接收诊断结果，进行决策"""
        correlation_id = event.correlation_id
        ctx = state_manager.get(correlation_id)
        if not ctx:
            return

        ctx.transition(HealingState.DECIDING, "开始风险评估与方案决策")

        diagnosis = event.payload
        root_cause = diagnosis.get("root_cause", "")
        affected_scope = diagnosis.get("affected_scope", "unknown")
        recommended_actions = diagnosis.get("recommended_actions", [])

        logger.info(f"[{self.name}] ====== 开始决策 [{correlation_id}] ======")

        # Step 1: 风险评估
        risk_level = self._assess_risk(affected_scope, ctx)

        # Step 2: 方案生成与排序
        candidates = self._generate_candidates(recommended_actions, root_cause, ctx)

        # Step 3: 选择最优方案
        selected = self._select_best(candidates, risk_level)

        # Step 4: 生成回滚计划
        rollback_plan = self._generate_rollback(selected, ctx)

        # Step 5: 人工升级判断（双锁机制）
        human_required = self._need_human_confirm(risk_level, ctx)

        # 更新上下文
        ctx.selected_action = selected.get("action", "none")
        ctx.risk_level = risk_level
        ctx.rollback_plan = rollback_plan
        ctx.human_required = human_required
        ctx.transition(HealingState.DECIDED, f"选择方案: {selected.get('name')}, 风险: {risk_level}")

        # 发布决策事件
        decision_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.DECISION,
            source=self.name,
            payload={
                "summary": f"决策: {selected.get('name')} | 风险: {risk_level} | 人工: {human_required}",
                "selected_action": selected,
                "risk_level": risk_level,
                "rollback_plan": rollback_plan,
                "human_required": human_required,
                "reason": selected.get("reason", "")
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(decision_event)
        logger.info(f"[{self.name}] ====== 决策完成 [{correlation_id}] ======")

    def _assess_risk(self, scope: str, ctx) -> str:
        """基于影响面评估风险等级"""
        base_risk = self._risk_rules.get(scope, "medium")

        # 叠加因子
        if ctx.severity == "P1":
            # P1故障但如果是单端口，可以自动处理
            pass

        # 业务时段检查（MVP简化）
        hour = datetime.now().hour
        if 9 <= hour <= 18:  # 工作时间
            if base_risk == "medium":
                return "high"  # 工作时间升级风险

        return base_risk

    def _generate_candidates(self, actions: List[str], root_cause: str, ctx) -> List[Dict[str, Any]]:
        """生成候选方案"""
        candidates = []

        for action in actions:
            if action == "shutdown_interface":
                candidates.append({
                    "id": "CAND-001",
                    "name": "隔离异常端口",
                    "action": "shutdown_interface",
                    "target": "Gi0/0/24",
                    "risk": "low",
                    "estimated_downtime": 0,
                    "reason": "直接消除环路源，影响面最小"
                })
            elif action == "activate_backup_route":
                candidates.append({
                    "id": "CAND-002", 
                    "name": "切换备用路由",
                    "action": "activate_backup_route",
                    "target": "bgp_peer_backup",
                    "risk": "medium",
                    "estimated_downtime": 30,
                    "reason": "保障业务连续性"
                })
            elif action == "notify_admin":
                candidates.append({
                    "id": "CAND-003",
                    "name": "仅通知人工处理",
                    "action": "notify_admin",
                    "target": "",
                    "risk": "low",
                    "estimated_downtime": -1,  # 未知
                    "reason": "高风险操作，需人工确认"
                })

        # 如果没有候选，默认人工介入
        if not candidates:
            candidates.append({
                "id": "CAND-000",
                "name": "人工介入排查",
                "action": "human_escalation",
                "target": "",
                "risk": "high",
                "estimated_downtime": -1,
                "reason": "无法自动生成安全修复方案"
            })

        return candidates

    def _select_best(self, candidates: List[Dict[str, Any]], risk_level: str) -> Dict[str, Any]:
        """选择最优方案：优先低风险、高确定性的方案"""
        # 排序: 风险低 -> 停机时间短 -> 确定性高
        sorted_cands = sorted(candidates, 
                             key=lambda x: (x["risk"] != "low", x.get("estimated_downtime", 999)))
        return sorted_cands[0]

    def _generate_rollback(self, selected: Dict[str, Any], ctx) -> str:
        """生成回滚计划"""
        action = selected.get("action", "")
        target = selected.get("target", "")

        if action == "shutdown_interface":
            return f"interface {target}\nundo shutdown  # 恢复端口"
        if action == "activate_backup_route":
            return f"deactivate backup route {target}  # 回切主路由"
        return "manual_rollback  # 需人工执行回滚"

    def _need_human_confirm(self, risk_level: str, ctx) -> bool:
        """双锁机制：判断是否需要人工确认"""
        if risk_level == "high":
            return True
        if ctx.severity == "P1" and risk_level == "medium":
            return True  # P1+中风险也需要人工
        return False

# 全局实例
strategist = StrategistAgent()

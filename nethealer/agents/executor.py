"""
Executor Agent - 执行Agent
职责: 通过设备抽象层下发原子化指令，配置快照，日志留痕
"""
import asyncio
import logging
import uuid
from typing import Dict, Any
from datetime import datetime
from core.bus import bus, Event, EventType
from core.state_machine import state_manager, HealingState
from core.device_abstraction import DeviceConnector, CommandTranslator, DeviceInfo, VendorType

logger = logging.getLogger(__name__)

class ExecutorAgent:
    """执行Agent: 精准、原子、可回滚的操作执行器"""

    def __init__(self):
        self.name = "Executor"

    async def on_decision(self, event: Event):
        """接收决策事件，执行修复"""
        correlation_id = event.correlation_id
        ctx = state_manager.get(correlation_id)
        if not ctx:
            return

        decision = event.payload
        human_required = decision.get("human_required", True)

        # 如果需要人工确认，直接升级
        if human_required:
            ctx.transition(HealingState.ESCALATED, "需人工确认，暂停自动执行")
            await self._escalate_human(correlation_id, ctx, decision)
            return

        ctx.transition(HealingState.EXECUTING, "开始自动执行修复")

        selected = decision.get("selected_action", {})
        action = selected.get("action", "")
        target = selected.get("target", "")

        logger.info(f"[{self.name}] ====== 开始执行 [{correlation_id}] ======")
        logger.info(f"[{self.name}] 执行操作: {action} -> {target}")

        # Step 1: 配置快照（MVP简化）
        snapshot = await self._take_snapshot(target, ctx)
        ctx.config_snapshot = snapshot

        # Step 2: 执行操作
        execution_log = []
        success = False

        try:
            if action == "shutdown_interface":
                success = await self._execute_shutdown(target, ctx, execution_log)
            elif action == "activate_backup_route":
                success = await self._execute_route_switch(target, ctx, execution_log)
            elif action == "human_escalation":
                success = False  # 不执行，直接升级
            else:
                logger.warning(f"[{self.name}] 未知操作: {action}")
                success = False

        except Exception as e:
            logger.error(f"[{self.name}] 执行异常: {e}")
            execution_log.append({"error": str(e)})
            success = False

        # Step 3: 更新上下文
        ctx.execution_log = execution_log

        if success:
            ctx.transition(HealingState.EXECUTED, "修复指令下发成功")
            # 触发验证
            await self._trigger_validation(correlation_id, ctx)
        else:
            ctx.transition(HealingState.ESCALATED, "执行失败，升级人工")
            await self._escalate_human(correlation_id, ctx, decision, reason="执行失败")

        logger.info(f"[{self.name}] ====== 执行完成 [{correlation_id}] ======")

    async def _take_snapshot(self, target: str, ctx) -> str:
        """执行前配置快照"""
        # MVP: 记录当前状态描述
        return f"SNAPSHOT-{ctx.correlation_id}-BEFORE-{target}"

    async def _execute_shutdown(self, interface: str, ctx, log: list) -> bool:
        """执行端口关闭"""
        device = DeviceInfo(
            name="core-sw-01",
            vendor=VendorType.HUAWEI,
            ip="192.168.1.1",
            device_type="switch",
            protocol="ssh",
            username="admin",
            password="admin"
        )

        connector = DeviceConnector(device)
        await connector.connect()

        try:
            # 进入系统视图
            log.append({"cmd": "system-view", "result": "entered"})

            # 关闭接口
            cmd = CommandTranslator.translate("shutdown_interface", device.vendor, iface=interface)
            output = await connector.execute(cmd)
            log.append({"cmd": cmd, "result": "executed", "output": output[:100]})

            # 保存配置
            save_cmd = CommandTranslator.translate("save_config", device.vendor)
            save_out = await connector.execute(save_cmd)
            log.append({"cmd": save_cmd, "result": "saved"})

            return True
        finally:
            await connector.disconnect()

    async def _execute_route_switch(self, target: str, ctx, log: list) -> bool:
        """执行路由切换（MVP简化）"""
        log.append({"action": "route_switch", "target": target, "status": "simulated"})
        return True  # MVP模拟成功

    async def _trigger_validation(self, correlation_id: str, ctx):
        """触发验证阶段"""
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.VALIDATION_START,
            source=self.name,
            payload={
                "summary": "触发修复验证",
                "validation_targets": ctx.alert_data.get("affected_ips", [])
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(event)

    async def _escalate_human(self, correlation_id: str, ctx, decision: Dict, reason: str = "人工确认"):
        """升级人工处理"""
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.HUMAN_ESCALATION,
            source=self.name,
            payload={
                "summary": f"升级人工: {reason}",
                "decision": decision,
                "context": ctx.to_dict()
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(event)

# 全局实例
executor = ExecutorAgent()

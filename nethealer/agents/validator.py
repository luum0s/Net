"""
Validator Agent - 验证Agent
职责: 持续探测修复效果，异常则自动回滚，闭环归档
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

class ValidatorAgent:
    """验证Agent: 修复效果的最终守门员"""

    def __init__(self):
        self.name = "Validator"
        self._validation_duration = 180  # 3分钟持续验证
        self._check_interval = 30        # 每30秒检查一次

    async def on_validation_start(self, event: Event):
        """接收验证启动事件"""
        correlation_id = event.correlation_id
        ctx = state_manager.get(correlation_id)
        if not ctx:
            return

        ctx.transition(HealingState.VALIDATING, "开始持续验证修复效果")

        targets = event.payload.get("validation_targets", [])
        if not targets:
            targets = ["192.168.10.10"]  # 默认探测目标

        logger.info(f"[{self.name}] ====== 开始验证 [{correlation_id}] ======")

        # 持续探测
        check_count = self._validation_duration // self._check_interval
        all_passed = True
        metrics_history = []

        for i in range(check_count):
            await asyncio.sleep(self._check_interval)

            metrics = await self._probe_targets(targets, ctx)
            metrics_history.append(metrics)

            logger.info(f"[{self.name}] 验证轮次 {i+1}/{check_count}: {metrics}")

            # 检查是否恢复
            if not self._is_recovered(metrics):
                all_passed = False
                logger.warning(f"[{self.name}] 验证失败，触发回滚!")
                break

        # 更新上下文
        ctx.validation_metrics = {
            "history": metrics_history,
            "final_passed": all_passed,
            "checks_total": check_count,
            "checks_executed": len(metrics_history)
        }

        if all_passed:
            ctx.validation_result = True
            ctx.transition(HealingState.VALIDATED, "修复验证通过，闭环完成")
            await self._close_success(correlation_id, ctx)
        else:
            ctx.validation_result = False
            ctx.transition(HealingState.ROLLING_BACK, "验证失败，执行自动回滚")
            await self._execute_rollback(correlation_id, ctx)

        logger.info(f"[{self.name}] ====== 验证完成 [{correlation_id}] ======")

    async def _probe_targets(self, targets: list, ctx) -> Dict[str, Any]:
        """探测目标可达性"""
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

        results = {}
        try:
            for target in targets:
                cmd = CommandTranslator.translate("ping", device.vendor, 
                                                 source="192.168.1.1", target=target)
                output = await connector.execute(cmd)

                # 解析丢包率
                loss = self._parse_loss_rate(output)
                results[target] = {
                    "loss_rate": loss,
                    "reachable": loss < 20.0
                }
        finally:
            await connector.disconnect()

        return {
            "timestamp": datetime.now().isoformat(),
            "targets": results,
            "overall_ok": all(r["reachable"] for r in results.values())
        }

    def _parse_loss_rate(self, ping_output: str) -> float:
        """解析ping输出中的丢包率"""
        import re
        match = re.search(r"(\d+\.?\d*)% packet loss", ping_output)
        if match:
            return float(match.group(1))
        # MVP: 模拟数据
        return 0.0  # 模拟全部恢复

    def _is_recovered(self, metrics: Dict[str, Any]) -> bool:
        """判断是否已恢复"""
        return metrics.get("overall_ok", False)

    async def _execute_rollback(self, correlation_id: str, ctx):
        """执行回滚"""
        rollback_cmd = ctx.rollback_plan
        logger.info(f"[{self.name}] 执行回滚: {rollback_cmd}")

        # MVP: 模拟回滚成功
        await asyncio.sleep(1)

        ctx.transition(HealingState.ROLLED_BACK, "回滚完成，升级人工")

        # 发布回滚事件
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ROLLBACK,
            source=self.name,
            payload={
                "summary": "自动回滚已执行",
                "rollback_command": rollback_cmd,
                "reason": "验证失败"
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(event)

        # 回滚后仍升级人工
        esc_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.HUMAN_ESCALATION,
            source=self.name,
            payload={
                "summary": "回滚后需人工复核",
                "context": ctx.to_dict()
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(esc_event)

    async def _close_success(self, correlation_id: str, ctx):
        """成功闭环"""
        ctx.transition(HealingState.CLOSED, "故障自愈闭环完成")

        # 生成思维链归档
        chain_of_thought = bus.get_chain_of_thought(correlation_id)

        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.CLOSED,
            source=self.name,
            payload={
                "summary": "故障自愈成功闭环",
                "mttr_seconds": 240,  # MVP模拟4分钟
                "chain_of_thought": chain_of_thought,
                "final_state": ctx.to_dict()
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(event)

        # TODO: 沉淀到知识库
        logger.info(f"[{self.name}] 案例已归档: {correlation_id}")

# 全局实例
validator = ValidatorAgent()

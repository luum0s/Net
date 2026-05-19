"""
Pathfinder Agent - 诊断Agent
职责: 长链推理逐层定位根因，每一步通过设备查询验证
核心难点: 跨厂商、跨协议栈的复杂故障定位
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from core.bus import bus, Event, EventType
from core.state_machine import state_manager, HealingState
from core.device_abstraction import DeviceConnector, CommandTranslator, DeviceInfo, VendorType

logger = logging.getLogger(__name__)

class PathfinderAgent:
    """诊断Agent: 长链推理的根因定位器"""

    def __init__(self):
        self.name = "Pathfinder"
        self._reasoning_chains = {
            "port_loop": ["show_interface_status", "show_mac_table", "show_stp", "show_port_security"],
            "connectivity": ["show_interface_status", "show_arp", "show_routing"],
            "bgp_issue": ["show_bgp_peer", "show_routing"],
        }

    async def on_diagnosis_start(self, event: Event):
        """接收诊断启动事件"""
        correlation_id = event.correlation_id
        ctx = state_manager.get(correlation_id)
        if not ctx:
            logger.error(f"[{self.name}] 找不到上下文: {correlation_id}")
            return

        ctx.transition(HealingState.DIAGNOSING, "开始长链推理诊断")

        # 获取告警信息
        alert = ctx.alert_data
        device_name = alert.get("device", "core-sw-01")
        symptom = alert.get("title", "")

        logger.info(f"[{self.name}] ====== 开始长链推理 [{correlation_id}] ======")

        # Step 1: 选择推理链
        chain = self._select_chain(symptom)

        # Step 2: 执行长链推理（每一步都查询真实设备）
        diagnosis_result = await self._execute_chain(device_name, chain, symptom, correlation_id)

        # Step 3: 分析影响面
        impact = self._analyze_impact(diagnosis_result)

        # Step 4: 更新上下文
        ctx.diagnosis_report = diagnosis_result
        ctx.root_cause = diagnosis_result.get("root_cause", "unknown")
        ctx.affected_devices = impact.get("devices", [])
        ctx.affected_scope = impact.get("scope", "unknown")
        ctx.transition(HealingState.DIAGNOSED, f"根因: {ctx.root_cause}")

        # Step 5: 发布诊断结果
        result_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.DIAGNOSIS_RESULT,
            source=self.name,
            payload={
                "summary": f"根因定位: {ctx.root_cause}",
                "root_cause": ctx.root_cause,
                "affected_scope": ctx.affected_scope,
                "reasoning_chain": diagnosis_result.get("chain_log", []),
                "recommended_actions": diagnosis_result.get("actions", [])
            },
            timestamp=datetime.now().isoformat(),
            correlation_id=correlation_id
        )
        await bus.publish(result_event)
        logger.info(f"[{self.name}] ====== 诊断完成 [{correlation_id}] ======")

    def _select_chain(self, symptom: str) -> List[str]:
        """根据症状选择推理链"""
        symptom_l = symptom.lower()
        if any(k in symptom_l for k in ["loop", "storm", "mac", "port"]):
            return self._reasoning_chains["port_loop"]
        if any(k in symptom_l for k in ["bgp", "peer", "route"]):
            return self._reasoning_chains["bgp_issue"]
        return self._reasoning_chains["connectivity"]

    async def _execute_chain(self, device_name: str, chain: List[str], 
                            symptom: str, correlation_id: str) -> Dict[str, Any]:
        """执行长链推理，每一步通过设备查询验证"""

        # MVP: 创建设备连接（使用模拟数据）
        device = DeviceInfo(
            name=device_name,
            vendor=VendorType.HUAWEI,
            ip="192.168.1.1",
            device_type="switch",
            protocol="ssh",
            username="admin",
            password="admin",
            critical=True
        )

        connector = DeviceConnector(device)
        await connector.connect()

        chain_log = []
        findings = {}
        root_cause = "unknown"
        actions = []

        try:
            for step_idx, action in enumerate(chain):
                # 翻译命令
                cmd = CommandTranslator.translate(action, device.vendor, iface="Gi0/0/24")

                # 执行查询（真实设备或模拟）
                raw_output = await connector.execute(cmd)

                # 解析输出
                parsed = CommandTranslator.parse_output(action, device.vendor, raw_output)

                step_result = {
                    "step": step_idx + 1,
                    "action": action,
                    "command": cmd,
                    "parsed": parsed,
                    "timestamp": datetime.now().isoformat()
                }
                chain_log.append(step_result)

                logger.info(f"[{self.name}] 推理步骤 {step_idx+1}: {action} -> {parsed}")

                # 长链推理逻辑：基于当前步骤结果决定下一步推理方向
                if action == "show_interface_status":
                    err_ports = [i for i in parsed.get("interfaces", []) 
                                if i.get("physical") == "err-disabled"]
                    if err_ports:
                        findings["err_ports"] = err_ports
                        root_cause = f"端口异常: {err_ports[0]['interface']} 处于err-disabled"
                        actions.append("shutdown_interface")
                    else:
                        findings["all_ports_normal"] = True

                elif action == "show_mac_table":
                    mac_count = parsed.get("count", 0)
                    findings["mac_count"] = mac_count
                    if mac_count > 50:
                        root_cause = "MAC地址表异常膨胀，疑似二层环路"
                        actions.append("shutdown_interface")

                elif action == "show_stp":
                    if parsed.get("has_loop_keywords"):
                        root_cause = "STP检测到环路，端口已被阻塞"
                        actions.append("shutdown_interface")
                        actions.append("notify_admin")

                elif action == "show_port_security":
                    # MVP简化
                    pass

                # 模拟推理延迟
                await asyncio.sleep(0.3)

        finally:
            await connector.disconnect()

        return {
            "chain_log": chain_log,
            "root_cause": root_cause,
            "findings": findings,
            "actions": actions,
            "device_queried": device_name,
            "steps_executed": len(chain_log)
        }

    def _analyze_impact(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """分析故障影响面"""
        findings = diagnosis.get("findings", {})

        if "err_ports" in findings:
            return {
                "devices": [diagnosis.get("device_queried")],
                "scope": "single_port",
                "affected_vlans": ["VLAN10"],
                "estimated_users": 50
            }

        if findings.get("mac_count", 0) > 50:
            return {
                "devices": [diagnosis.get("device_queried")],
                "scope": "switch_downlink",
                "affected_vlans": ["VLAN10", "VLAN20", "VLAN30"],
                "estimated_users": 200
            }

        return {
            "devices": [],
            "scope": "unknown",
            "affected_vlans": [],
            "estimated_users": 0
        }

# 全局实例
pathfinder = PathfinderAgent()

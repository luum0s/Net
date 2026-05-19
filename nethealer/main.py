#!/usr/bin/env python3
"""
NetHealer - 多Agent网络故障自愈中枢
主入口: 初始化总线、注册Agent、启动演示
"""
import asyncio
import logging
import sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/nethealer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NetHealer")

# 导入核心组件
from core.bus import bus, EventType
from core.state_machine import state_manager
from agents.sentinel import sentinel
from agents.pathfinder import pathfinder
from agents.strategist import strategist
from agents.executor import executor
from agents.validator import validator

console = Console()

def setup_agents():
    """注册所有Agent到消息总线"""
    console.print("[bold cyan]正在初始化 NetHealer Agent集群...[/bold cyan]")

    # Sentinel -> 监听外部告警入口（不通过总线，直接调用）
    # Pathfinder -> 监听诊断启动
    bus.subscribe(EventType.DIAGNOSIS_START, pathfinder.on_diagnosis_start)

    # Strategist -> 监听诊断结果
    bus.subscribe(EventType.DIAGNOSIS_RESULT, strategist.on_diagnosis_result)

    # Executor -> 监听决策
    bus.subscribe(EventType.DECISION, executor.on_decision)

    # Validator -> 监听验证启动
    bus.subscribe(EventType.VALIDATION_START, validator.on_validation_start)

    console.print("[green]✓[/green] Sentinel Agent (感知) 已就绪")
    console.print("[green]✓[/green] Pathfinder Agent (诊断) 已就绪")
    console.print("[green]✓[/green] Strategist Agent (决策) 已就绪")
    console.print("[green]✓[/green] Executor Agent (执行) 已就绪")
    console.print("[green]✓[/green] Validator Agent (验证) 已就绪")
    console.print("")

async def simulate_fault():
    """模拟一个网络故障并触发自愈流程"""
    console.print(Panel(
        "[bold yellow]模拟场景: 核心交换机下联区域出现二层环路[/bold yellow]\n"
        "症状: 192.168.10.0/24 网段批量丢包，Gi0/0/24端口err-disabled",
        title="故障注入",
        border_style="red"
    ))

    # 构造原始告警（模拟Zabbix/Prometheus格式）
    raw_alert = {
        "alertname": "Network_Port_Loop_Detected",
        "device": "core-sw-01",
        "ips": ["192.168.10.10", "192.168.10.11", "192.168.10.50"],
        "metric": "interface_status",
        "value": "err-disabled",
        "threshold": "up",
        "severity": "critical"
    }

    # 注入故障 -> Sentinel接收
    await sentinel.on_alert(raw_alert)

    # 等待整个长链推理完成（演示用，实际为异步事件驱动）
    await asyncio.sleep(8)

    # 输出结果
    print_results()

def print_results():
    """打印自愈结果"""
    console.print("\n[bold cyan]=== 自愈执行报告 ===[/bold cyan]")

    active = state_manager.list_active()
    if not active:
        # 查找已完成的
        console.print("[yellow]所有流程已处理完毕[/yellow]")

    # 显示思维链
    for ctx_data in active:
        cid = ctx_data["correlation_id"]

        table = Table(title=f"故障ID: {cid}", box=box.ROUNDED)
        table.add_column("阶段", style="cyan")
        table.add_column("状态", style="green")
        table.add_column("详情", style="white")

        table.add_row("严重度", ctx_data["severity"], "")
        table.add_row("根因", ctx_data["root_cause"], "")
        table.add_row("修复动作", ctx_data["selected_action"], "")
        table.add_row("风险等级", ctx_data["risk_level"], "")
        table.add_row("需人工", str(ctx_data["human_required"]), "")
        table.add_row("验证结果", str(ctx_data["validation_result"]), "")

        console.print(table)

        # 打印思维链
        cot = bus.get_chain_of_thought(cid)
        if cot:
            console.print(Panel(cot, title="完整思维链 (Chain-of-Thought)", border_style="blue"))

    console.print("\n[bold green]演示完成! 查看 logs/nethealer.log 获取详细日志[/bold green]")

async def main():
    """主函数"""
    console.print(Panel(
        "[bold]NetHealer v0.1 - 多Agent网络故障自愈中枢[/bold]\n"
        "架构: 感知→诊断→决策→执行→验证 闭环长链推理",
        title="启动",
        border_style="cyan"
    ))

    setup_agents()

    # 演示模式
    await simulate_fault()

    # 保持运行（实际生产环境为持续服务）
    console.print("\n[dim]按 Ctrl+C 退出...[/dim]")
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[red]系统已停止[/red]")
        sys.exit(0)

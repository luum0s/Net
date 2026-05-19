"""
Network Device Abstraction Layer (NDAL)
屏蔽多厂商CLI差异，向上提供统一逻辑操作接口
"""
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class VendorType(Enum):
    HUAWEI = "huawei"
    H3C = "h3c"
    CISCO = "cisco"
    JUNIPER = "juniper"
    RUIJIE = "ruijie"

@dataclass
class DeviceInfo:
    name: str
    vendor: VendorType
    ip: str
    device_type: str
    protocol: str
    username: str
    password: str
    enable_password: Optional[str] = None
    port: int = 22
    critical: bool = False
    extra: Dict[str, Any] = None

class CommandTranslator:
    """命令翻译器：逻辑操作 -> 厂商CLI"""

    _COMMAND_MAP = {
        "show_interface_status": {
            VendorType.HUAWEI: "display interface brief",
            VendorType.H3C: "display interface brief",
            VendorType.CISCO: "show ip interface brief",
        },
        "show_mac_table": {
            VendorType.HUAWEI: "display mac-address",
            VendorType.H3C: "display mac-address",
            VendorType.CISCO: "show mac address-table",
        },
        "show_arp": {
            VendorType.HUAWEI: "display arp all",
            VendorType.H3C: "display arp",
            VendorType.CISCO: "show ip arp",
        },
        "show_routing": {
            VendorType.HUAWEI: "display ip routing-table",
            VendorType.H3C: "display ip routing-table",
            VendorType.CISCO: "show ip route",
        },
        "show_bgp_peer": {
            VendorType.HUAWEI: "display bgp peer",
            VendorType.H3C: "display bgp peer",
            VendorType.CISCO: "show ip bgp summary",
        },
        "show_stp": {
            VendorType.HUAWEI: "display stp brief",
            VendorType.H3C: "display stp brief",
            VendorType.CISCO: "show spanning-tree summary",
        },
        "show_port_security": {
            VendorType.HUAWEI: "display port-security",
            VendorType.H3C: "display port-security",
            VendorType.CISCO: "show port-security",
        },
        "shutdown_interface": {
            VendorType.HUAWEI: "interface {iface}\nshutdown",
            VendorType.H3C: "interface {iface}\nshutdown",
            VendorType.CISCO: "interface {iface}\nshutdown",
        },
        "no_shutdown_interface": {
            VendorType.HUAWEI: "interface {iface}\nundo shutdown",
            VendorType.H3C: "interface {iface}\nundo shutdown",
            VendorType.CISCO: "interface {iface}\nno shutdown",
        },
        "save_config": {
            VendorType.HUAWEI: "save\ny",
            VendorType.H3C: "save force",
            VendorType.CISCO: "write memory",
        },
        "ping": {
            VendorType.HUAWEI: "ping -c 5 -a {source} {target}",
            VendorType.H3C: "ping -c 5 -a {source} {target}",
            VendorType.CISCO: "ping {target} source {source} repeat 5",
        },
        "traceroute": {
            VendorType.HUAWEI: "tracert {target}",
            VendorType.H3C: "tracert {target}",
            VendorType.CISCO: "traceroute {target}",
        }
    }

    @classmethod
    def translate(cls, action: str, vendor: VendorType, **kwargs) -> str:
        """将逻辑操作翻译为厂商CLI"""
        if action not in cls._COMMAND_MAP:
            raise ValueError(f"未知操作: {action}")

        vendor_map = cls._COMMAND_MAP[action]
        if vendor not in vendor_map:
            raise ValueError(f"厂商 {vendor.value} 不支持操作: {action}")

        cmd = vendor_map[vendor]
        try:
            return cmd.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"操作 {action} 缺少参数: {e}")

    @classmethod
    def parse_output(cls, action: str, vendor: VendorType, raw_output: str) -> Dict[str, Any]:
        """解析不同厂商的命令输出为结构化数据"""
        parsers = {
            "show_interface_status": cls._parse_interface_status,
            "show_mac_table": cls._parse_mac_table,
            "show_arp": cls._parse_arp,
            "show_stp": cls._parse_stp,
        }

        if action in parsers:
            return parsers[action](raw_output)

        return {"raw": raw_output, "parsed": False}

    @staticmethod
    def _parse_interface_status(output: str) -> Dict[str, Any]:
        """解析接口状态"""
        interfaces = []
        for line in output.split("\n"):
            # 匹配: Interface IP Address Physical Protocol
            parts = line.split()
            if len(parts) >= 4 and not line.startswith("Interface"):
                interfaces.append({
                    "interface": parts[0],
                    "ip": parts[1] if len(parts) > 1 else "--",
                    "physical": parts[-2] if len(parts) >= 3 else "unknown",
                    "protocol": parts[-1] if len(parts) >= 4 else "unknown"
                })
        return {"interfaces": interfaces, "count": len(interfaces)}

    @staticmethod
    def _parse_mac_table(output: str) -> Dict[str, Any]:
        """解析MAC地址表"""
        macs = []
        for line in output.split("\n"):
            parts = line.split()
            if len(parts) >= 4 and re.match(r"[0-9a-fA-F]{4}", parts[0]):
                macs.append({
                    "vlan": parts[0],
                    "mac": parts[1],
                    "type": parts[2],
                    "interface": parts[3]
                })
        return {"macs": macs, "count": len(macs)}

    @staticmethod
    def _parse_arp(output: str) -> Dict[str, Any]:
        """解析ARP表"""
        entries = []
        for line in output.split("\n"):
            parts = line.split()
            if len(parts) >= 4 and re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                entries.append({
                    "ip": parts[0],
                    "mac": parts[1],
                    "type": parts[2],
                    "interface": parts[3]
                })
        return {"entries": entries, "count": len(entries)}

    @staticmethod
    def _parse_stp(output: str) -> Dict[str, Any]:
        """解析STP状态"""
        return {"raw": output, "has_loop_keywords": "loop" in output.lower()}

class DeviceConnector:
    """设备连接器（MVP使用SSH模拟，生产环境集成Netmiko/NAPALM）"""

    def __init__(self, device: DeviceInfo):
        self.device = device
        self.connected = False
        self._session_log = []

    async def connect(self) -> bool:
        """建立连接（MVP模拟）"""
        logger.info(f"[{self.device.name}] 连接建立 {self.device.ip}:{self.device.port}")
        self.connected = True
        return True

    async def execute(self, command: str) -> str:
        """执行命令并返回输出（MVP模拟真实设备响应）"""
        if not self.connected:
            raise ConnectionError(f"设备 {self.device.name} 未连接")

        self._session_log.append(f"> {command}")

        # MVP: 根据命令返回模拟数据
        output = self._simulate_response(command)
        self._session_log.append(output)

        logger.debug(f"[{self.device.name}] 执行: {command}")
        return output

    def _simulate_response(self, command: str) -> str:
        """模拟设备响应（用于MVP演示）"""
        if "display interface brief" in command or "show ip interface brief" in command:
            return """Interface                   IP Address      Physical  Protocol  
GigabitEthernet0/0/1        192.168.10.1    up        up        
GigabitEthernet0/0/2        unassigned      down      down      
GigabitEthernet0/0/24       unassigned      err-disabled down"""

        if "display mac-address" in command or "show mac address-table" in command:
            return """MAC Address    VLAN/VSI/BD   Learned-From        Type      
5489-98c7-1a2b 10/-/-        GE0/0/1             dynamic   
5489-98c7-1a2c 10/-/-        GE0/0/1             dynamic   
... (模拟大量MAC学习)"""

        if "display arp" in command or "show ip arp" in command:
            return """IP Address      MAC Address     Expire(M) Type        Interface
192.168.10.10   5489-98c7-1a2b  20        D           GE0/0/1
192.168.10.11   5489-98c7-1a2c  20        D           GE0/0/1"""

        if "display stp" in command or "show spanning-tree" in command:
            return """MSTID  Port                        Role  STP State     Protection
0      GigabitEthernet0/0/1        ROOT  FORWARDING      NONE
0      GigabitEthernet0/0/24       DESI  DISCARDING      LOOP"""

        if "ping" in command:
            return """Ping 192.168.10.10: 5 data bytes, press CTRL_C to break
Reply from 192.168.10.10: bytes=56 Sequence=1 ttl=255 time=1 ms
--- 192.168.10.10 ping statistics ---
5 packet(s) transmitted
5 packet(s) received
0.00% packet loss"""

        return f"% Command executed: {command}"

    async def disconnect(self):
        self.connected = False
        logger.info(f"[{self.device.name}] 连接断开")

    def get_session_log(self) -> str:
        return "\n".join(self._session_log)

# NetHealer - 多Agent网络故障自愈中枢

## 项目概述

NetHealer 是一个基于多Agent协作的网络故障自愈系统，采用"感知→诊断→决策→执行→验证"的闭环长链推理架构，专门解决异构网络环境下的故障发现慢、诊断难、修复险的核心痛点。

## 核心架构

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Sentinel  │───→│  Pathfinder │───→│  Strategist │───→│   Executor  │───→│  Validator  │
│   (感知)     │    │   (诊断)     │    │   (决策)     │    │   (执行)     │    │   (验证)     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                   │                   │                   │                   │
      └───────────────────┴───────────────────┴───────────────────┴───────────────────┘
                                    Kafka/Redis 消息总线
```

## Agent职责

| Agent | 职责 | 关键技术 |
|-------|------|---------|
| **Sentinel** | 多源告警聚合、降噪、定级 | 事件聚合、严重度分类 |
| **Pathfinder** | 长链推理逐层定位根因 | CoT思维链、设备查询验证（防LLM幻觉） |
| **Strategist** | 风险评估、方案排序、回滚策略 | 双锁机制（规则引擎+风险分级） |
| **Executor** | 原子化指令下发、配置快照 | NDAL设备抽象层（屏蔽多厂商差异） |
| **Validator** | 持续探测、异常回滚、闭环归档 | 自动回滚、知识沉淀 |

## 关键技术难点攻克

1. **多厂商命令差异**: NDAL设备抽象层，逻辑操作自动翻译为华为/华三/Cisco具体CLI
2. **长链推理幻觉**: 强制每步推理必须通过SNMP/SSH查询真实设备，禁止纯LLM臆测
3. **自动修复安全性**: 双锁机制（规则引擎校验+人工确认），中低危操作限时自动回滚

## 快速开始

### 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 配置设备（编辑 config/devices.yaml）
# 设置环境变量
export DEVICE_PASSWORD="your_password"
export ENABLE_PASSWORD="your_enable_password"
```

### 运行演示

```bash
python main.py
```

演示将模拟一个"核心交换机下联区域二层环路"故障，完整展示5个Agent的协作自愈流程。

### 生产部署

1. 将 `DeviceConnector` 中的模拟响应替换为真实 `Netmiko`/`NAPALM` 连接
2. 消息总线从内存版替换为 `Kafka` 集群
3. 集成 `Zabbix`/`Prometheus` Webhook 到 `Sentinel.on_alert()`
4. 对接 `Neo4j` 拓扑数据库和 `Milvus` 向量知识库
5. LLM诊断Agent接入 `OpenAI`/`Claude` 或本地 `Qwen-72B`

## 项目结构

```
nethealer/
├── agents/              # 5个核心Agent
│   ├── sentinel.py      # 感知Agent
│   ├── pathfinder.py    # 诊断Agent（长链推理核心）
│   ├── strategist.py    # 决策Agent
│   ├── executor.py      # 执行Agent
│   └── validator.py     # 验证Agent
├── core/                # 基础设施
│   ├── bus.py           # 消息总线
│   ├── device_abstraction.py  # NDAL设备抽象层
│   └── state_machine.py # 自愈状态机
├── config/              # 配置
│   ├── devices.yaml     # 设备清单
│   └── rules.yaml       # 自愈规则与合规基线
├── logs/                # 日志目录
├── knowledge/           # 知识库（RAG沉淀）
├── main.py              # 主入口
└── requirements.txt     # 依赖
```

## 设计哲学

- **可观测**: 完整思维链记录，每一步推理可追溯审计
- **可回滚**: 任何自动操作都有对应的回滚计划
- **可演进**: 知识自动沉淀，历史案例驱动诊断准确率提升
- **可控**: 高危操作强制人工确认，杜绝自动化灾难

## License

MIT License - 仅供学习研究使用，生产环境需充分测试。

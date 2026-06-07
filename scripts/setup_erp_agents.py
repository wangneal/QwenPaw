#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键创建 ERP 专业 Agent 并配置路由。

用法（在 QwenPaw 容器内执行）：
    python3 /tmp/setup_erp_agents.py

或从宿主机执行：
    docker cp scripts/setup_erp_agents.py qwenpaw:/tmp/setup_erp_agents.py
    docker exec qwenpaw python3 /tmp/setup_erp_agents.py

环境变量：
    PERSONA_BASE  — Persona 文件根目录（默认 /tmp/erp-personas）
    SKILL_BASE    — Skill 文件根目录（默认 /tmp/erp-skills）
    QWENPAW_WORKING_DIR — QwenPaw 工作目录（默认 /app/working）
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Agent 定义 ──────────────────────────────────────────────

AGENTS = [
    {
        "id": "erp-finance",
        "name": "财务助手",
        "persona_dir": "erp-finance",
        "skills": ["kingdee-query-guide", "kingdee-field-mapping", "kingdee-write-safety", "kingdee-finance-fields", "kingdee-product-qa"],
        "description": "金蝶财务域专家 — 总账、应收、应付、固定资产、报表",
    },
    {
        "id": "erp-sales",
        "name": "销售助手",
        "persona_dir": "erp-sales",
        "skills": ["kingdee-query-guide", "kingdee-field-mapping", "kingdee-write-safety", "kingdee-sales-fields", "kingdee-product-qa"],
        "description": "金蝶销售域专家 — 销售订单、出库、价格、客户",
    },
    {
        "id": "erp-inventory",
        "name": "库存助手",
        "persona_dir": "erp-inventory",
        "skills": ["kingdee-query-guide", "kingdee-field-mapping", "kingdee-write-safety", "kingdee-inventory-fields", "kingdee-product-qa"],
        "description": "金蝶库存域专家 — 出入库、盘点、库存查询",
    },
    {
        "id": "erp-purchase",
        "name": "采购助手",
        "persona_dir": "erp-purchase",
        "skills": ["kingdee-query-guide", "kingdee-field-mapping", "kingdee-write-safety", "kingdee-procurement-fields", "kingdee-product-qa"],
        "description": "金蝶采购域专家 — 采购订单、入库、供应商管理",
    },
    {
        "id": "erp-executive",
        "name": "高管决策助手",
        "persona_dir": "erp-executive",
        "skills": [
            "kingdee-query-guide", "kingdee-field-mapping",
            "erp-cross-system-reconciliation", "erp-cross-system-correlation",
            "erp-cross-system-monthly", "erp-cross-system-push", "erp-executive-digest", "kingdee-product-qa",
        ],
        "description": "ERP 高管决策助手 — 跨域汇总、多系统对账、经营分析",
    },
]

DEPRECATED_ERP_SKILLS = {"humanizer-zh"}

# 金蝶工具列表（需要为每个专业 agent 启用）
KINGDEE_TOOL_FALLBACKS = [
    "kingdee_query_bill",
    "kingdee_view_bill",
    "kingdee_get_report",
    "kingdee_get_kds_report",
    "kingdee_query_metadata",
    "kingdee_search_form",
    "kingdee_list_user_orgs",
    "kingdee_save_bill",
    "kingdee_delete_bill",
    "kingdee_submit_bill",
    "kingdee_audit_bill",
    "kingdee_unaudit_bill",
    "kingdee_push_bill",
    "kingdee_execute_operation",
    "kingdee_switch_org",
    "kingdee_workflow_audit",
    "kingdee_product_qa",
    "kingdee_list_digest_templates",
    "erp_unified_query",
    "erp_compare_data",
]

# 从默认 agent 配置复制的工具配置（金蝶连接信息）
CONFIG_TOOLS = ["kingdee_query_bill"]
FLAGSHIP_TOOL_PREFIX = "kingdee_flagship_"


def load_erp_tool_metadata() -> dict[str, dict]:
    """Load ERP tool metadata from plugin manifest, with name fallbacks.

    The Kingdee plugin evolves faster than this deployment helper. Reading
    plugin.json prevents newly added tools from being omitted from specialist
    agents during initialization.
    """
    manifest_candidates = []
    env_manifest = os.environ.get("KINGDEE_PLUGIN_MANIFEST", "").strip()
    if env_manifest:
        manifest_candidates.append(Path(env_manifest))
    manifest_candidates.extend([
        Path("/app/builtin-plugins/tool/kingdee-erp/plugin.json"),
        Path(__file__).resolve().parents[1] / "plugins" / "tool" / "kingdee-erp" / "plugin.json",
    ])

    tools: dict[str, dict] = {}
    seen = set()
    for manifest_path in manifest_candidates:
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  警告: 读取工具清单失败 {manifest_path}: {exc}")
            continue
        for item in data.get("meta", {}).get("tools", []):
            name = item.get("name") if isinstance(item, dict) else ""
            if name and name not in seen:
                tools[name] = {
                    "name": name,
                    "description": str(item.get("description", "")).strip(),
                    "icon": str(item.get("icon", "erp")).strip() or "erp",
                    "requires_config": bool(item.get("requires_config", True)),
                }
                seen.add(name)
        if tools:
            break

    for name in KINGDEE_TOOL_FALLBACKS:
        if name not in seen:
            tools[name] = {
                "name": name,
                "description": "",
                "icon": "erp",
                "requires_config": True,
            }
            seen.add(name)
    return tools


def load_erp_tool_names() -> list[str]:
    """Load ERP tool names from plugin manifest, with integration fallbacks."""
    return list(load_erp_tool_metadata().keys())


def apply_tool_metadata(entry: dict, tool_name: str, metadata: dict | None) -> None:
    """Synchronize user-facing tool metadata from the plugin manifest."""
    entry["name"] = tool_name
    entry["display_to_user"] = True
    entry.setdefault("async_execution", False)
    if not metadata:
        entry.setdefault("icon", "erp")
        return
    if metadata.get("description"):
        entry["description"] = metadata["description"]
    entry["icon"] = metadata.get("icon") or "erp"
    entry["requires_config"] = bool(metadata.get("requires_config", True))


def should_enable_flagship_tools() -> bool:
    """Return whether flagship-version tools should be enabled."""
    return os.environ.get("KINGDEE_ENABLE_FLAGSHIP_TOOLS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def disable_flagship_tools_for_enterprise(builtin: dict) -> int:
    """Disable flagship-only tools for Enterprise Edition deployments."""
    if should_enable_flagship_tools():
        return 0
    disabled = 0
    for tool_name, entry in builtin.items():
        if tool_name.startswith(FLAGSHIP_TOOL_PREFIX) and entry.get("enabled", False):
            entry["enabled"] = False
            disabled += 1
    return disabled

# 默认 Agent 的 ERP 路由规则
ROUTING_SECTION = """

## ERP 语义路由

当用户的请求涉及 ERP / 金蝶 / 财务 / 销售 / 采购 / 库存 / 生产 / 供应链等业务系统操作时，你应该作为路由器，将请求转发给对应的专业 Agent。

### 路由规则

| 用户意图关键词 | 目标 Agent | 说明 |
|---|---|---|
| 凭证、科目、总账、应收、应付、收付款、余额表、利润表、资产负债表、财务、报表、固定资产、发票、费用、合并报表 | `erp-finance` | 财务域 |
| 销售订单、客户、报价、出库、发货、销售、价格、合同 | `erp-sales` | 销售域 |
| 采购订单、供应商、采购、入库、比价、采购申请 | `erp-purchase` | 采购域 |
| 库存、盘点、出入库、仓库、物料、库存查询、调拨 | `erp-inventory` | 库存域 |
| 经营分析、汇总、对比、多系统、对账、月结、利润、成本、决策、报表汇总 | `erp-executive` | 高管决策 |
| 怎么操作、如何配置、报错解决、产品问题、知识库、智能客服 | `erp-finance` | 产品问答（任意 Agent 可处理） |
| ERP 相关但不确定具体域 | `erp-finance` | 默认路由到财务 |

### 路由流程

1. 分析用户意图，判断属于哪个业务域
2. 使用 `chat_with_agent` 工具，将用户原始问题转发给对应的专业 Agent
3. 将专业 Agent 的回复直接返回给用户
4. 如果用户的问题不涉及 ERP，正常回答即可

### 输出约束

1. 只输出面向用户的最终答复、操作摘要、阻断原因和下一步动作。
2. 不得输出内部思考、工具选择推理、执行计划草稿或英文推理句。
3. 用户未要求英文时，答复使用中文；工具名、FormId、字段名、错误码可保留原文。
4. 不得使用 emoji、表情符号或装饰性图标。

### 示例

用户: "帮我查一下上个月的应收款余额"
→ 调用 `chat_with_agent(to_agent="erp-finance", text="帮我查一下上个月的应收款余额")`

用户: "最近有哪些销售订单还没发货？"
→ 调用 `chat_with_agent(to_agent="erp-sales", text="最近有哪些销售订单还没发货？")`

用户: "今天天气怎么样？"
→ 直接回答（非 ERP 问题，不需要路由）
"""

ROUTING_OUTPUT_CONSTRAINTS = """

## ERP 路由输出约束

1. 只输出面向用户的最终答复、操作摘要、阻断原因和下一步动作。
2. 不得输出内部思考、工具选择推理、执行计划草稿或英文推理句。
3. 用户未要求英文时，答复使用中文；工具名、FormId、字段名、错误码可保留原文。
4. 不得使用 emoji、表情符号或装饰性图标。
"""

ERP_RUNTIME_OUTPUT_CONTRACT = """# ERP 运行期输出契约

以下规则优先级高于其他 ERP 业务说明，适用于所有用户可见输出。

## 用户可见输出

1. 只输出最终答复、操作摘要、阻断原因、下一步动作和必要的确认问题。
2. 在分析意图、选择工具、准备参数、等待工具返回、整理工具结果时，不得输出任何过程性文字。
3. 不得复述“用户想要……”“我需要……”“让我……”“首先……”“根据规则……”等内部推理。
4. 不得输出英文推理句，例如 The user wants、I need、I should、Let me、looking at the tool。
5. 不得输出工具选择理由、执行计划草稿、调试说明或模型自述。
6. 不得使用 emoji、表情符号或装饰性图标。

## 工具调用行为

1. 需要工具时，直接调用工具；调用前不向用户解释工具选择过程。
2. 工具返回后，只基于工具结果输出业务结论或阻断说明。
3. 工具返回配置错误、权限错误或金蝶业务错误时，不得包装为成功。

## 标准输出结构

查询成功时：

**查询结果**：说明查询对象、组织、时间范围和关键数据。
**数据来源**：列出工具名、FormId、单据号或记录标识。

写入、删除、分配、取消分配、审核、反审核、下推等操作处于预览阶段时：

**操作预览**：说明操作类型、业务对象、关键编码、目标组织和影响范围。
**执行状态**：预览模式，尚未写入金蝶。
**下一步动作**：请用户确认后再执行。

被配置、权限或业务规则阻断时：

**阻断原因**：说明明确原因。
**下一步动作**：说明需要补充的配置、权限或业务参数。
"""

ERP_RUNTIME_MARKER = "# ERP 运行期输出契约"


# ── 工具函数 ────────────────────────────────────────────────

def run(cmd: str, check=True):
    """执行命令并打印输出。"""
    print(f"  > {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout.strip():
        print(f"    {result.stdout.strip()}")
    if result.returncode != 0 and check:
        print(f"    ERROR: {result.stderr.strip()}")
        if "already exists" not in result.stderr:
            return False
    return True


def read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def ensure_erp_runtime_contract(path: Path) -> bool:
    """Ensure the ERP runtime output contract is the first prompt section."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing.startswith(ERP_RUNTIME_MARKER):
        return False
    if ERP_RUNTIME_MARKER in existing:
        before, _, after = existing.partition(ERP_RUNTIME_MARKER)
        remainder = after
        next_header = remainder.find("\n# ")
        if next_header >= 0:
            existing = (before + remainder[next_header + 1:]).strip()
        else:
            existing = before.strip()
    new_content = ERP_RUNTIME_OUTPUT_CONTRACT.strip()
    if existing.strip():
        new_content += "\n\n" + existing.strip()
    path.write_text(new_content + "\n", encoding="utf-8")
    return True


def parse_skill_frontmatter(skill_md_path: Path) -> dict:
    """解析 SKILL.md 的 YAML frontmatter，返回 metadata 字典。"""
    with open(skill_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.startswith("---"):
        return {"name": skill_md_path.parent.name, "description": ""}
    end = content.find("---", 3)
    if end == -1:
        return {"name": skill_md_path.parent.name, "description": ""}
    yaml_block = content[3:end].strip()
    meta = {}
    for line in yaml_block.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta


def reconcile_skill_manifest(workspace_dir: Path):
    """扫描 workspace/skills/ 目录，更新 workspace/skill.json。

    这是 QwenPaw skill 系统的核心发现机制：
    - 扫描 <workspace>/skills/ 下每个包含 SKILL.md 的子目录
    - 读取 SKILL.md 的 frontmatter 构建 metadata
    - 更新 <workspace>/skill.json 的 skills 字段
    - 移除已不存在的 skill 条目
    """
    skills_dir = workspace_dir / "skills"
    manifest_path = workspace_dir / "skill.json"

    # 发现所有包含 SKILL.md 的 skill 目录
    discovered = {}
    if skills_dir.exists():
        for skill_path in skills_dir.iterdir():
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                fm = parse_skill_frontmatter(skill_path / "SKILL.md")
                skill_name = skill_path.name
                now = datetime.now(timezone.utc).isoformat()
                discovered[skill_name] = {
                    "enabled": True,
                    "channels": ["all"],
                    "source": "customized",
                    "installed_from": "",
                    "config": {},
                    "tags": [],
                    "metadata": {
                        "name": fm.get("name", skill_name),
                        "description": fm.get("description", ""),
                        "version_text": fm.get("version_text", "1.0"),
                        "source": "customized",
                        "protected": False,
                        "requirements": {
                            "require_bins": [],
                            "require_envs": [],
                        },
                        "updated_at": now,
                    },
                    "requirements": {
                        "require_bins": [],
                        "require_envs": [],
                    },
                    "updated_at": now,
                }

    # 读取或创建 manifest
    if manifest_path.exists():
        manifest = read_json(str(manifest_path))
    else:
        manifest = {
            "schema_version": "workspace-skill-manifest.v1",
            "version": 0,
            "skills": {},
        }

    # 更新 skills 字段
    existing = manifest.get("skills", {})
    # 添加新发现的 skill
    for name, entry in discovered.items():
        if name not in existing:
            existing[name] = entry
        else:
            # 已存在则更新 metadata 但保留 enabled 等用户配置
            existing[name]["metadata"] = entry["metadata"]
            existing[name]["updated_at"] = entry["updated_at"]

    # 移除已不存在的 skill
    to_remove = [name for name in existing if name not in discovered]
    for name in to_remove:
        del existing[name]

    manifest["skills"] = existing
    manifest["version"] = manifest.get("version", 0) + 1
    write_json(str(manifest_path), manifest)

    return len(discovered), len(to_remove)


# ── 主流程 ──────────────────────────────────────────────────

def main():
    working_dir = os.environ.get("QWENPAW_WORKING_DIR", "/app/working")
    workspace_base = Path(working_dir) / "workspaces"
    erp_tool_metadata = load_erp_tool_metadata()
    erp_tools = list(erp_tool_metadata.keys())
    print(f"已加载 {len(erp_tools)} 个 ERP 工具用于专业 Agent 初始化")

    # 找默认 agent 的配置（用于复制金蝶连接 config）
    default_agent_json = workspace_base / "default" / "agent.json"
    default_config = {}
    if default_agent_json.exists():
        default_data = read_json(str(default_agent_json))
        builtin = default_data.get("tools", {}).get("builtin_tools", {})
        for tool_name in CONFIG_TOOLS:
            if tool_name in builtin:
                default_config[tool_name] = builtin[tool_name]

    print(f"=== 创建 {len(AGENTS)} 个 ERP 专业 Agent ===\n")

    for agent_def in AGENTS:
        agent_id = agent_def["id"]
        agent_name = agent_def["name"]
        ws_dir = workspace_base / agent_id

        print(f"\n--- {agent_name} ({agent_id}) ---")

        # ── 1. 创建 Agent（如果不存在）──
        if ws_dir.exists():
            print(f"  Agent 目录已存在")
        else:
            run(f"qwenpaw agent create --name '{agent_name}' --agent-id {agent_id} --language zh")

        # ── 2. 复制 Persona（SOUL.md + PROFILE.md）──
        # Persona 是纯文件驱动，复制即可，QwenPaw 运行时自动读取
        persona_base = os.environ.get("PERSONA_BASE", "/tmp/erp-personas")
        zh_dir = Path(persona_base) / agent_def["persona_dir"] / "zh"

        for md_file in ["SOUL.md", "PROFILE.md"]:
            src = zh_dir / md_file
            dst = ws_dir / md_file
            if src.exists():
                shutil.copy2(str(src), str(dst))
                print(f"  已复制 {md_file}")
            elif dst.exists():
                print(f"  {md_file} 已存在（跳过）")
            else:
                print(f"  警告: {md_file} 未找到: {src}")

        if ensure_erp_runtime_contract(ws_dir / "AGENTS.md"):
            print("  已写入 ERP 运行期输出契约")

        # ── 3. 复制 Skills + 注册到 skill.json ──
        # Skills 需要文件复制 + manifest 更新才能被 QwenPaw 识别
        skill_base = os.environ.get("SKILL_BASE", "/tmp/erp-skills")
        skills_installed = 0

        for skill_name in agent_def["skills"]:
            skill_src = Path(skill_base) / skill_name
            skill_dst = ws_dir / "skills" / skill_name
            if skill_src.exists():
                if skill_dst.exists():
                    shutil.rmtree(str(skill_dst))
                shutil.copytree(str(skill_src), str(skill_dst))
                # 验证 SKILL.md 存在
                if (skill_dst / "SKILL.md").exists():
                    print(f"  已安装 skill: {skill_name}")
                    skills_installed += 1
                else:
                    print(f"  警告: skill {skill_name} 缺少 SKILL.md")
            else:
                print(f"  警告: skill 未找到: {skill_src}")

        for skill_name in DEPRECATED_ERP_SKILLS:
            deprecated_dst = ws_dir / "skills" / skill_name
            if deprecated_dst.exists():
                shutil.rmtree(str(deprecated_dst))
                print(f"  已移除过期 skill: {skill_name}")

        # 执行 reconcile：扫描 skills/ 目录并更新 skill.json
        if skills_installed > 0:
            found, removed = reconcile_skill_manifest(ws_dir)
            print(f"  reconcile skill.json: 发现 {found} 个 skill, 移除 {removed} 个过期条目")

        # ── 4. 启用金蝶工具到 agent.json ──
        agent_json_path = ws_dir / "agent.json"
        if agent_json_path.exists():
            agent_data = read_json(str(agent_json_path))
            builtin = agent_data.setdefault("tools", {}).setdefault("builtin_tools", {})

            enabled_count = 0
            for tool_name in erp_tools:
                metadata = erp_tool_metadata.get(tool_name)
                if tool_name in builtin:
                    apply_tool_metadata(builtin[tool_name], tool_name, metadata)
                    if not builtin[tool_name].get("enabled", False):
                        builtin[tool_name]["enabled"] = True
                        enabled_count += 1
                elif tool_name in default_config:
                    entry = dict(default_config[tool_name])
                    entry["enabled"] = True
                    apply_tool_metadata(entry, tool_name, metadata)
                    builtin[tool_name] = entry
                    enabled_count += 1
                else:
                    entry = {
                        "name": tool_name,
                        "enabled": True,
                        "display_to_user": True,
                        "async_execution": False,
                        "icon": "erp",
                        "config": {},
                    }
                    apply_tool_metadata(entry, tool_name, metadata)
                    builtin[tool_name] = entry
                    enabled_count += 1

            # 也启用 chat_with_agent 和 list_agents（跨 Agent 通信）
            for routing_tool in ["chat_with_agent", "list_agents"]:
                if routing_tool in builtin and not builtin[routing_tool].get("enabled", False):
                    builtin[routing_tool]["enabled"] = True

            disabled_flagship = disable_flagship_tools_for_enterprise(builtin)
            write_json(str(agent_json_path), agent_data)
            print(f"  启用 {enabled_count} 个金蝶工具")
            if disabled_flagship:
                print(f"  已禁用 {disabled_flagship} 个旗舰版专用工具")

    print(f"\n=== 全部 {len(AGENTS)} 个 Agent 创建完成 ===")

    # ── 4.5 配置传播：从 default Agent 继承模型 + Kingdee 连接配置 ──
    print("\n--- 传播配置到专家 Agent ---")
    default_agent_json = workspace_base / "default" / "agent.json"
    if default_agent_json.exists():
        default_data = read_json(str(default_agent_json))

        # 提取 default agent 的模型配置
        default_model = default_data.get("active_model")

        # 提取 default agent 的 kingdee_query_bill 配置（连接参数）
        # 注意：QwenPaw 将安装的工具放在 builtin_tools 而非 custom_tools
        kd_config = (
            default_data.get("tools", {})
            .get("builtin_tools", {})
            .get("kingdee_query_bill", {})
            .get("config", {})
        )

        if default_model:
            print(f"  默认模型: {default_model.get('provider_id', '?')}/{default_model.get('model', '?')}")
        else:
            print("  警告: 默认 Agent 无 active_model，跳过模型传播")

        if kd_config:
            # 检查是否有实质内容（不只是空值）
            has_real_config = any(
                v for k, v in kd_config.items()
                if k in ("server_url", "acct_id", "user_name", "app_id", "app_secret", "lcid")
            )
            if has_real_config:
                print(f"  金蝶连接配置: server_url={kd_config.get('server_url', '?')[:50]}...")
            else:
                print("  警告: 金蝶连接配置为空（可能尚未在 Console 中配置），跳过配置传播")
                kd_config = {}
        else:
            print("  警告: 默认 Agent 无 Kingdee 连接配置，跳过配置传播")

        # 写入每个专家 Agent
        propagated = 0
        for agent_info in AGENTS:
            agent_id = agent_info["id"]
            agent_json_path = workspace_base / agent_id / "agent.json"
            if not agent_json_path.exists():
                continue

            agent_data = read_json(str(agent_json_path))
            changed = False

            # 传播模型。专业 Agent 必须跟随 default 当前可用模型，
            # 避免历史 agent.json 保留已无授权的模型配置。
            if default_model and agent_data.get("active_model") != default_model:
                agent_data["active_model"] = default_model
                changed = True

            # 传播 Kingdee 连接配置到所有金蝶工具
            if kd_config:
                bt = agent_data.setdefault("tools", {}).setdefault("builtin_tools", {})
                for tool_name in erp_tools:
                    if tool_name in bt:
                        existing_cfg = bt[tool_name].get("config", {})
                        if not existing_cfg or not any(
                            v for k, v in existing_cfg.items()
                            if k in ("server_url", "acct_id", "app_id")
                        ):
                            bt[tool_name]["config"] = dict(kd_config)
                            changed = True

            if changed:
                write_json(str(agent_json_path), agent_data)
                propagated += 1

        print(f"  已传播配置到 {propagated}/{len(AGENTS)} 个专家 Agent")

    # ── 5. 修改默认 Agent SOUL.md — 添加 ERP 语义路由 ──
    print("\n--- 配置默认 Agent ERP 语义路由 ---")
    default_soul = workspace_base / "default" / "SOUL.md"

    if default_soul.exists():
        content = default_soul.read_text(encoding="utf-8")
        if ensure_erp_runtime_contract(default_soul):
            print("  默认 Agent SOUL.md 已前置 ERP 运行期输出契约")
        content = default_soul.read_text(encoding="utf-8")
        if "ERP 语义路由" not in content:
            with open(str(default_soul), "a", encoding="utf-8") as f:
                f.write(ROUTING_SECTION)
            print("  默认 Agent SOUL.md 已添加 ERP 路由规则")
        else:
            print("  ERP 路由规则已存在，跳过")
        content = default_soul.read_text(encoding="utf-8")
        if "ERP 路由输出约束" not in content:
            with open(str(default_soul), "a", encoding="utf-8") as f:
                f.write(ROUTING_OUTPUT_CONSTRAINTS)
            print("  默认 Agent SOUL.md 已添加 ERP 路由输出约束")

    # ── 6. 确保默认 Agent 启用 chat_with_agent / list_agents ──
    default_agent_json_path = workspace_base / "default" / "agent.json"
    if default_agent_json_path.exists():
        default_data = read_json(str(default_agent_json_path))
        bt = default_data.setdefault("tools", {}).setdefault("builtin_tools", {})
        changed = False
        for tool_name, metadata in erp_tool_metadata.items():
            if tool_name in bt:
                before = dict(bt[tool_name])
                apply_tool_metadata(bt[tool_name], tool_name, metadata)
                if bt[tool_name] != before:
                    changed = True
        for tool in ["chat_with_agent", "list_agents"]:
            if tool in bt and not bt[tool].get("enabled", False):
                bt[tool]["enabled"] = True
                changed = True
        disabled_flagship = disable_flagship_tools_for_enterprise(bt)
        if disabled_flagship:
            changed = True
        if changed:
            write_json(str(default_agent_json_path), default_data)
            print("  默认 Agent 已启用 chat_with_agent/list_agents")
            if disabled_flagship:
                print(f"  默认 Agent 已禁用 {disabled_flagship} 个旗舰版专用工具")
        else:
            print("  chat_with_agent/list_agents 已是启用状态")

    print("\n=== 部署完成！请重启 QwenPaw 使配置生效 ===")
    print("  docker restart qwenpaw")
    print("  重启后清除浏览器缓存 (Ctrl+Shift+Delete)")


def insert_default_permissions():
    """插入默认管理员权限，确保 Console 可直接测试。

    Console 聊天时用户身份为 console:default（无 user_id 时）。
    如果权限表为空，所有工具调用都会被拦截。
    此函数在权限表为空时插入一条全量管理员权限。
    """
    working_dir = os.environ.get("QWENPAW_WORKING_DIR", "/app/working")
    db_path = Path(working_dir) / "plugin_data" / "erp" / "permissions.db"

    if not db_path.exists():
        print("\n  权限数据库不存在，跳过默认权限插入")
        return

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 检查是否已有权限记录
    count = cur.execute("SELECT COUNT(*) FROM user_permissions").fetchone()[0]
    if count > 0:
        print(f"\n  权限表已有 {count} 条记录，跳过默认权限插入")
        conn.close()
        return

    # 插入默认管理员权限（全组织 + 全域 + 读写）
    # Console 身份: channel=console, user_id=default
    default_perms = [
        ("console:default", "*", "管理员", "", "writeable"),
        ("unknown:unknown", "*", "开发调试", "", "writeable"),
    ]
    cur.executemany(
        "INSERT INTO user_permissions (key, org_id, display_name, domains, access) VALUES (?, ?, ?, ?, ?)",
        default_perms,
    )
    conn.commit()
    conn.close()
    print(f"\n--- 插入默认管理员权限 ---")
    print(f"  已插入 {len(default_perms)} 条全量权限（全组织 + 全域 + 读写）")
    print(f"  console:default — Console 聊天身份")
    print(f"  unknown:unknown — 开发调试身份")


def migrate_config_to_json():
    """将 QwenPaw agent.json 中的金蝶连接配置迁移到自管 JSON 文件。

    从 agent.json 的 builtin_tools.kingdee_query_bill.config 读取配置，
    写入 plugin_data/erp/configs/kingdee.json。

    这是多厂商配置框架化的关键迁移步骤：
    - 旧：配置存在 QwenPaw 的 agent.json（per-tool 存储）
    - 新：配置存在 plugin_data/erp/configs/{backend}.json（自管存储）
    """
    working_dir = os.environ.get("QWENPAW_WORKING_DIR", "/app/working")
    default_json = Path(working_dir) / "workspaces" / "default" / "agent.json"

    if not default_json.exists():
        print("\n  默认 Agent 配置不存在，跳过配置迁移")
        return

    try:
        data = json.loads(default_json.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"\n  警告: 读取 agent.json 失败: {e}")
        return

    # 从 builtin_tools 中读取金蝶配置
    kd_config = (
        data.get("tools", {})
        .get("builtin_tools", {})
        .get("kingdee_query_bill", {})
        .get("config", {})
    )

    if not kd_config:
        print("\n  agent.json 中无金蝶配置，跳过配置迁移")
        return

    # 检查是否有实质内容
    has_real = any(
        v for k, v in kd_config.items()
        if k in ("server_url", "acct_id", "app_id")
    )
    if not has_real:
        print("\n  agent.json 中金蝶配置为空（可能尚未在 Console 中配置），跳过迁移")
        return

    # 写入自管 JSON
    config_dir = Path(working_dir) / "plugin_data" / "erp" / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "kingdee.json"

    # 如果已有自管配置且有效，不覆盖
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            if existing and any(v for k, v in existing.items() if k in ("server_url", "acct_id", "app_id")):
                print("\n  自管配置已存在，跳过迁移")
                return
        except Exception:
            pass

    config_path.write_text(
        json.dumps(kd_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n--- 配置迁移 ---")
    print(f"  已从 agent.json 迁移金蝶连接配置到 {config_path}")
    server_url = kd_config.get("server_url", "")
    print(f"  server_url: {server_url[:50]}...")


if __name__ == "__main__":
    main()
    insert_default_permissions()
    migrate_config_to_json()

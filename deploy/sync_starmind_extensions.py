# -*- coding: utf-8 -*-
"""Deployment-side StarMind extension sync.

This script keeps StarMind-specific plugin/skill enablement outside the
QwenPaw core runtime.  It is intended to run from the Docker entrypoint after
built-in plugin files have been copied into the working directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from qwenpaw.agents.skill_system import SkillPoolService, SkillService
from qwenpaw.config import load_config
from qwenpaw.config.config import (
    BuiltinToolConfig,
    load_agent_config,
    save_agent_config,
)
from qwenpaw.constant import WORKING_DIR


def _is_enabled_env(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _flagship_enabled() -> bool:
    """Return whether Kingdee Flagship Edition tools should be exposed."""
    return _is_enabled_env("KINGDEE_ENABLE_FLAGSHIP_TOOLS", False)


def _is_flagship_tool(name: str) -> bool:
    return name.startswith("kingdee_flagship_")


def _agent_ids() -> list[str]:
    config = load_config()
    profiles = getattr(config.agents, "profiles", {}) or {}
    ids = list(profiles) or ["default"]

    requested = os.environ.get("STARMIND_EXTENSION_AGENT_IDS", "").strip()
    if requested:
        allowed = {item.strip() for item in requested.split(",") if item.strip()}
        ids = [agent_id for agent_id in ids if agent_id in allowed]
    return ids


def _workspace_for_agent(agent_id: str) -> Path:
    config = load_config()
    profiles = getattr(config.agents, "profiles", {}) or {}
    ref = profiles.get(agent_id)
    workspace = Path(getattr(ref, "workspace_dir", "") or WORKING_DIR)
    workspace = workspace.expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _tool_spec(name: str, description: str = "", icon: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "icon": icon,
        "enabled": True,
    }


KINGDEE_RUNTIME_TOOL_SPECS = [
    _tool_spec(
        "kingdee_flagship_describe_form",
        "旗舰版：查询表单的 V2 API 请求参数定义，调用 V2 API 前先用此工具了解参数",
        "erp",
    ),
    _tool_spec(
        "kingdee_flagship_request_v2",
        "旗舰版 V2 RESTful API 通用请求，先用 describe_form 查看参数格式再调用",
        "erp",
    ),
    _tool_spec("kingdee_flagship_list_user_orgs", "旗舰版：查询用户有权限的组织列表", "erp"),
    _tool_spec("kingdee_flagship_search_form", "旗舰版：模糊搜索表单，返回匹配的 FormId 列表", "erp"),
    _tool_spec("kingdee_flagship_switch_org", "旗舰版：切换当前默认组织（本地记录）", "erp"),
    _tool_spec("erp_unified_query", "跨ERP统一查询：同时查询多个ERP系统并合并结果", "erp"),
    _tool_spec("erp_compare_data", "跨ERP数据比对：对比两个ERP系统中的同类数据差异", "erp"),
]


def _collect_plugin_tool_specs() -> dict[str, dict[str, Any]]:
    plugins_dir = Path(os.environ.get("starmind_WORKING_DIR", WORKING_DIR)) / "plugins"
    specs: dict[str, dict[str, Any]] = {}
    if not plugins_dir.is_dir():
        return specs

    for plugin_dir in sorted(plugins_dir.iterdir()):
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Skipping invalid plugin manifest {manifest_path}: {exc}")
            continue

        meta = manifest.get("meta") or {}
        old_name = meta.get("tool_name")
        if isinstance(old_name, str) and old_name:
            specs[old_name] = _tool_spec(old_name)

        for tool in meta.get("tools", []):
            if not isinstance(tool, dict) or not tool.get("name"):
                continue
            name = tool["name"]
            if _is_flagship_tool(name) and not _flagship_enabled():
                continue
            specs[name] = {
                "name": name,
                "description": tool.get("description", ""),
                "icon": tool.get("icon"),
                "display_to_user": tool.get("display_to_user", True),
                "async_execution": tool.get("async_execution", False),
                "enabled": tool.get("enabled", True),
            }

        if manifest.get("id") == "qwenpaw-kd-tool" or plugin_dir.name == "kingdee-erp":
            for spec in KINGDEE_RUNTIME_TOOL_SPECS:
                if _is_flagship_tool(spec["name"]) and not _flagship_enabled():
                    continue
                specs.setdefault(spec["name"], spec)

    return specs


def sync_plugin_tools() -> None:
    if not _is_enabled_env("STARMIND_AUTO_ENABLE_PLUGIN_TOOLS", True):
        return

    specs = _collect_plugin_tool_specs()
    if not specs:
        print("No plugin tools found to sync.")
        return

    for agent_id in _agent_ids():
        agent_cfg = load_agent_config(agent_id)
        changed = False
        added = 0
        enabled = 0
        disabled = 0
        for name, spec in specs.items():
            should_enable = bool(spec.get("enabled", True))
            current = agent_cfg.tools.builtin_tools.get(name)
            if current is None:
                agent_cfg.tools.builtin_tools[name] = BuiltinToolConfig(
                    name=name,
                    enabled=should_enable,
                    description=spec.get("description", ""),
                    display_to_user=bool(spec.get("display_to_user", True)),
                    async_execution=bool(spec.get("async_execution", False)),
                    icon=spec.get("icon"),
                    config={},
                )
                changed = True
                added += 1
                if should_enable:
                    enabled += 1
                continue

            if should_enable and not current.enabled:
                current.enabled = True
                changed = True
                enabled += 1
            if spec.get("description") and current.description != spec["description"]:
                current.description = spec["description"]
                changed = True
            if spec.get("icon") and current.icon != spec["icon"]:
                current.icon = spec["icon"]
                changed = True

        if not _flagship_enabled():
            for name, current in agent_cfg.tools.builtin_tools.items():
                if _is_flagship_tool(name) and current.enabled:
                    current.enabled = False
                    changed = True
                    disabled += 1

        if changed:
            save_agent_config(agent_id, agent_cfg)
        print(
            f"  Agent {agent_id}: plugin tools checked {len(specs)}, "
            f"added {added}, enabled {enabled}, disabled {disabled}"
        )


def sync_skills() -> None:
    if not _is_enabled_env("STARMIND_AUTO_ENABLE_SKILLS", True):
        return

    pool = SkillPoolService()
    for agent_id in _agent_ids():
        workspace = _workspace_for_agent(agent_id)
        service = SkillService(workspace)
        installed = 0
        enabled = 0
        for skill in pool.list_all_skills():
            result = pool.download_to_workspace(skill.name, workspace, overwrite=False)
            if result.get("success"):
                installed += 1
            enable_result = service.enable_skill(skill.name)
            if enable_result.get("success"):
                enabled += 1
        print(f"  Agent {agent_id}: installed/verified {installed}, enabled {enabled}")


def main() -> None:
    print("Syncing and enabling StarMind extensions...")
    sync_plugin_tools()
    sync_skills()


if __name__ == "__main__":
    main()

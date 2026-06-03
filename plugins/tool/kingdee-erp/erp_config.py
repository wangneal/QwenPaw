# -*- coding: utf-8 -*-
"""Multi-backend ERP connection configuration manager.

Storage: plugin_data/erp/configs/{backend_name}.json
Each backend (kingdee, yonyou, dingtalk, etc.) has its own config file.

Architecture:
- ConfigManager: Read/write per-backend config from JSON files
- Backend registry: Each backend declares its name, label, config_fields
- HTTP API: /api/erp/config/* for frontend CRUD
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 存储路径 ──────────────────────────────────────────────

def _get_config_dir() -> Path:
    """获取配置存储目录，如果不存在则创建。"""
    base = os.environ.get("QWENPAW_WORKING_DIR", os.path.expanduser("~/.qwenpaw"))
    config_dir = Path(base) / "plugin_data" / "erp" / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _get_config_path(backend_name: str) -> Path:
    """获取指定后端的配置文件路径。"""
    return _get_config_dir() / f"{backend_name}.json"


# ── 配置管理器 ────────────────────────────────────────────

class ConfigManager:
    """多后端 ERP 连接配置管理器

    后端在插件启动时注册。每个后端提供：
    - name: 唯一标识符（如 "kingdee"）
    - label: 显示名称（如 "金蝶云星空"）
    - config_fields: 配置界面的字段定义列表
    - test_connection: 可选的异步连接测试函数
    """

    _backends: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def register_backend(
        cls,
        name: str,
        label: str,
        config_fields: List[Dict[str, Any]],
        test_connection=None,
        icon: str = "🔧",
    ):
        """注册后端及其配置元数据

        Args:
            name: 后端唯一标识符（小写，如 "kingdee"）
            label: 显示名称（如 "金蝶云星空"）
            config_fields: 配置字段定义列表
            test_connection: 可选的异步连接测试函数(config: dict) -> dict
            icon: 显示图标
        """
        with cls._lock:
            cls._backends[name] = {
                "name": name,
                "label": label,
                "config_fields": config_fields,
                "test_connection": test_connection,
                "icon": icon,
            }
        logger.info(f"已注册配置后端: {name} ({label})")

    @classmethod
    def list_backends(cls) -> List[Dict[str, Any]]:
        """列出所有已注册后端及其配置状态

        Returns:
            包含 name, label, icon, config_fields, configured 的字典列表
        """
        with cls._lock:
            backends_snapshot = dict(cls._backends)
        result = []
        for name, meta in backends_snapshot.items():
            config = cls.get_config(name)
            # 检查后端是否有真实的配置值
            configured = bool(config and any(
                v for k, v in config.items()
                if k in ("server_url", "acct_id", "app_id", "api_key", "base_url")
            ))
            result.append({
                "name": name,
                "label": meta["label"],
                "icon": meta["icon"],
                "config_fields": meta["config_fields"],
                "configured": configured,
            })
        return result

    @classmethod
    def get_config(cls, backend_name: str) -> Dict[str, Any]:
        """从 JSON 文件读取指定后端的配置

        如果未配置则返回空字典。
        """
        with cls._lock:
            path = _get_config_path(backend_name)
            if not path.exists():
                return {}
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception as e:
                logger.error(f"读取 {backend_name} 配置失败: {e}")
                return {}

    @classmethod
    def save_config(cls, backend_name: str, config: Dict[str, Any]) -> None:
        """保存指定后端的配置到 JSON 文件

        同时同步到 QwenPaw 原生工具配置以保持向后兼容
        （确保 Console 中的原生 ToolConfigModal 仍然可用）。
        """
        with cls._lock:
            path = _get_config_path(backend_name)
            path.parent.mkdir(parents=True, exist_ok=True)

            # 日志中脱敏密码字段
            log_config = {
                k: ("***" if k in ("app_secret", "api_key", "secret", "password", "token") and v else v)
                for k, v in config.items()
            }
            logger.info(f"正在保存 {backend_name} 配置: {log_config}")

            path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

        # 同步到 QwenPaw 原生工具配置以保持向后兼容（锁外执行，避免嵌套持锁）
        cls._sync_to_qwenpaw(backend_name, config)

    @classmethod
    def _sync_to_qwenpaw(cls, backend_name: str, config: Dict[str, Any]) -> None:
        """同步配置到 QwenPaw 的 agent.json 以保持向后兼容

        确保使用 get_tool_config() 的工具在迁移期间仍然可用。
        """
        try:
            from qwenpaw.plugins import get_tool_config
            from qwenpaw.app.agent_context import get_current_agent_id

            agent_id = get_current_agent_id()
            if not agent_id:
                # 无 Agent 上下文（如前端 HTTP 路由）— 同步到默认 Agent
                agent_id = "default"

            # 查找此后端的健康检查工具
            from erp_backend import get_registry
            reg = get_registry()
            backend = reg.get(backend_name)
            if backend:
                check_tool = backend.get_health_check_tool()
                if check_tool:
                    from qwenpaw.plugins.api import PluginApi
                    from qwenpaw.plugins.registry import PluginRegistry
                    registry = PluginRegistry()
                    registry.set_tool_config(check_tool, agent_id, config)
                    logger.debug(f"已同步 {backend_name} 配置到 Agent {agent_id} 工具 {check_tool}")
        except ImportError:
            logger.debug("QwenPaw 不可用，跳过原生配置同步")
        except Exception as e:
            logger.debug(f"原生配置同步失败（非关键）: {e}")

    @classmethod
    def get_config_fields(cls, backend_name: str) -> List[Dict[str, Any]]:
        """获取指定后端的配置字段定义"""
        meta = cls._backends.get(backend_name)
        if meta:
            return meta["config_fields"]
        return []

    @classmethod
    async def test_connection(cls, backend_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试指定后端的连接

        Returns:
            包含 success (bool), message (str), details (optional dict) 的字典
        """
        meta = cls._backends.get(backend_name)
        if not meta:
            return {"success": False, "message": f"未知后端: {backend_name}"}

        test_fn = meta.get("test_connection")
        if not test_fn:
            return {"success": False, "message": f"后端 {meta['label']} 未实现连接测试"}

        try:
            result = await test_fn(config)
            if isinstance(result, dict):
                return result
            return {"success": bool(result), "message": "连接成功" if result else "连接失败"}
        except ValueError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"连接测试失败: {e}"}

    @classmethod
    def migrate_from_qwenpaw(cls, backend_name: str) -> bool:
        """从 QwenPaw 的 agent.json 迁移配置到我们的 JSON 文件

        在一键部署时调用，以保留现有配置。

        Returns:
            如果发生迁移则返回 True，如果跳过则返回 False
        """
        # 如果已有配置则跳过
        existing = cls.get_config(backend_name)
        if existing and any(v for k, v in existing.items()
                           if k in ("server_url", "acct_id", "app_id", "api_key")):
            logger.debug(f"{backend_name}: 已有配置，跳过迁移")
            return False

        # 尝试从 QwenPaw 原生存储读取
        try:
            from qwenpaw.plugins import get_tool_config
            from erp_backend import get_registry
            reg = get_registry()
            backend = reg.get(backend_name)
            if backend:
                check_tool = backend.get_health_check_tool()
                if check_tool:
                    cfg = get_tool_config(check_tool)
                    if cfg and any(v for k, v in cfg.items()
                                  if k in ("server_url", "acct_id", "app_id")):
                        cls.save_config(backend_name, cfg)
                        logger.info(f"已从 QwenPaw 原生存储迁移 {backend_name} 配置")
                        return True
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"从 QwenPaw 迁移失败: {e}")

        # 回退：直接从 agent.json 读取
        try:
            working_dir = os.environ.get("QWENPAW_WORKING_DIR", os.path.expanduser("~/.qwenpaw"))
            default_json = Path(working_dir) / "workspaces" / "default" / "agent.json"
            if default_json.exists():
                data = json.loads(default_json.read_text(encoding="utf-8"))
                from erp_backend import get_registry
                reg = get_registry()
                backend = reg.get(backend_name)
                if backend:
                    check_tool = backend.get_health_check_tool()
                    if check_tool:
                        tool_cfg = (data.get("tools", {})
                                    .get("builtin_tools", {})
                                    .get(check_tool, {})
                                    .get("config", {}))
                        if tool_cfg and any(v for k, v in tool_cfg.items()
                                            if k in ("server_url", "acct_id", "app_id")):
                            cls.save_config(backend_name, tool_cfg)
                            logger.info(f"已从 agent.json 回退迁移 {backend_name} 配置")
                            return True
        except Exception as e:
            logger.debug(f"从 agent.json 迁移失败: {e}")

        return False


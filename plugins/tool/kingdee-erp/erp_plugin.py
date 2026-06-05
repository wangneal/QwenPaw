# -*- coding: utf-8 -*-
"""ERP 工具插件入口

多后端架构：将所有已注册的 ERP 后端（金蝶、SAP 等）的工具和路由注册到 QwenPaw Agent 工具包中。

QwenPaw 通过 importlib.util.spec_from_file_location 加载此文件，
因此必须将插件目录添加到 sys.path 以支持子模块导入。
"""

import asyncio
import logging
import os
import sys

# 确保插件根目录在 sys.path 中，支持子包相互导入
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from qwenpaw.plugins.api import PluginApi
from erp_backend import get_registry
from erp_config import ConfigManager
from backends.kingdee import KingdeeBackend
from backends.kingdee_flagship import KingdeeFlagshipBackend

logger = logging.getLogger(__name__)


class ERPToolPlugin:
    """ERP Tools Plugin - multi-backend architecture."""

    def register(self, api: PluginApi):
        reg = get_registry()

        # 注册后端（防重复）
        if not reg.get("kingdee"):
            kingdee = KingdeeBackend()
            reg.register(kingdee)
        if not reg.get("kingdee_flagship"):
            flagship = KingdeeFlagshipBackend()
            reg.register(flagship)

        # 各后端的 icon（从各自 config_fields 模块常量取）
        _BACKEND_ICONS = {
            "kingdee": "🦋",
            "kingdee_flagship": "🌟",
        }

        # 注册后端到 ConfigManager（多厂商配置管理）
        for name, backend in reg.get_all().items():
            ConfigManager.register_backend(
                name=name,
                label=backend.display_name,
                config_fields=backend.config_fields,
                test_connection=backend.test_connection,
                icon=_BACKEND_ICONS.get(name, ""),
            )

        # Register tools and routes from all backends
        for name, backend in reg.get_all().items():
            backend.register_tools(api)
            backend.register_routes(api)

        # 配置路由已移至 backend.py register_routes() 中注册
        # (与 erp-permissions 路由放在一起，确保正确挂载)

        # Register startup health check hooks
        async def _health_check():
            try:
                for name, backend in reg.get_all().items():
                    cfg = ConfigManager.get_config(name)
                    if not cfg:
                        continue
                    if asyncio.iscoroutinefunction(backend.health_check):
                        ok = await backend.health_check(cfg)
                    else:
                        ok = backend.health_check(cfg)
                    status = "✅ 连接正常" if ok else "❌ 连接失败"
                    logger.info(f"{backend.display_name} WebAPI {status}")
            except Exception as e:
                logger.warning(f"Health check skipped: {e}")

        api.register_startup_hook("erp_health_check", _health_check, priority=80)

        # Register integration tools (cross-system glue tools)
        try:
            from integration.tools import erp_unified_query, erp_compare_data
            api.register_tool(
                tool_name="erp_unified_query",
                tool_func=erp_unified_query,
                description="跨ERP统一查询：同时查询多个ERP系统并合并结果",
                icon="🌐",
            )
            api.register_tool(
                tool_name="erp_compare_data",
                tool_func=erp_compare_data,
                description="跨ERP数据比对：对比两个ERP系统中的同类数据差异",
                icon="⚖️",
            )
            logger.info("Integration tools registered (2 glue tools)")
        except Exception as e:
            logger.warning(f"Integration tools skipped: {e}")

        logger.info(f"ERP 工具插件已注册 ({len(reg.list_all())} 个后端)")


# 导出插件实例
plugin = ERPToolPlugin()

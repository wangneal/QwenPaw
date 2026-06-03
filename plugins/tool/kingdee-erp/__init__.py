# -*- coding: utf-8 -*-
"""QwenPaw ERP 工具插件 - 多后端架构

可扩展的 ERP 工具插件，支持金蝶、SAP、Oracle 等。
"""

import os
import sys

# 确保插件根目录在 sys.path 中，支持绝对导入
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from erp_backend import ERPBackend, BackendRegistry, get_registry
from erp_permissions import PermissionManager, check_query_permission, check_write_permission

__all__ = [
    "ERPBackend", "BackendRegistry", "get_registry",
    "PermissionManager", "check_query_permission", "check_write_permission",
]

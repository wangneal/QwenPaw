# -*- coding: utf-8 -*-
"""金蝶业务域定义 — 从本地数据库查询结果动态加载。

每个业务域对应一组 FormId 前缀，用于权限过滤。
默认映射从 metadata/domain_map.json 读取（从金蝶 SQL Server T_META_OBJECTTYPE 实查）。
支持用户通过插件配置自定义覆盖。
"""

import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

# 元数据文件路径（从金蝶数据库实查生成）
_METADATA_DIR = os.path.join(os.path.dirname(__file__), "metadata")
_DOMAIN_MAP_FILE = os.path.join(_METADATA_DIR, "domain_map.json")

# 基础资料前缀（任何域都可以访问）
BASE_PREFIXES = ["BD_"]


def _load_domain_map() -> Dict[str, List[str]]:
    """从 domain_map.json 加载业务域 → FormId 前缀映射。"""
    if not os.path.exists(_DOMAIN_MAP_FILE):
        logger.warning(f"域映射文件不存在: {_DOMAIN_MAP_FILE}，使用空映射")
        return {}

    try:
        with open(_DOMAIN_MAP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            logger.info(f"从域映射文件加载: {list(data.keys())}")
            return data
        return {}
    except Exception as e:
        logger.error(f"加载域映射失败: {e}")
        return {}


def _merge_custom_domains(base: Dict[str, List[str]], custom_json: str) -> Dict[str, List[str]]:
    """合并用户自定义业务域映射。

    custom_json 格式: {"finance": ["GL_","AR_"], "custom_domain": ["XX_","YY_"]}
    用户自定义的域会覆盖或新增到基础映射中。
    """
    if not custom_json:
        return base
    try:
        custom = json.loads(custom_json)
        if not isinstance(custom, dict):
            return base
        merged = base.copy()
        for domain, prefixes in custom.items():
            if isinstance(prefixes, list):
                merged[domain] = prefixes
        return merged
    except (json.JSONDecodeError, TypeError):
        return base


# 模块级缓存
_domain_map: Dict[str, List[str]] = {}


def get_domain_map(custom_json: str = "") -> Dict[str, List[str]]:
    """获取业务域映射（带缓存）。

    Args:
        custom_json: 用户自定义域映射 JSON 字符串（可选）

    Returns:
        域名 → FormId 前缀列表
    """
    global _domain_map
    if not _domain_map:
        _domain_map = _load_domain_map()
    if custom_json:
        return _merge_custom_domains(_domain_map, custom_json)
    return _domain_map


def reload_domain_map():
    """强制重新加载业务域映射（用于配置变更后）。"""
    global _domain_map
    _domain_map = {}

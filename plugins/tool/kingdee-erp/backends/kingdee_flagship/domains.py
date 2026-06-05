# -*- coding: utf-8 -*-
"""金蝶云星空旗舰版业务域定义 — 复用经典版的域映射"""

# 直接复用经典版的业务域映射和基础资料前缀
from backends.kingdee.domains import get_domain_map, BASE_PREFIXES, reload_domain_map

__all__ = ["get_domain_map", "BASE_PREFIXES", "reload_domain_map"]

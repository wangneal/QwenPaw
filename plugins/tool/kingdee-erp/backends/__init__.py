# -*- coding: utf-8 -*-
"""ERP Backend implementations.

Each subpackage implements the ERPBackend protocol for a specific ERP system.
"""

from .kingdee import KingdeeBackend
from .kingdee_flagship import KingdeeFlagshipBackend

__all__ = ["KingdeeBackend", "KingdeeFlagshipBackend"]

# -*- coding: utf-8 -*-
"""ERP Backend implementations.

Each subpackage implements the ERPBackend protocol for a specific ERP system.
"""

from .kingdee import KingdeeBackend

__all__ = ["KingdeeBackend"]

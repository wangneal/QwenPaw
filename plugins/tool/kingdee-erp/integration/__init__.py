# -*- coding: utf-8 -*-
"""Integration tools - cross-system glue tools.

Lightweight integration approach: 2 glue tools + Skill-driven patterns.
The Agent IS the pipeline - tools just provide fan-out/merge and comparison.
"""

from .tools import erp_unified_query, erp_compare_data

__all__ = ["erp_unified_query", "erp_compare_data"]
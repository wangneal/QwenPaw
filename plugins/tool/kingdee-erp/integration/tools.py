# -*- coding: utf-8 -*-
"""跨系统整合工具

两个胶水工具用于轻量级整合：
1. erp_unified_query: 扇出查询多个 ERP 系统，合并结果
2. erp_compare_data: 比较两个 ERP 系统的数据

Agent 将这些与 Skill 文件结合使用，处理复杂的多步骤场景。
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse
from erp_backend import get_registry

logger = logging.getLogger(__name__)


def _get_registry():
    return get_registry()


def _parse_systems(systems: str) -> List[str]:
    """Parse comma-separated systems string to list."""
    if not systems:
        return []
    return [s.strip() for s in systems.split(",") if s.strip()]


def _parse_query_params(query_params: str) -> Dict[str, Any]:
    """Parse JSON query params string to dict."""
    if not query_params:
        return {}
    try:
        return json.loads(query_params)
    except json.JSONDecodeError as e:
        logger.debug("查询参数JSON解析失败: %s", e)
        return {}


async def erp_unified_query(
    systems: str,
    query_params: str,
    limit: int = 100,
) -> ToolResponse:
    """跨ERP统一查询：同时查询多个ERP系统并合并结果。

    使用场景：
    - 同时查金蝶和SAP的应收账款
    - 汇总多系统的库存数据
    - 统一查询多ERP的客户信息

    Args:
        systems: 目标系统列表，逗号分隔（如 "kingdee,sap"），空=查所有已配置系统
        query_params: 查询参数，JSON字符串格式，如 '{"form_id":"AR_receivable","field_keys":"FNumber,FName","filter":"FDate>=''2026-01-01''"}'
        limit: 每个系统返回的最大记录数，默认100

    Returns:
        ToolResponse with merged results from all systems
    """
    reg = _get_registry()
    available = reg.list_all()
    target_systems = _parse_systems(systems) if systems else available
    params = _parse_query_params(query_params)

    results = {}
    errors = {}

    for sys_name in target_systems:
        if sys_name not in available:
            errors[sys_name] = f"系统 '{sys_name}' 未注册"
            continue
        backend = reg.get(sys_name)
        try:
            from erp_config import ConfigManager
            cfg = ConfigManager.get_config(sys_name)
            if not cfg:
                errors[sys_name] = f"{backend.display_name} 未配置连接信息"
                continue
            client = backend.get_client(cfg)
            form_id = params.get("form_id", "")
            field_keys = params.get("field_keys", "")
            filter_string = params.get("filter", "")
            top = min(params.get("top", limit), limit)
            if form_id and field_keys:
                data = await client.execute_bill_query(
                    form_id, field_keys, filter_string, "", top
                )
                results[sys_name] = {
                    "system": backend.display_name,
                    "count": len(data) if isinstance(data, list) else 0,
                    "data": data[:limit] if isinstance(data, list) else data,
                }
            else:
                errors[sys_name] = "缺少 form_id 或 field_keys 参数"
        except Exception as e:
            errors[sys_name] = str(e)

    # Format output
    lines = [f"统一查询结果（{len(target_systems)} 个系统）：\n"]
    for sys_name, data in results.items():
        backend = reg.get(sys_name)
        lines.append(f"## {backend.display_name} ({sys_name})")
        lines.append(f"  返回 {data['count']} 条记录")
        if data.get("data"):
            lines.append(f"  示例: {json.dumps(data['data'][:3], ensure_ascii=False)}")
        lines.append("")
    if errors:
        lines.append("## 错误")
        for sys_name, err in errors.items():
            lines.append(f"  {sys_name}: {err}")

    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])


async def erp_compare_data(
    left_system: str,
    left_query: str,
    right_system: str,
    right_query: str,
    key_field: str,
    compare_fields: str = "",
) -> ToolResponse:
    """跨ERP数据比对：对比两个ERP系统中的同类数据差异。

    使用场景：
    - 金蝶 vs SAP 应收账款对账
    - 跨系统库存数量比对
    - 客户主数据一致性检查

    Args:
        left_system: 左侧系统名称（如 "kingdee"）
        left_query: 左侧查询参数，JSON字符串，如 '{"form_id":"AR_receivable","field_keys":"FNumber,FAmount"}'
        right_system: 右侧系统名称（如 "sap"）
        right_query: 右侧查询参数，JSON字符串
        key_field: 用于匹配的关键字段名（如 "FNumber"）
        compare_fields: 要比对的字段列表，逗号分隔（如 "FAmount,FQty"），空=比对所有共同字段

    Returns:
        ToolResponse with comparison results
    """
    reg = _get_registry()

    # Validate systems
    for sys_name in [left_system, right_system]:
        if sys_name not in reg.list_all():
            return ToolResponse(content=[TextBlock(type="text", text=f"系统 '{sys_name}' 未注册。可用: {reg.list_all()}")])

    # Parse query params
    left_params = _parse_query_params(left_query)
    right_params = _parse_query_params(right_query)
    compare_fields_list = [f.strip() for f in compare_fields.split(",") if f.strip()] if compare_fields else []

    # Query both systems
    results = {}
    for sys_name, params in [(left_system, left_params), (right_system, right_params)]:
        backend = reg.get(sys_name)
        try:
            from erp_config import ConfigManager
            cfg = ConfigManager.get_config(sys_name)
            if not cfg:
                results[sys_name] = {"error": f"{backend.display_name} 未配置"}
                continue
            client = backend.get_client(cfg)
            form_id = params.get("form_id", "")
            field_keys = params.get("field_keys", "")
            filter_str = params.get("filter", "")
            top = params.get("top", 500)
            if form_id and field_keys:
                data = await client.execute_bill_query(form_id, field_keys, filter_str, "", top)
                results[sys_name] = {
                    "system": backend.display_name,
                    "count": len(data) if isinstance(data, list) else 0,
                    "data": data if isinstance(data, list) else [],
                }
            else:
                results[sys_name] = {"error": "缺少 form_id 或 field_keys"}
        except Exception as e:
            results[sys_name] = {"error": str(e)}

    # Compare
    lines = [f"数据比对：{left_system} vs {right_system}\n"]
    lines.append(f"关键字段: {key_field}")
    if compare_fields_list:
        lines.append(f"比对字段: {', '.join(compare_fields_list)}")
    lines.append("")

    data_left = results.get(left_system, {}).get("data", [])
    data_right = results.get(right_system, {}).get("data", [])

    if isinstance(data_left, list) and isinstance(data_right, list):
        lines.append(f"  {left_system}: {len(data_left)} 条")
        lines.append(f"  {right_system}: {len(data_right)} 条")
        diff = abs(len(data_left) - len(data_right))
        if diff == 0:
            lines.append("  ✅ 记录数一致")
        else:
            lines.append(f"  ⚠️ 记录数差异: {diff} 条")

        # Build lookup by key_field
        left_map = {}
        for row in data_left:
            if isinstance(row, dict) and key_field in row:
                left_map[row[key_field]] = row
        right_map = {}
        for row in data_right:
            if isinstance(row, dict) and key_field in row:
                right_map[row[key_field]] = row

        # Find differences
        only_left = set(left_map.keys()) - set(right_map.keys())
        only_right = set(right_map.keys()) - set(left_map.keys())
        common_keys = set(left_map.keys()) & set(right_map.keys())

        if only_left:
            lines.append(f"\n  仅在 {left_system}: {len(only_left)} 条")
            lines.append(f"    示例: {list(only_left)[:5]}")
        if only_right:
            lines.append(f"\n  仅在 {right_system}: {len(only_right)} 条")
            lines.append(f"    示例: {list(only_right)[:5]}")

        # Compare common records
        value_diffs = []
        for k in list(common_keys)[:20]:  # Limit to 20 for summary
            left_row = left_map[k]
            right_row = right_map[k]
            fields_to_check = compare_fields_list if compare_fields_list else set(left_row.keys()) & set(right_row.keys())
            for field in fields_to_check:
                if field == key_field:
                    continue
                left_val = left_row.get(field)
                right_val = right_row.get(field)
                if left_val != right_val:
                    value_diffs.append({
                        "key": k,
                        "field": field,
                        "left": left_val,
                        "right": right_val,
                    })

        if value_diffs:
            lines.append(f"\n  值差异: {len(value_diffs)} 处")
            for d in value_diffs[:5]:
                lines.append(f"    {d['key']}.{d['field']}: {d['left']} vs {d['right']}")
    else:
        for sys_name in [left_system, right_system]:
            err = results.get(sys_name, {}).get("error", "未知错误")
            if err:
                lines.append(f"  {sys_name} 错误: {err}")

    lines.append("\n💡 提示：详细对账请让Agent按Skill分步执行（先查各系统明细→按关键字段匹配→标记差异项）")

    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

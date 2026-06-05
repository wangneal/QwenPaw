# -*- coding: utf-8 -*-
"""Kingdee tool functions for QwenPaw Agent.

All tools use kingdee_ prefix naming convention.
All write/query tools require org_id for per-org permission control.
"""

import asyncio
import hashlib
import json
import logging
import os
from typing import Optional

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from .sdk import KingdeeClient, _logger as sdk_logger
from erp_config import ConfigManager
from erp_permissions import (
    PermissionManager,
    check_operation_permission,
    filter_fields_by_permission,
)

try:
    from qwenpaw.plugins import get_tool_config
except ImportError:
    get_tool_config = None

try:
    from qwenpaw.app.agent_context import get_current_channel, get_current_user_id
except ImportError:
    get_current_channel = None
    get_current_user_id = None

logger = logging.getLogger(__name__)

# 延迟初始化的全局变量（受 asyncio.Lock 保护）
_client = None
_client_lock = asyncio.Lock()
_perm_mgr = None
_perm_mgr_lock = asyncio.Lock()


async def _get_client():
    """获取金蝶客户端（双重检查锁防竞态）

    配置读取优先级：
    1. ConfigManager 自管 JSON 文件（多厂商框架）
    2. QwenPaw get_tool_config()（回退兼容）
    """
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is not None:
            return _client

        # 1. 优先：自管 JSON
        cfg = ConfigManager.get_config("kingdee")

        # 2. 回退：QwenPaw get_tool_config（兼容旧配置，见 AGENTS.md）
        if not cfg or not any(v for k, v in cfg.items() if k in ("server_url", "acct_id", "app_id")):
            if get_tool_config is not None:
                try:
                    cfg = get_tool_config("kingdee_query_bill")
                except Exception as e:
                    logger.debug("get_tool_config 回退失败: %s", e)

        if not cfg:
            raise RuntimeError(
                "金蝶插件未配置。请在管理页面 → 连接配置 中填写金蝶 WebAPI 连接信息。"
            )
        _client = KingdeeClient(
            server_url=cfg["server_url"], acct_id=cfg["acct_id"],
            user_name=cfg["user_name"], app_id=cfg["app_id"],
            app_secret=cfg["app_secret"],
        )
        logger.info("Kingdee client created: %s", cfg["server_url"])
    return _client


def reset_client():
    """Reset the cached client (for testing/reconfiguration)."""
    global _client
    _client = None


async def _get_perm_mgr():
    """获取权限管理器（双重检查锁防竞态）"""
    global _perm_mgr
    if _perm_mgr is not None:
        return _perm_mgr
    async with _perm_mgr_lock:
        if _perm_mgr is not None:
            return _perm_mgr
        _perm_mgr = PermissionManager()
    return _perm_mgr


def _identity():
    if get_current_channel is None or get_current_user_id is None:
        return ("unknown", "unknown")
    try:
        return (get_current_channel() or "unknown",
                get_current_user_id() or "unknown")
    except (RuntimeError, ValueError, AttributeError) as e:
        logger.debug("获取用户身份失败: %s", e)
        return ("unknown", "unknown")


def _op_tag(ch: str, uid: str) -> str:
    """Generate operator tag for audit trail in ToolResponse."""
    return f"\n\n[操作人: {ch}:{uid}]"


async def _audit(pm, ch: str, uid: str, action: str, form_id: str, target: str = "", detail: str = ""):
    """写入审计日志（异步）。"""
    try:
        await pm.log_operation(
            operator=f"{ch}:{uid}",
            action=action,
            form_id=form_id,
            target=target,
            detail=detail,
        )
    except Exception as e:
        logger.warning("审计日志写入失败: %s", e)


def _get_context():
    """获取当前调用者身份（渠道:用户ID）。"""
    ch = ""
    uid = ""
    if get_current_channel:
        try:
            ch = get_current_channel() or ""
        except Exception:
            pass
    if get_current_user_id:
        try:
            uid = get_current_user_id() or ""
        except Exception:
            pass
    return ch, uid


def _build_write_preview(action: str, form_id: str, org_id, details: dict, warning: str = "") -> ToolResponse:
    """构建写入操作预览摘要。第一次调用（execute=False）时返回此预览，不执行实际操作。

    这是防幻觉的硬性防护：无论模型是否遵守文字指令，
    代码层面第一次调用永远只返回预览，不可能执行写入。
    """
    lines = [
        "⚠️ 写入操作预览（尚未执行）",
        "",
        f"📋 操作类型：{action}",
        f"📄 目标表单：{form_id}",
        f"🏢 组织ID：{org_id}",
        "",
        "📝 操作详情：",
    ]
    for k, v in details.items():
        lines.append(f"  • {k}：{v}")

    if warning:
        lines.extend(["", f"🚨 {warning}"])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "如确认执行，请再次调用本工具并设置 execute=True",
        "如需修改，请调整参数后重新调用（execute=False）",
    ])

    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])


def _fmt_table(headers, rows):
    if not rows:
        return "查询结果为空。"
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, v in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(v)))
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    hdr = "| " + " | ".join(str(h).ljust(w) for h, w in zip(headers, widths)) + " |"
    lines = [sep, hdr, sep]
    for row in rows:
        cells = [str(row[i] if i < len(row) else "").ljust(widths[i])
                 for i in range(len(widths))]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append(sep)
    return "\n".join(lines)


# ======== 组织发现工具 ========

async def kingdee_list_user_orgs() -> ToolResponse:
    """查询当前用户有权限的组织列表。在操作单据前必须先调用此工具确定组织。"""
    ch, uid = _identity()
    logger.info("[Tool] kingdee_list_user_orgs caller=%s:%s", ch, uid)
    pm = await _get_perm_mgr()
    key = f"{ch}:{uid}"
    orgs = pm.list_user_orgs(key)

    if not orgs:
        return ToolResponse(content=[TextBlock(type="text", text=(
            f"您的权限尚未配置（身份: {key}）。\n"
            "请联系管理员在 QwenPaw 管理页面配置您的权限。"
        ))])

    # 从金蝶查询组织名称
    org_ids = [o["org_id"] for o in orgs if o["org_id"] != "*"]
    org_name_map = {}
    try:
        client = await _get_client()
        org_name_map = await client.get_org_names(org_ids)
    except Exception as e:
        logger.warning("Failed to query org names: %s", e)

    lines = [f"您有权限的组织（共 {len(orgs)} 个）：\n"]
    lines.append(f"{'组织编号':<10} {'组织名称':<20} {'业务域':<25} {'访问级别'}")
    lines.append("-" * 70)
    for o in orgs:
        org_id = o["org_id"]
        display_id = org_id if org_id != "*" else "(全部)"
        org_name = org_name_map.get(org_id, "") if org_id != "*" else "(不限)"
        domains = ", ".join(o["domains"]) if o["domains"] else "(无限制)"
        access = "读写" if o["access"] == "writeable" else "只读"
        lines.append(f"{display_id:<10} {org_name:<20} {domains:<25} {access}")

    lines.append("\n操作单据时请指定 org_id 参数。")
    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])


# ======== 查询工具 ========

async def kingdee_query_bill(
    form_id: str, field_keys: str, org_id: str,
    filter_string: str = "", order_string: str = "",
    top_row_count: int = 100,
) -> ToolResponse:
    """查询金蝶单据数据（销售订单、采购订单、物料、客户等）。

    ⚠️ 防幻觉规则：
    1. 不确定FormId时，必须先调用kingdee_search_form搜索，不得猜测
    2. 不确定字段名时，必须先调用kingdee_query_metadata查询，不得猜测
    3. 不得编造或猜测过滤值（如客户名、供应商名），不确定时先用模糊查询确认
    4. 查询结果为空时如实告知用户，不得编造替代答案
    5. 回答时引用具体查询结果，标注数据来源

    Args:
        form_id: 单据FormId（如 SAL_SaleOrder, AR_Receivable, BD_Material）。不得猜测，不确定时先调用kingdee_search_form
        field_keys: 查询字段，逗号分隔（如 FDate,FCustId.FName,FQty）。不得猜测，不确定时先调用kingdee_query_metadata
        org_id: 组织ID（必填，先调用 kingdee_list_user_orgs 获取可用组织，不得编造）
        filter_string: 过滤条件（如 FDate >= '2026-05-01'）。过滤值必须是精确值，不确定时先模糊查询确认
        order_string: 排序（如 FDate DESC）
        top_row_count: 最大返回行数
    """
    ch, uid = _identity()
    logger.info("[Tool] kingdee_query_bill caller=%s:%s form_id=%s org=%s fields=%s",
                ch, uid, form_id, org_id, field_keys[:60])
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "query")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    # 行级过滤注入：解析并合并 FilterString
    row_filter = resolve_row_filter(pm, f"{ch}:{uid}", org_id, form_id)
    if row_filter:
        if filter_string:
            filter_string = f"({filter_string}) AND ({row_filter})"
        else:
            filter_string = row_filter

    try:
        client = await _get_client()
        result = await client.execute_bill_query(
            form_id, field_keys, filter_string, order_string, top_row_count,
        )
        if not result:
            return ToolResponse(content=[TextBlock(type="text", text=f"查询 {form_id} (组织:{org_id}) 无数据。{EMPTY_RESULT_SUFFIX}")])

        # 字段级权限过滤：将行数据转为 dict → 过滤 → 转回行数据
        headers = field_keys.split(",")
        key = f"{ch}:{uid}"
        filtered_rows = []
        for row in result:
            row_dict = dict(zip(headers, row))
            row_dict = filter_fields_by_permission(pm, key, org_id, form_id, row_dict)
            filtered_rows.append([row_dict.get(h, "") for h in headers])
        # 更新表头：移除 hidden 字段（过滤后不存在的字段）
        visible_headers = [h for h in headers if h in (filtered_rows[0] if filtered_rows else {})]
        # 重建 filtered_rows 只保留 visible 字段
        if filtered_rows and len(visible_headers) != len(headers):
            header_idx = {h: i for i, h in enumerate(headers)}
            filtered_rows = [
                [row[header_idx[h]] for h in visible_headers]
                for row in filtered_rows
            ]
            headers = visible_headers

        table = _fmt_table(headers, filtered_rows)
        return ToolResponse(content=[TextBlock(type="text", text=f"查询 {form_id} (组织:{org_id})，共 {len(filtered_rows)} 条：\n\n{table}")])
    except Exception as e:
        logger.error("kingdee_query_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"查询失败: {e}")])


async def kingdee_view_bill(form_id: str, org_id: str, number: str = "", bill_id: str = "") -> ToolResponse:
    """查看金蝶单据完整详情。

    ⚠️ 防幻觉规则：单据编号必须来自查询结果或用户明确提供，不得编造或猜测。

    Args:
        form_id: 单据FormId（不得猜测，不确定时先调用kingdee_search_form）
        org_id: 组织ID（必填，来自kingdee_list_user_orgs查询结果，不得编造）
        number: 单据编号（必须来自查询结果或用户明确提供，不得猜测）
        bill_id: 单据内码（与number二选一，必须来自查询结果）
    """
    ch, uid = _identity()
    logger.info("[Tool] kingdee_view_bill caller=%s:%s form_id=%s org=%s number=%s",
                ch, uid, form_id, org_id, number)
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "view")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])
    try:
        client = await _get_client()
        result = await client.view_bill(form_id, number=number, bill_id=bill_id)
        # 字段级权限过滤
        if isinstance(result, dict):
            key = f"{ch}:{uid}"
            result = filter_fields_by_permission(pm, key, org_id, form_id, result)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"单据详情 ({form_id}, 组织:{org_id}):\n\n{text[:8000]}")])
    except Exception as e:
        logger.error("kingdee_view_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"查看失败: {e}")])


async def kingdee_get_report(
    form_id: str, org_id: str, scheme_id: str = "",
    field_keys: str = "", start_row: int = 0, limit: int = 2000,
    quickly_conditions: str = "",
) -> ToolResponse:
    """查询金蝶报表数据。

    ⚠️ 防幻觉规则：form_id和scheme_id不得猜测，不确定时查看报表文档或询问用户。

    支持两种模式：
    1. 标准报表（利润表、资产负债表等）：提供 field_keys，通过 Model 传参
    2. 分页账表（收发存汇总、物料收发明细等）：提供 scheme_id + quickly_conditions

    Args:
        form_id: 报表FormId（不得猜测，如 GLR_AccoutBalance, HS_INOUTSTOCKSUMMARYRPT, STK_StockDetailRpt）
        org_id: 组织ID（必填，来自kingdee_list_user_orgs查询结果，不得编造）
        scheme_id: 过滤方案ID（分页账表必填，查 T_BAS_FILTERSCHEME.FSCHEMEID）
        field_keys: 查询字段（标准报表用，逗号分隔）
        start_row: 起始行
        limit: 最大行数
        quickly_conditions: 快速过滤条件JSON（分页账表用）
            格式: [{"FieldName":"BeginDate","FieldValue":"2026-01-01"},{"FieldName":"EndDate","FieldValue":"2026-12-31"}]
    """
    ch, uid = _identity()
    logger.info("[Tool] kingdee_get_report caller=%s:%s form_id=%s org=%s scheme=%s",
                ch, uid, form_id, org_id, scheme_id)
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "report")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])
    try:
        client = await _get_client()

        # 分页账表模式：有 scheme_id 时使用
        if scheme_id:
            qc = None
            if quickly_conditions:
                qc = json.loads(quickly_conditions) if isinstance(quickly_conditions, str) else quickly_conditions
            result = await client.get_report_paged(form_id, scheme_id, qc)
        else:
            # 标准报表模式
            params = {
                "FORMID": form_id, "FSCHEMEID": "",
                "StartRow": str(start_row), "Limit": str(limit),
                "CurQueryId": "", "FieldKeys": field_keys,
            }
            result = await client.get_report_data(form_id, params)

        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"报表 ({form_id}, 组织:{org_id}):\n\n{text[:8000]}")])
    except Exception as e:
        logger.error("kingdee_get_report error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"报表查询失败: {e}")])


async def kingdee_get_kds_report(
    report_type: int,
    report_number: str,
    acct_system_number: str,
    acct_policy_number: str,
    currency_number: str,
    curr_unit_number: str,
    cycle_type: int,
    year: int,
    period: int,
    org_number: str = "",
    scope_type_number: str = "",
    scope_number: str = "",
    data_type: str = "Json",
) -> ToolResponse:
    """查询金蝶合并报表数据（KDS报表系统）。

    用于查询合并报表、汇总报表、工作底稿、抵消表、阿米巴报表、预算报表等。

    Args:
        report_type: 报表类型（1=个别报表, 2=穿透报表, 14=汇总报表, 15=合并报表, 16=工作底稿, 17=合并个别报表, 20=个别报表调整表, 31=抵消表, 51=阿米巴报表, 61=预算报表）
        report_number: 报表编码（如 HB00001）
        acct_system_number: 核算体系编号（如 KJHSTX01_SYS）
        acct_policy_number: 会计政策编号（如 KJZC01_SYS）
        currency_number: 币别编号（如 PRE001）
        curr_unit_number: 币别单位编号（如 JEDW01_SYS）
        cycle_type: 周期类型（1=会计期间, 2=日报, 3=周报, 4=月报, 5=季报, 6=半年报, 7=年报, 8=旬报, 10=自定义）
        year: 年份（如 2025）
        period: 期间（如 3 表示第3期）
        org_number: 组织编号（部分报表需要）
        scope_type_number: 合并方案编号（部分报表需要，如 HXX001）
        scope_number: 合并范围编号（部分报表需要，如 001）
        data_type: 数据格式（Json/Excel/Itemdata），默认 Json
    """
    ch, uid = _identity()
    logger.info("[Tool] kingdee_get_kds_report caller=%s:%s report_type=%s report_number=%s year=%s period=%s",
                ch, uid, report_type, report_number, year, period)
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", "", org_number, "report")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])
    try:
        client = await _get_client()
        parameters = {
            "ReportType": report_type,
            "ReportNumber": report_number,
            "AcctSystemNumber": acct_system_number,
            "AcctPolicyNumber": acct_policy_number,
            "CurrencyNumber": currency_number,
            "CurrUnitNumber": curr_unit_number,
            "CycleType": cycle_type,
            "Year": year,
            "Period": period,
            "DataType": data_type,
        }
        if org_number:
            parameters["OrgNumber"] = org_number
        if scope_type_number:
            parameters["ScopeTypeNumber"] = scope_type_number
        if scope_number:
            parameters["ScopeNumber"] = scope_number

        result = await client.get_kds_report_data(parameters)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"合并报表 ({report_number}, 类型:{report_type}):\n\n{text[:8000]}")])
    except Exception as e:
        logger.error("kingdee_get_kds_report error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"合并报表查询失败: {e}")])


# ======== 写入工具 ========

async def kingdee_save_bill(form_id: str, model: dict, org_id: str, execute: bool = False) -> ToolResponse:
    """保存/新增金蝶单据。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行保存
    - 用户确认后第二次调用 execute=True：执行实际保存

    ⚠️ 防幻觉规则：
    1. 所有编码值（供应商/物料/组织/部门）必须先通过查询工具获取，禁止猜测或编造
    2. 基础资料字段必须用JSON对象包裹编码，如 {"FSupplierId": {"FNumber": "S001"}}，禁止直接传字符串
    3. 写入前必须先调用kingdee_query_metadata确认字段类型和传值规则
    4. 用户指令模糊时（如"帮我新增订单"），必须追问具体参数（供应商、物料、数量等），不得自行填充缺失值

    Args:
        form_id: 单据FormId（不得猜测，不确定时先调用kingdee_search_form）
        model: 单据Model数据。基础资料字段必须用JSON对象包裹编码，
               如 {"FSupplierId": {"FNumber": "S001"}}，禁止直接传字符串。
               单据类型用FNUMBER大写，用户用FUserID，联系人用FCONTACTNUMBER。
               详见 kingdee-write-safety 技能。
        org_id: 组织ID（必填，来自kingdee_list_user_orgs查询结果，不得编造）
        execute: 是否执行保存。默认False返回预览，True时执行实际操作
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _identity()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "save")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    # 预览操作指纹
    pkey = _preview_key(form_id, org_id, model_hash=hashlib.md5(json.dumps(model, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8])

    if not execute:
        # 提取 model 中的关键字段值用于预览
        preview_details = {"单据类型": form_id, "组织ID": org_id}
        model_inner = model.get("Model", model)  # 兼容嵌套结构
        for key in ("FBillNo", "FDate", "FSupplierId", "FCustId", "FMaterialId", "FPurchaseOrgId"):
            if key in model_inner:
                val = model_inner[key]
                if isinstance(val, dict):
                    val = val.get("FNumber", val.get("FNUMBER", str(val)))
                preview_details[key] = str(val)[:100]
        _register_preview(caller, pkey)
        return _build_write_preview("保存/新增单据", form_id, org_id, preview_details)

    # 防跳步校验：必须先预览过才能执行
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到操作预览记录。这是防幻觉硬性防护——防止模型跳过确认直接执行写入。")

    try:
        client = await _get_client()
        result = await client.save_bill(form_id, model)
        await _audit(pm, ch, uid, "save", form_id, detail=str(result)[:200])
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"保存成功 ({form_id}, 组织:{org_id}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_save_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"保存失败: {e}")])


async def kingdee_delete_bill(form_id: str, org_id: str, numbers: list = None, ids: str = "", execute: bool = False) -> ToolResponse:
    """删除金蝶单据。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行删除
    - 用户确认后第二次调用 execute=True：执行实际删除

    ⚠️ 防幻觉规则：
    1. 单据编号必须来自查询结果或用户明确提供，不得猜测
    2. 仅限未审核单据
    3. 删除不可逆，预览时会显示不可逆警告

    Args:
        form_id: 单据FormId（不得猜测，不确定时先调用kingdee_search_form）
        org_id: 组织ID（必填，来自kingdee_list_user_orgs查询结果，不得编造）
        numbers: 单据编号列表（必须来自查询结果或用户明确提供）
        ids: 单据内码（与numbers二选一，必须来自查询结果）
        execute: 是否执行删除。默认False返回预览，True时执行实际操作
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _get_context()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "delete")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    pkey = _preview_key(form_id, org_id, numbers=str(numbers), ids=ids)

    if not execute:
        detail_items = {"单据编号": str(numbers or ids), "单据类型": form_id}
        _register_preview(caller, pkey)
        return _build_write_preview("删除单据", form_id, org_id, detail_items,
                                     warning="删除操作不可逆！删除后数据无法恢复！")

    # 防跳步校验
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到删除操作预览记录。")

    try:
        client = await _get_client()
        result = await client.delete_bill(form_id, numbers=numbers, ids=ids)
        await _audit(pm, ch, uid, "delete", form_id, target=target)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"删除成功 ({form_id}, 组织:{org_id}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_delete_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"删除失败: {e}")])


async def kingdee_submit_bill(form_id: str, org_id: str, numbers: list = None, ids: str = "", execute: bool = False) -> ToolResponse:
    """提交金蝶单据审批。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行提交
    - 用户确认后第二次调用 execute=True：执行实际提交

    ⚠️ 防幻觉规则：
    1. 单据编号必须来自查询结果或用户明确提供，不得猜测
    2. 用户指令模糊时（如"提交那个订单"），必须追问具体单号

    Args:
        form_id: 单据FormId（不得猜测）
        org_id: 组织ID（必填）
        numbers: 单据编号列表（必须来自查询结果）
        ids: 单据内码（与numbers二选一）
        execute: 是否执行提交。默认False返回预览
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _get_context()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "submit")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    pkey = _preview_key(form_id, org_id, numbers=str(numbers), ids=ids)

    if not execute:
        detail_items = {"单据编号": str(numbers or ids), "单据类型": form_id}
        _register_preview(caller, pkey)
        return _build_write_preview("提交单据", form_id, org_id, detail_items)

    # 防跳步校验
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到提交操作预览记录。")

    try:
        client = await _get_client()
        result = await client.submit_bill(form_id, numbers=numbers, ids=ids)
        await _audit(pm, ch, uid, "submit", form_id, target=target)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"提交成功 ({form_id}, 组织:{org_id}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_submit_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"提交失败: {e}")])


async def kingdee_audit_bill(form_id: str, org_id: str, numbers: list = None, ids: str = "", execute: bool = False) -> ToolResponse:
    """审核金蝶单据。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行审核
    - 用户确认后第二次调用 execute=True：执行实际审核

    ⚠️ 防幻觉规则：
    1. 单据编号必须来自查询结果或用户明确提供，不得猜测
    2. 审核后不可修改，需反审核后才能修改
    3. 用户指令模糊时，必须追问具体单号

    Args:
        form_id: 单据FormId（不得猜测）
        org_id: 组织ID（必填）
        numbers: 单据编号列表（必须来自查询结果）
        ids: 单据内码（与numbers二选一）
        execute: 是否执行审核。默认False返回预览
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _get_context()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "audit")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    pkey = _preview_key(form_id, org_id, numbers=str(numbers), ids=ids)

    if not execute:
        detail_items = {"单据编号": str(numbers or ids), "单据类型": form_id}
        _register_preview(caller, pkey)
        return _build_write_preview("审核单据", form_id, org_id, detail_items,
                                     warning="审核后单据不可修改，需反审核后才能修改")

    # 防跳步校验
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到审核操作预览记录。")

    try:
        client = await _get_client()
        result = await client.audit_bill(form_id, numbers=numbers, ids=ids)
        await _audit(pm, ch, uid, "audit", form_id, target=target)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"审核成功 ({form_id}, 组织:{org_id}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_audit_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"审核失败: {e}")])


async def kingdee_unaudit_bill(form_id: str, org_id: str, numbers: list = None, ids: str = "", execute: bool = False) -> ToolResponse:
    """反审核金蝶单据。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行反审核
    - 用户确认后第二次调用 execute=True：执行实际反审核

    Args:
        form_id: 单据FormId（不得猜测）
        org_id: 组织ID（必填）
        numbers: 单据编号列表（必须来自查询结果）
        ids: 单据内码（与numbers二选一）
        execute: 是否执行反审核。默认False返回预览
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _get_context()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "unaudit")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    pkey = _preview_key(form_id, org_id, numbers=str(numbers), ids=ids)

    if not execute:
        detail_items = {"单据编号": str(numbers or ids), "单据类型": form_id}
        _register_preview(caller, pkey)
        return _build_write_preview("反审核单据", form_id, org_id, detail_items)

    # 防跳步校验
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到反审核操作预览记录。")

    try:
        client = await _get_client()
        result = await client.unaudit_bill(form_id, numbers=numbers, ids=ids)
        await _audit(pm, ch, uid, "unaudit", form_id, target=target)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"反审核成功 ({form_id}, 组织:{org_id}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_unaudit_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"反审核失败: {e}")])


async def kingdee_push_bill(form_id: str, push_data: dict, org_id: str, execute: bool = False) -> ToolResponse:
    """下推金蝶单据（如销售订单→销售出库单）。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行下推
    - 用户确认后第二次调用 execute=True：执行实际下推

    ⚠️ 防幻觉规则：
    1. 必须说明源单→目标单的转换关系
    2. 源单编号和目标表单ID必须来自查询结果，不得猜测
    3. 用户指令模糊时，必须追问下推到什么目标单据

    Args:
        form_id: 源单FormId（不得猜测，不确定时先调用kingdee_search_form）
        push_data: 下推数据（必须包含源单内码，来自查询结果）
        org_id: 组织ID（必填，来自kingdee_list_user_orgs查询结果，不得编造）
        execute: 是否执行下推。默认False返回预览，True时执行实际操作
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _get_context()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "push")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    pkey = _preview_key(form_id, org_id, push_hash=hashlib.md5(json.dumps(push_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8])

    if not execute:
        detail_items = {"源单表单": form_id, "下推数据": str(push_data)[:200]}
        _register_preview(caller, pkey)
        return _build_write_preview("下推单据", form_id, org_id, detail_items)

    # 防跳步校验
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到下推操作预览记录。")

    try:
        client = await _get_client()
        result = await client.push_bill(form_id, push_data)
        await _audit(pm, ch, uid, "push", form_id, detail=str(push_data)[:200])
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"下推成功 ({form_id}, 组织:{org_id}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_push_bill error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"下推失败: {e}")])


async def kingdee_execute_operation(
    form_id: str, op_number: str, op_data: dict, org_id: str, execute: bool = False,
) -> ToolResponse:
    """执行金蝶自定义操作（禁用、启用等）。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行操作
    - 用户确认后第二次调用 execute=True：执行实际操作

    ⚠️ 防幻觉规则：
    1. op_number 和 op_data 不得猜测
    2. 用户指令模糊时，必须追问具体操作

    Args:
        form_id: 单据FormId（不得猜测）
        op_number: 操作编号（不得猜测）
        op_data: 操作数据（不得编造）
        org_id: 组织ID（必填）
        execute: 是否执行操作。默认False返回预览
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _get_context()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "execute")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    pkey = _preview_key(form_id, org_id, op_number=op_number)

    if not execute:
        detail_items = {
            "操作编号": op_number,
            "目标单据": form_id,
            "操作数据": json.dumps(op_data or {}, ensure_ascii=False)[:200],
        }
        _register_preview(caller, pkey)
        return _build_write_preview("执行自定义操作", form_id, org_id, detail_items)

    # 防跳步校验
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到自定义操作预览记录。")

    try:
        client = await _get_client()
        result = await client.execute_operation(form_id, op_number, op_data)
        await _audit(pm, ch, uid, "execute_op", form_id, target=op_number)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"操作成功 ({form_id}.{op_number}, 组织:{org_id}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_execute_operation error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"操作失败: {e}")])


async def kingdee_workflow_audit(
        form_id: str,
        org_id: int,
        numbers: list[str],
        audit_result: str,
        user_id: str,
        opinion: str = "",
        execute: bool = False
    ) -> ToolResponse:
    """工作流审批金蝶单据（通过/驳回/终止）。

    双步调用（强制）：
    - 第一次调用 execute=False（默认）：仅返回操作预览，不执行审批
    - 用户确认后第二次调用 execute=True：执行实际审批

    ⚠️ 防幻觉规则：
    1. 审批类型（通过/驳回/终止）必须由用户明确指定，不得自行决定
    2. 审批人user_id必须来自查询结果或用户明确提供，不得猜测
    3. org_id必填，必须来自kingdee_list_user_orgs查询结果

    Args:
        form_id: 单据FormId（不得猜测，不确定时先调用kingdee_search_form）
        org_id: 组织ID（必填，来自kingdee_list_user_orgs查询结果，不得编造）
        numbers: 单据编号列表（必须来自查询结果或用户明确提供）
        audit_result: 审批结果（通过/驳回/终止，必须由用户明确指定）
        user_id: 审批人内码（必须来自查询结果或用户明确提供，不得猜测）
        opinion: 审批意见
        execute: 是否执行审批。默认False返回预览，True时执行实际操作
    """
    # FormId 校验
    if not _is_valid_form_id(form_id):
        return _build_invalid_form_id_response(form_id)

    ch, uid = _get_context()
    caller = f"{ch}:{uid}"
    pm = await _get_perm_mgr()
    ok, err = check_operation_permission(pm, ch, uid, "kingdee", form_id, org_id, "workflow")
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    pkey = _preview_key(form_id, org_id, numbers=str(numbers), audit_result=audit_result, user_id=user_id)

    if not execute:
        detail_items = {
            "单据编号": str(numbers),
            "审批结果": audit_result,
            "审批人内码": user_id,
        }
        _register_preview(caller, pkey)
        return _build_write_preview(f"工作流审批({audit_result})", form_id, org_id, detail_items)

    # 防跳步校验
    if not _check_previewed(caller, pkey):
        return _build_block_response("未检测到工作流审批预览记录。")

    # 审批类型映射
    result_type_map = {"通过": "A", "驳回": "B", "终止": "C"}
    approval_type = result_type_map.get(audit_result, audit_result)
    type_label = audit_result

    try:
        client = await _get_client()
        result = await client.workflow_audit(form_id, numbers, user_id, approval_type)
        target = ",".join(numbers)
        await _audit(pm, ch, uid, "workflow_audit", form_id, target=target, detail=f"type={type_label}")
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"工作流审批{type_label} ({form_id}, {target}):\n\n{text}{_op_tag(ch, uid)}")])
    except Exception as e:
        logger.error("kingdee_workflow_audit error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"工作流审批失败: {e}")])


async def kingdee_switch_org(org_number: str) -> ToolResponse:
    """切换金蝶组织。

    Args:
        org_number: 组织编号
    """
    ch, uid = _identity()
    logger.info("[Tool] kingdee_switch_org caller=%s:%s org=%s", ch, uid, org_number)
    try:
        client = await _get_client()
        result = await client.switch_org(org_number)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"组织切换成功:\n\n{text}")])
    except Exception as e:
        logger.error("kingdee_switch_org error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"切换失败: {e}")])


# ======== 元数据工具 ========

async def kingdee_query_metadata(form_id: str) -> ToolResponse:
    """查询金蝶表单的字段定义（字段名、类型、中文名、所属实体）。"""
    ch, uid = _identity()
    logger.info("[Tool] kingdee_query_metadata caller=%s:%s form_id=%s", ch, uid, form_id)
    try:
        meta_dir = os.path.join(os.path.dirname(__file__), "metadata")
        tables_path = os.path.join(meta_dir, "common_tables.json")
        if os.path.exists(tables_path):
            with open(tables_path, "r", encoding="utf-8") as f:
                tables = json.load(f)
            for table in tables.get("tables", []):
                if table.get("form_id", "").upper() == form_id.upper():
                    fields = table.get("fields", [])
                    lines = [f"表单: {table.get('form_name', form_id)} ({form_id})\n"]
                    lines.append(f"{'字段名':<30} {'类型':<20} {'中文名'}")
                    lines.append("-" * 70)
                    for field in fields:
                        lines.append(
                            f"{field.get('field_key',''):<30} "
                            f"{field.get('field_type',''):<20} "
                            f"{field.get('display_name','')}"
                        )
                    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])

        client = await _get_client()
        result = await client.query_business_info(form_id)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return ToolResponse(content=[TextBlock(type="text", text=f"表单元数据 ({form_id}):\n\n{text[:8000]}")])
    except Exception as e:
        logger.error("kingdee_query_metadata error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"元数据查询失败: {e}")])


# ── 防跳步：预览状态注册表 ──────────────────────────────────────────────
# 记录某调用者是否已预览过特定操作，防止模型直接传 execute=True 跳过确认
_preview_registry: dict[str, set[str]] = {}


def _preview_key(form_id: str, org_id, **kwargs) -> str:
    """生成预览操作的唯一标识（用于防跳步校验）。"""
    core = f"{form_id}:{org_id}"
    # 将关键参数纳入 hash，防止预览 A 操作后执行 B 操作
    for k in sorted(kwargs):
        v = kwargs[k]
        if v is not None:
            core += f":{k}={v}"
    return hashlib.md5(core.encode()).hexdigest()[:16]


def _register_preview(caller: str, key: str) -> None:
    """记录一次成功预览。"""
    if caller not in _preview_registry:
        _preview_registry[caller] = set()
    _preview_registry[caller].add(key)


def _check_previewed(caller: str, key: str) -> bool:
    """检查该调用者是否已预览过该操作。"""
    return key in _preview_registry.get(caller, set())


def _build_block_response(reason: str) -> ToolResponse:
    """构建操作被阻止的响应。"""
    return ToolResponse(content=[TextBlock(
        type="text",
        text=f"🚫 操作已阻止：{reason}\n\n请先以 execute=False 调用获取操作预览，确认后再以 execute=True 执行。"
    )])


# ── FormId 白名单校验 ───────────────────────────────────────────────────
# 防止模型编造不存在的表单ID

def _load_valid_form_ids() -> set[str]:
    """从元数据文件加载所有合法的 FormId。"""
    valid_ids: set[str] = set()
    meta_dir = os.path.join(os.path.dirname(__file__), "metadata")

    # 加载 common_tables.json
    ct_path = os.path.join(meta_dir, "common_tables.json")
    if os.path.exists(ct_path):
        try:
            with open(ct_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for t in data.get("tables", []):
                fid = t.get("form_id", "").strip()
                if fid:
                    valid_ids.add(fid)
        except Exception:
            pass

    # 加载 domain_tables.json
    dt_path = os.path.join(meta_dir, "domain_tables.json")
    if os.path.exists(dt_path):
        try:
            with open(dt_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for domain_tables in data.values():
                for t in domain_tables:
                    fid = t.get("form_id", "").strip()
                    if fid:
                        valid_ids.add(fid)
        except Exception:
            pass

    return valid_ids


# 延迟加载，模块级缓存
_valid_form_ids_cache: set[str] | None = None


def _is_valid_form_id(form_id: str) -> bool:
    """校验 FormId 是否在白名单中。"""
    global _valid_form_ids_cache
    if _valid_form_ids_cache is None:
        _valid_form_ids_cache = _load_valid_form_ids()
    # 精确匹配，或前缀匹配（如 PUR_ 匹配 PUR_PurchaseOrder）
    if form_id in _valid_form_ids_cache:
        return True
    prefix = form_id.split("_")[0] + "_" if "_" in form_id else ""
    if prefix and any(fid.startswith(prefix) for fid in _valid_form_ids_cache):
        return True
    return False


def _build_invalid_form_id_response(form_id: str) -> ToolResponse:
    """构建 FormId 不合法的响应。"""
    return ToolResponse(content=[TextBlock(
        type="text",
        text=f"🚫 表单ID '{form_id}' 不合法：系统中不存在此表单。\n\n"
             f"请使用 kingdee_query_metadata 工具查询有效的表单ID，不要猜测或编造。"
    )])


# ── 空结果硬编码声明 ───────────────────────────────────────────────────
# 防止模型对空结果编造回答

EMPTY_RESULT_SUFFIX = (
    "\n\n⚠️ 系统中未找到匹配数据，请核实查询条件。"
    "不要基于此空结果编造或推测任何数据内容。"
    "如需调整查询条件请重新调用查询工具。"
)

async def kingdee_search_form(keyword: str) -> ToolResponse:
    """模糊搜索金蝶表单，返回匹配的 FormId 列表。"""
    ch, uid = _identity()
    logger.info("[Tool] kingdee_search_form caller=%s:%s keyword=%s", ch, uid, keyword)
    try:
        meta_dir = os.path.join(os.path.dirname(__file__), "metadata")
        matches = []
        seen_form_ids = set()

        # 搜索 common_tables.json（9个常用表单）
        common_tables_path = os.path.join(meta_dir, "common_tables.json")
        if os.path.exists(common_tables_path):
            with open(common_tables_path, "r", encoding="utf-8") as f:
                common_tables = json.load(f)

            kw = keyword.lower()
            for table in common_tables.get("tables", []):
                name = table.get("form_name", "").lower()
                form_id = table.get("form_id", "").lower()
                desc = table.get("description", "").lower()
                if kw in name or kw in form_id or kw in desc:
                    matches.append(table)
                    seen_form_ids.add(form_id)

        # 搜索 domain_tables.json（7710个表单）
        domain_tables_path = os.path.join(meta_dir, "domain_tables.json")
        if os.path.exists(domain_tables_path):
            with open(domain_tables_path, "r", encoding="utf-8") as f:
                domain_tables = json.load(f)

            kw = keyword.lower()
            for domain_key, forms in domain_tables.items():
                for form in forms:
                    form_id = form.get("form_id", "").lower()
                    form_name = form.get("name", "").lower()
                    if form_id in seen_form_ids:
                        continue  # 跳过已匹配的
                    if kw in form_id or kw in form_name:
                        matches.append({
                            "form_id": form.get("form_id", ""),
                            "name": form.get("name", ""),
                            "description": f"域: {domain_key}",
                        })
                        seen_form_ids.add(form_id)

        if not matches:
            return ToolResponse(content=[TextBlock(type="text", text=f"未找到包含 '{keyword}' 的表单。{EMPTY_RESULT_SUFFIX}")])

        lines = [f"搜索 '{keyword}' 找到 {len(matches)} 个表单：\n"]
        lines.append(f"{'FormId':<30} {'名称':<20} {'说明'}")
        lines.append("-" * 70)
        for m in matches[:50]:  # 限制返回50条
            lines.append(
                f"{m.get('form_id',''):<30} "
                f"{m.get('name', m.get('form_name', '')):<20} "
                f"{m.get('description','')}"
            )
        if len(matches) > 50:
            lines.append(f"\n... 还有 {len(matches) - 50} 个结果，请缩小搜索范围")
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])
    except Exception as e:
        logger.error("kingdee_search_form error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"搜索失败: {e}")])


# ======== 金蝶产品智能问答工具 ========


async def kingdee_product_qa(
    question: str,
    kdcloud_token: str = "",
    session_id: str = "",
    deep_think: bool = False,
) -> ToolResponse:
    """金蝶产品智能问答：解答金蝶 ERP 产品使用问题。

    通过金蝶云社区智能搜索接口，回答用户关于金蝶产品的操作、配置、报错等问题。
    产品 ID 从连接配置中读取（kdcloud_product_id），无需每次传入。

    Args:
        question: 用户问题内容
        kdcloud_token: 金蝶云社区 PAT Token（首次使用需提供，格式如 kdt_xxx...）
        session_id: 多轮对话会话ID（追问时使用，首次提问留空）
        deep_think: 是否启用深度思考模式
    """
    import urllib.request
    import urllib.parse
    import urllib.error
    import ssl

    ch, uid = _identity()
    logger.info("[Tool] kingdee_product_qa caller=%s:%s question=%s", ch, uid, question[:50])

    # 从配置读取
    cfg = ConfigManager.get_config("kingdee")

    # Token 管理：优先从配置读取，参数传入可覆盖
    token = cfg.get("kdcloud_token", "") if cfg else ""
    if kdcloud_token.strip():
        token = kdcloud_token.strip()

    if not token:
        return ToolResponse(content=[TextBlock(type="text", text=(
            "未配置金蝶云社区 Token。请按以下步骤获取：\n"
            "1. 访问 https://vip.kingdee.com 并登录\n"
            "2. 点击右上角头像 → 个人主页 → 编辑资料\n"
            "3. 找到「个人访问令牌」区域 → 新建令牌\n"
            "4. 复制 token（格式如 kdt_xxxxxxxx...）\n"
            "5. 在连接配置中填写「金蝶云社区 Token」"
        ))])

    # 产品ID：从配置读取
    product_id = cfg.get("kdcloud_product_id", "1") if cfg else "1"

    # 产品线ID：根据产品ID自动推断
    product_line_map = {
        "1": "35",   # 星空
        "3": "35",   # 星瀚
        "9": "35",   # 星辰
        "87": "35",  # 苍穹
        "93": "35",  # 套件
        "11": "35",  # EAS
        "16": "35",  # S-HR
        "15": "35",  # 精斗云会计
        "98": "35",  # 精斗云进销存
    }
    product_line_id = product_line_map.get(product_id, "35")

    # 构建请求参数
    params = {
        "scene": "1",
        "searchText": question,
        "productId": str(product_id),
        "useDeepThink": "true" if deep_think else "false",
        "useClarification": "false",
        "productLineId": product_line_id,
        "channel_level": "Agent Skill",
    }
    if session_id:
        params["sessionId"] = session_id

    url = "https://vip.kingdee.com/aisapi/ai-search?" + urllib.parse.urlencode(params)

    # SSL 上下文
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()
    except Exception:
        pass

    # 发送请求
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
    })

    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as response:
            full_answer = ""
            think_content = ""
            final_session_id = ""
            search_sources = []

            for line in response:
                try:
                    line = line.decode("utf-8").strip()
                except Exception:
                    continue
                if not line or not line.startswith("data:"):
                    continue
                try:
                    data = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                msg = data.get("message", "")
                is_think = data.get("isThink", False)

                if msg == "未授权操作":
                    return ToolResponse(content=[TextBlock(type="text", text=(
                        "Token 无效或已过期。请重新提供有效的 token：\n"
                        "1. 访问 https://vip.kingdee.com → 个人主页 → 编辑资料 → 个人访问令牌\n"
                        "2. 复制新 token 提供给我"
                    ))])

                if is_think and msg:
                    think_content += msg
                elif msg:
                    full_answer += msg

                sid = data.get("aiSearchSessionId", "")
                if sid:
                    final_session_id = str(sid)
                src = data.get("searchSources")
                if src and isinstance(src, list) and len(src) > 0:
                    search_sources = src

            # 构建响应
            result_parts = []
            if full_answer:
                result_parts.append(full_answer)
            if search_sources:
                result_parts.append("\n\n**参考来源：**")
                for i, src in enumerate(search_sources[:5], 1):
                    title = src.get("title", "未知文档")
                    url = src.get("url", "")
                    if url:
                        result_parts.append(f"{i}. [{title}]({url})")
                    else:
                        result_parts.append(f"{i}. {title}")
            if final_session_id:
                result_parts.append(f"\n\n[sessionId: {final_session_id}]")

            return ToolResponse(content=[TextBlock(type="text", text="\n".join(result_parts))])

    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return ToolResponse(content=[TextBlock(type="text", text=(
                "Token 无效 or 已过期。请重新提供有效的 token。"
            ))])
        return ToolResponse(content=[TextBlock(type="text", text=f"请求失败: HTTP {e.code}")])
    except urllib.error.URLError as e:
        return ToolResponse(content=[TextBlock(type="text", text=f"网络请求失败: {e.reason}")])
    except Exception as e:
        logger.error("kingdee_product_qa error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"问答失败: {e}")])


async def kingdee_list_digest_templates(template_id: str = "") -> ToolResponse:
    """列出所有预定义的高管报表摘要模板（如销售日报/应收周报/库存月报/财务月报）。如果不传 template_id 则列出所有模板概览，否则展示单个模板的详细提示词。"""
    try:
        from .erp_report_digest import list_templates, get_template
        if template_id:
            tpl = get_template(template_id)
            if not tpl:
                return ToolResponse(content=[TextBlock(type="text", text=f"未找到模板 ID 为 '{template_id}' 的报表模板。")])
            
            lines = [
                f"### 📋 报表模板详情：{tpl['name']} ({tpl['id']})",
                f"- **说明**: {tpl['description']}",
                f"- **执行周期 (Cron)**: `{tpl['cron']}`",
                f"- **相关表单 (FormId)**: `{tpl['form_id']}`",
                "",
                "**提示词模板 (Prompt Template)：**",
                "```text",
                tpl['prompt'],
                "```"
            ]
            return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])
        else:
            templates = list_templates()
            lines = [
                "### 📋 可用的高管报表摘要模板",
                "在为高管生成定时或即时报表时，您可以参考以下模板。通过传入 `template_id` 参数可查看单个模板的详细提示词。",
                "",
                "| 模板 ID | 报表名称 | 执行周期 | 相关表单 | 说明 |",
                "| :--- | :--- | :--- | :--- | :--- |"
            ]
            for t in templates:
                lines.append(f"| `{t['id']}` | {t['name']} | `{t['cron']}` | `{t['form_id']}` | {t['description']} |")
            
            return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])
    except Exception as e:
        logger.error("kingdee_list_digest_templates error: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"获取模板失败: {e}")])

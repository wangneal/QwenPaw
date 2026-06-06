# -*- coding: utf-8 -*-
"""Kingdee Flagship tool functions for QwenPaw Agent.

旗舰版使用 V2 RESTful API：
  POST /v2/{app_number}/{form_id}/{operation}

请求体（body）是表单特定的 JSON 数据，由 LLM 根据表单字段构造。
所有工具使用 kingdee_flagship_ 前缀命名。
"""

import asyncio
import json
import logging
import os

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from .sdk import KingdeeFlagshipClient
from erp_config import ConfigManager
from erp_permissions import (
    PermissionManager,
    check_operation_permission,
)

try:
    from qwenpaw.app.agent_context import get_current_channel, get_current_user_id
except ImportError:
    get_current_channel = None
    get_current_user_id = None

logger = logging.getLogger(__name__)

# 延迟初始化的全局变量
_client = None
_client_lock = asyncio.Lock()
_perm_mgr = None
_perm_mgr_lock = asyncio.Lock()

_SYSTEM_NAME = "kingdee_flagship"
_EMPTY_RESULT_SUFFIX = "（查询结果为空，请确认搜索关键词是否正确）"

# ══════════════════════════════════════════════════════════════
# 内部辅助函数
# ══════════════════════════════════════════════════════════════


async def _get_client():
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is not None:
            return _client
        cfg = ConfigManager.get_config("kingdee_flagship")
        _REQUIRED_KEYS = ("server_url", "app_id", "app_secret", "tenantid", "account_id", "user_name")
        if not cfg or not all(cfg.get(k) for k in _REQUIRED_KEYS):
            raise RuntimeError(
                "旗舰版插件未配置或配置不完整。请在管理页面 -> 连接配置 中填写："
                + "、".join(_REQUIRED_KEYS)
            )
        _client = KingdeeFlagshipClient(
            server_url=cfg["server_url"],
            app_id=cfg["app_id"],
            app_secret=cfg["app_secret"],
            tenantid=cfg["tenantid"],
            account_id=cfg["account_id"],
            user_name=cfg["user_name"],
            kd_language=cfg.get("kd_language", "zh_CN"),
        )
        logger.info("Flagship client created: %s", cfg["server_url"])
    return _client


def reset_client():
    global _client
    _client = None


async def _get_perm_mgr():
    global _perm_mgr
    if _perm_mgr is not None:
        return _perm_mgr
    async with _perm_mgr_lock:
        if _perm_mgr is not None:
            return _perm_mgr
        _perm_mgr = PermissionManager()
    return _perm_mgr


def _identity():
    try:
        if get_current_channel is None or get_current_user_id is None:
            return ("unknown", "unknown")
        return (get_current_channel() or "unknown",
                get_current_user_id() or "unknown")
    except (ImportError, RuntimeError, ValueError, AttributeError):
        return ("unknown", "unknown")


async def _audit(pm, ch: str, uid: str, action: str, form_id: str, target: str = "", detail: str = ""):
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


# ══════════════════════════════════════════════════════════════
# 辅助工具
# ══════════════════════════════════════════════════════════════


async def kingdee_flagship_list_user_orgs() -> ToolResponse:
    """旗舰版：查询当前用户有权限的组织列表。"""
    ch, uid = _identity()
    logger.info("[Tool] kingdee_flagship_list_user_orgs caller=%s:%s", ch, uid)
    pm = await _get_perm_mgr()
    key = f"{ch}:{uid}"
    orgs = pm.list_user_orgs(key)
    if not orgs:
        return ToolResponse(content=[TextBlock(type="text", text=(
            f"您的权限尚未配置（身份: {key}）。\n"
            "请联系管理员在 QwenPaw 管理页面配置您的权限。"
        ))])
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


async def kingdee_flagship_search_form(keyword: str) -> ToolResponse:
    """旗舰版：模糊搜索表单，返回匹配的 FormId 列表。

    Args:
        keyword: 搜索关键词（如 "销售订单"、"bd_supplier"）
    """
    ch, uid = _identity()
    logger.info("[Tool] kingdee_flagship_search_form caller=%s:%s keyword=%s", ch, uid, keyword)
    try:
        meta_dir = os.path.join(os.path.dirname(__file__), "..", "kingdee", "metadata")
        matches = []
        seen_form_ids = set()

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
                        continue
                    if kw in form_id or kw in form_name:
                        matches.append({
                            "form_id": form.get("form_id", ""),
                            "name": form.get("name", ""),
                            "description": f"域: {domain_key}",
                        })
                        seen_form_ids.add(form_id)

        v2_path = os.path.join(os.path.dirname(__file__), "v2_form_mapping.json")
        if os.path.exists(v2_path):
            with open(v2_path, "r", encoding="utf-8") as f:
                v2_data = json.load(f)
            kw = keyword.lower()
            form_op_url = v2_data.get("form_op_url", {})
            for fid in form_op_url:
                if fid in seen_form_ids:
                    continue
                if kw in fid.lower():
                    ops_list = list(form_op_url[fid].keys())
                    op_str = ", ".join(ops_list)
                    matches.append({
                        "form_id": fid,
                        "name": "",
                        "description": f"V2表单, 支持: {op_str}" if op_str else "V2表单",
                    })
                    seen_form_ids.add(fid)

        if not matches:
            return ToolResponse(content=[TextBlock(type="text", text=f"未找到包含 '{keyword}' 的表单。{_EMPTY_RESULT_SUFFIX}")])

        lines = [f"搜索 '{keyword}' 找到 {len(matches)} 个表单：\n"]
        lines.append(f"{'FormId':<35} {'名称':<20} {'说明'}")
        lines.append("-" * 80)
        for m in matches[:50]:
            lines.append(f"{m.get('form_id',''):<35} {m.get('name', m.get('form_name', '')):<20} {m.get('description','')}")
        if len(matches) > 50:
            lines.append(f"\n... 还有 {len(matches) - 50} 个结果，请缩小搜索范围")
        pm = await _get_perm_mgr()
        await _audit(pm, ch, uid, "search_form", "", keyword, f"搜索到{len(matches)}个表单")
        return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])
    except Exception as e:
        logger.error("旗舰版搜索表单失败: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"搜索失败: {e}")])


_switch_org_cache: dict[str, str] = {}


async def kingdee_flagship_switch_org(org_number: str) -> ToolResponse:
    """旗舰版：切换当前默认组织。本地记录，无需调用ERP API。"""
    ch, uid = _identity()
    logger.info("[Tool] kingdee_flagship_switch_org caller=%s:%s org=%s", ch, uid, org_number)
    pm = await _get_perm_mgr()
    key = f"{ch}:{uid}"
    user_orgs = pm.list_user_orgs(key)
    org_ids = [o["org_id"] for o in user_orgs]
    if org_number not in org_ids and "*" not in org_ids:
        return ToolResponse(content=[TextBlock(type="text", text=(
            f"您没有组织 {org_number} 的权限。\n"
            f"您有权限的组织: {', '.join(org_ids) if org_ids else '无'}"
        ))])
    org_name = ""
    try:
        client = await _get_client()
        name_map = await client.get_org_names([org_number])
        org_name = name_map.get(org_number, "")
    except Exception as e:
        logger.warning("查询组织名称失败: %s", e)
    _switch_org_cache[key] = org_number
    await _audit(pm, ch, uid, "switch_org", "", org_number, f"切换到组织 {org_number}")
    display = f"{org_number}（{org_name}）" if org_name else org_number
    return ToolResponse(content=[TextBlock(type="text", text=f"已切换默认组织到: {display}\n\n后续操作如不指定 org_id，将默认使用此组织。")])


# ══════════════════════════════════════════════════════════════
# 表单参数描述工具
# ══════════════════════════════════════════════════════════════

# 延迟加载表单参数映射
_form_params_cache: dict | None = None
_FORM_PARAMS_PATH = os.path.join(os.path.dirname(__file__), "v2_form_params.json")


def _load_form_params() -> dict:
    """加载 v2_form_params.json（表单API参数字典）。"""
    global _form_params_cache
    if _form_params_cache is not None:
        return _form_params_cache
    if not os.path.exists(_FORM_PARAMS_PATH):
        _form_params_cache = {}
        return _form_params_cache
    try:
        with open(_FORM_PARAMS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _form_params_cache = data.get("params", {})
    except Exception as e:
        logger.warning("加载 v2_form_params.json 失败: %s", e)
        _form_params_cache = {}
    return _form_params_cache


async def kingdee_flagship_describe_form(form_id: str) -> ToolResponse:
    """旗舰版：查询表单的 V2 API 请求参数定义。

    在调用任何 V2 API（request_v2）之前，应先用此工具查看该表单支持哪些操作和参数。
    返回结果包含每个操作（batchQuery/batchSave/batchDelete 等）的请求参数字段。

    Args:
        form_id: 表单ID（如 bd_supplier, sm_delivernotice, im_otherinbill）
    """
    ch, uid = _identity()
    logger.info("[Tool] kingdee_flagship_describe_form caller=%s:%s form_id=%s", ch, uid, form_id)

    params = _load_form_params()
    if not params:
        return ToolResponse(content=[TextBlock(type="text", text="表单参数定义未加载（v2_form_params.json 不可用）。请确认文件存在。")])

    form_ops = params.get(form_id)
    if not form_ops:
        return ToolResponse(content=[TextBlock(type="text", text=f"未找到表单 '{form_id}' 的参数定义。可使用 kingdee_flagship_search_form 搜索支持的表单。")])

    lines = [f"表单: {form_id}\n"]
    lines.append("支持的 V2 API 操作与参数：\n")

    for op_name, op_params in form_ops.items():
        lines.append(f"[{op_name}]")
        if not op_params:
            lines.append("  （无自定义参数，使用默认请求体）")
        else:
            # 按 level 分组
            top_params = [p for p in op_params if p.get('l', '') in ('', '1')]
            sub_params = [p for p in op_params if p.get('l', '') not in ('', '1')]
            for p in top_params:
                req = "【必填】" if p.get('m') == '1' else "【可选】"
                desc = p.get('d', '') or ''
                ex = p.get('e', '') or ''
                ex_str = f'  示例: {ex}' if ex else ''
                lines.append(f"  {req} {p.get('n', '')} ({p.get('t', '')}) {desc}{ex_str}")
            if top_params and sub_params:
                lines.append(f"  ... 还有 {len(sub_params)} 个子级参数")
        lines.append("")

    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])


# ══════════════════════════════════════════════════════════════
# 通用 V2 API 工具
# ══════════════════════════════════════════════════════════════


async def kingdee_flagship_request_v2(
    form_id: str,
    operation: str,
    body: str = "",
    org_id: str = "",
) -> ToolResponse:
    """旗舰版 V2 RESTful API 通用请求。

    旗舰版的核心工具，所有单据操作都通过此工具执行。
    V2 API 是表单特定的，请求体（body）需要根据表单字段构造。

    ⚠️ 防幻觉规则：body 参数名必须来自 describe_form 的返回结果。
    不要在不知道参数名的情况下猜测。如果传入了不存在的参数名，工具会拒绝执行。

    V2 API 格式：POST /v2/{app_number}/{form_id}/{operation}

    常见操作码（operation）：
    - batchQuery: 查询单据列表
    - batchSave: 保存/新增单据
    - batchAdd: 新增单据
    - batchUpdate: 修改单据
    - batchDelete: 删除单据
    - batchSubmit: 提交单据
    - batchAudit: 审核单据
    - batchUnAudit: 反审核单据
    - batchUnSubmit: 反提交/撤销
    - batchDisable: 禁用
    - batchEnable: 启用

    Args:
        form_id: 表单ID（如 bd_supplier, sm_delivernotice）
        operation: V2 操作码（如 batchQuery, batchSave 等）
        body: 请求体 JSON 字符串。参数名必须与 describe_form 返回的字段名一致
        org_id: 组织ID（用于权限校验）
    """
    ch, uid = _identity()
    pm = await _get_perm_mgr()

    logger.info("[Tool] kingdee_flagship_request_v2 caller=%s:%s form=%s op=%s org=%s",
                ch, uid, form_id, operation, org_id)

    ok, err = check_operation_permission(pm, ch, uid, _SYSTEM_NAME, form_id, org_id, operation)
    if not ok:
        return ToolResponse(content=[TextBlock(type="text", text=err)])

    try:
        client = await _get_client()
        body_dict = json.loads(body) if body else {}

        # ── 防幻觉：校验 body 参数名是否合法 ──────────────────
        # LLM 可能凭训练数据中的经典版 API 知识猜测参数名（如 FieldKeys/FilterString），
        # 这里用 API 文档中的真实参数名做白名单校验。只校验顶层参数（level=1/空），
        # 子级参数（level=2/3）只在嵌套对象中出现，LLM 不会直接放在顶层 body 中。
        if body_dict:
            form_params = _load_form_params()
            known_ops = form_params.get(form_id, {})
            known_params = known_ops.get(operation, [])
            if known_params:
                top_names = {p["n"] for p in known_params if p.get("l", "1") in ("", "1")}
                unknown_keys = set(body_dict.keys()) - top_names
                if unknown_keys:
                    skip = {"_debug", "_test"}
                    unknown_keys = unknown_keys - skip
                if unknown_keys:
                    return ToolResponse(content=[TextBlock(
                        type="text",
                        text=f"参数不合法：{', '.join(sorted(unknown_keys))} 不是表单 '{form_id}' "
                             f"操作 '{operation}' 支持的参数。\n\n"
                             f"请先调用 kingdee_flagship_describe_form('{form_id}') "
                             f"查看该表单支持哪些参数，不要猜测或编造参数名。"
                    )])

        result = await client.request_v2(form_id, operation, body_dict)

        await _audit(pm, ch, uid, operation, form_id, "", f"body keys={list(body_dict.keys())}")

        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        return ToolResponse(content=[TextBlock(type="text", text=text)])

    except json.JSONDecodeError as e:
        return ToolResponse(content=[TextBlock(type="text", text=f"参数错误: body 不是有效的JSON: {e}")])
    except Exception as e:
        logger.error("旗舰版V2请求失败: %s", e, exc_info=True)
        return ToolResponse(content=[TextBlock(type="text", text=f"请求失败: {e}")])

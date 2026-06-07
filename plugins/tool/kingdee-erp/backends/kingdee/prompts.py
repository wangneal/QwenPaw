"""Centralized Kingdee ERP tool descriptions and agent prompt templates."""

from __future__ import annotations

from typing import Any, Dict


DEFAULT_TOOL_ICON = "erp"


TOOL_DEFINITIONS = [
    {
        "name": "kingdee_list_user_orgs",
        "description": "查询当前身份可访问的 ERP 组织列表。未配置默认组织且业务操作需要组织上下文时，必须先使用此工具获取组织信息。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_query_bill",
        "description": "查询金蝶单据或基础资料行数据。使用前必须校验 FormId 和字段标识；过滤条件必须来自明确输入或已确认的查询结果。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_view_bill",
        "description": "按明确的单据编号或内码查看单个金蝶单据或基础资料记录。标识必须来自用户输入或前置查询结果。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_get_report",
        "description": "查询金蝶报表数据。FormId、方案标识、字段和报表参数必须由用户明确提供，或来自元数据和配置。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_get_kds_report",
        "description": "查询金蝶 KDS 报表数据。核算体系、会计政策、币别、报表编号和范围参数必须来自明确配置。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_save_bill",
        "description": "新增或更新金蝶单据和基础资料。工具层强制执行预览确认、FormId 校验和业务响应校验；引用字段必须使用已验证编码。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_delete_bill",
        "description": "按明确编号或内码删除金蝶记录。工具层强制执行预览确认、FormId 校验和业务响应校验。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_delete_recent_entity",
        "description": "删除同一渠道、用户和会话中最近一次成功保存的唯一记录。用于撤销刚创建的错误记录；执行前仍需预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_submit_bill",
        "description": "按明确编号或内码提交金蝶单据。工具层强制执行预览确认和业务响应校验。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_audit_bill",
        "description": "按明确编号或内码审核金蝶单据。工具层强制执行预览确认和业务响应校验。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_unaudit_bill",
        "description": "按明确编号或内码反审核金蝶单据。工具层强制执行预览确认和业务响应校验。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_push_bill",
        "description": "将金蝶源单下推生成目标单据。源单记录和转换参数必须来自明确输入或前置查询结果；执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_allocate_base_data",
        "description": "按内码将企业版基础资料分配到目标组织。执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_cancel_allocate_base_data",
        "description": "按内码取消企业版基础资料分配。执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_group_save_base_data",
        "description": "新增或更新企业版基础资料分组。FormId 可配置；分组编码、父分组内码和分组字段必须明确。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_query_group_info",
        "description": "按分组内码或记录内码查询企业版基础资料分组信息。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_query_group_by_business_key",
        "description": "按明确分组编码、名称或内码查询企业版基础资料分组信息；内部解析分组内码后调用 QueryGroupInfo。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_group_delete_base_data",
        "description": "按分组内码删除企业版基础资料分组。执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_create_group_under_parent",
        "description": "在指定父分组下新增基础资料子分组。父分组必须通过明确名称、编码或内码解析；父分组匹配不唯一时拒绝执行。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_delete_group_by_business_key",
        "description": "按明确分组编码、名称或内码删除基础资料分组。名称匹配不唯一时拒绝执行；执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_allocate_customers_to_orgs",
        "description": "按已验证客户编码、名称或内码，以及组织编码、名称或内码完成客户分配。执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_cancel_allocate_customers_to_orgs",
        "description": "按已验证客户和组织业务标识取消客户分配。执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_execute_operation",
        "description": "按明确的金蝶操作编码和操作数据执行自定义操作。执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_workflow_audit",
        "description": "按明确单据编号、审批人内码和审批结果处理金蝶工作流审批。执行前必须预览确认。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_switch_org",
        "description": "设置当前渠道、用户和智能体上下文的默认金蝶组织。组织编码必须明确提供。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_query_metadata",
        "description": "查询金蝶表单元数据和字段定义。构建字段列表、过滤条件或写入载荷前应先使用此工具确认字段。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_search_form",
        "description": "搜索可用金蝶 FormId。无法确认准确 FormId 时使用此工具。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": True,
    },
    {
        "name": "kingdee_product_qa",
        "description": "使用已配置的金蝶云社区 Token 查询金蝶产品文档和故障处理知识。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": False,
    },
    {
        "name": "kingdee_list_digest_templates",
        "description": "列出预置高管报表摘要模板，或查看指定模板的完整提示词。",
        "icon": DEFAULT_TOOL_ICON,
        "requires_config": False,
    },
]


TOOL_DEFINITIONS_BY_NAME = {item["name"]: item for item in TOOL_DEFINITIONS}


def build_manifest_tools() -> list[dict[str, Any]]:
    """Return plugin manifest tool metadata from centralized tool definitions."""
    return [
        {
            "name": item["name"],
            "description": item["description"],
            "icon": item.get("icon", DEFAULT_TOOL_ICON),
            "requires_config": bool(item.get("requires_config", True)),
        }
        for item in TOOL_DEFINITIONS
    ]


REPORT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "sales_daily": {
        "name": "销售日报",
        "description": "销售订单汇总、销售退货汇总、客户排名和异常波动分析",
        "cron": "0 9 * * *",
        "form_id": "SAL_SaleOrder",
        "prompt": (
            "任务: 生成销售日报。\n"
            "查询要求:\n"
            "1. 查询昨日销售订单汇总，按客户统计金额和数量。\n"
            "2. 查询昨日销售退货单汇总，按客户统计金额和数量。\n"
            "3. 计算净销售额，公式为销售订单金额减销售退货金额。\n"
            "4. 对比前一日净销售额并计算环比变化。\n"
            "5. 按净销售额列示前五名客户。\n"
            "6. 当单日降幅大于30%时列为异常波动。\n"
            "输出要求:\n"
            "1. 标题格式为: 销售日报 - {date}。\n"
            "2. 使用表格列示: 客户、订单金额、退货金额、净销售额、环比。\n"
            "3. 异常项使用文字标记: 异常。\n"
            "4. 最后输出不超过三条经营结论。"
        ),
    },
    "receivable_weekly": {
        "name": "应收周报",
        "description": "应收余额、收款汇总、账龄分析和逾期客户清单",
        "cron": "0 9 * * 1",
        "form_id": "AR_Receivable",
        "prompt": (
            "任务: 生成应收周报。\n"
            "查询要求:\n"
            "1. 查询本周应收账款余额，按客户汇总。\n"
            "2. 查询本周收款单金额，按客户汇总。\n"
            "3. 计算净应收，公式为应收余额减已收款金额。\n"
            "4. 按账龄区间分组: 0-30天、31-60天、61-90天、90天以上。\n"
            "5. 列示逾期超过30天的前十名客户及金额。\n"
            "6. 对比上周应收余额变化。\n"
            "输出要求:\n"
            "1. 标题格式为: 应收周报 - {week}。\n"
            "2. 使用表格列示: 客户、应收余额、已收款、净应收、账龄。\n"
            "3. 逾期项使用文字标记: 逾期。\n"
            "4. 最后输出不超过三条回款建议。"
        ),
    },
    "inventory_monthly": {
        "name": "库存月报",
        "description": "库存金额、库存变动、周转天数和呆滞物料分析",
        "cron": "0 9 1 * *",
        "form_id": "STK_Inventory",
        "prompt": (
            "任务: 生成库存月报。\n"
            "查询要求:\n"
            "1. 查询当前库存总金额和总数量，按物料类别汇总。\n"
            "2. 查询本月入库汇总，按仓库统计。\n"
            "3. 查询本月出库汇总，按仓库统计。\n"
            "4. 计算本月净变动和期末库存。\n"
            "5. 查询超过90天无出入库记录的前十项呆滞物料。\n"
            "6. 计算库存周转天数，公式为平均库存除以日均出库。\n"
            "输出要求:\n"
            "1. 标题格式为: 库存月报 - {month}。\n"
            "2. 使用表格列示: 仓库、期初、入库、出库、期末、周转天数。\n"
            "3. 呆滞物料使用文字标记: 呆滞。\n"
            "4. 最后输出不超过三条库存优化建议。"
        ),
    },
    "finance_monthly": {
        "name": "财务月报",
        "description": "利润表、关键指标和异动科目分析",
        "cron": "0 10 1 * *",
        "form_id": "GLR_ProfitStatement",
        "prompt": (
            "任务: 生成财务月报。\n"
            "查询要求:\n"
            "1. 查询本月利润表，包括营业收入、营业成本、期间费用和净利润。\n"
            "2. 对比上月金额并计算变化额和变化率。\n"
            "3. 当科目变化率大于20%时列为异动科目，并说明对利润的影响方向。\n"
            "4. 计算毛利率和净利率。\n"
            "输出要求:\n"
            "1. 标题格式为: 财务月报 - {month}。\n"
            "2. 使用表格列示: 科目、本月金额、上月金额、变化额、变化率。\n"
            "3. 单独列示毛利率和净利率。\n"
            "4. 异动科目使用文字标记: 异动。\n"
            "5. 最后输出不超过三条经营建议。"
        ),
    },
}

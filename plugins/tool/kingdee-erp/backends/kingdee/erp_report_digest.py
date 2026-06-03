"""
ERP 高管报表摘要 — 预定义报表模板 + Cron Job 管理

预定义报表：
  - sales_daily:     销售日报 (每日 09:00)
  - receivable_weekly: 应收周报 (每周一 09:00)
  - inventory_monthly: 库存月报 (每月1日 09:00)
  - finance_monthly: 财务月报 (每月1日 10:00)

通过 QwenPaw CronJobManager 创建定时任务，
task_type="agent" 让 Agent 自动调用金蝶查询工具并推送。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("erp_report_digest")


# ──────────────────────────────────────────────
# 报表模板定义
# ──────────────────────────────────────────────

REPORT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "sales_daily": {
        "name": "销售日报",
        "description": "销售订单汇总 + 同比 + Top 客户",
        "cron": "0 9 * * *",           # 每日 09:00
        "form_id": "SAL_SaleOrder",
        "prompt": (
            "请执行以下查询并生成销售日报：\n"
            "1. 查询昨日的销售订单汇总（金额、数量），按客户分组（入）\n"
            "2. 查询昨日的销售退货单汇总（金额、数量），按客户分组（出）\n"
            "3. 计算净销售额 = 销售订单金额 − 退货金额\n"
            "4. 对比前天的净销售额变化（环比）\n"
            "5. 按净销售额列出 Top 5 客户\n"
            "6. 如有异常波动（单日降幅>30%），重点标注\n\n"
            "格式要求：\n"
            "- 标题：📊 销售日报 - {date}\n"
            "- 表格：客户 | 订单金额 | 退货金额 | 净销售额 | 环比\n"
            "- 异常项用 ⚠️ 标注\n"
            "- 最后给出简短总结（2-3句话）"
        ),
    },
    "receivable_weekly": {
        "name": "应收周报",
        "description": "应收余额 + 账龄分析 + 逾期预警",
        "cron": "0 9 * * 1",           # 每周一 09:00
        "form_id": "AR_Receivable",
        "prompt": (
            "请执行以下查询并生成应收周报：\n"
            "1. 查询本周应收账款总余额（按客户汇总）\n"
            "2. 查询本周各客户的收款单汇总金额\n"
            "3. 计算净应收 = 应收余额 − 已收款金额，按客户列出\n"
            "4. 按账龄分组：0-30天、31-60天、61-90天、90天以上\n"
            "5. 列出逾期超过30天的 Top 10 客户及金额\n"
            "6. 对比上周应收余额变化\n\n"
            "格式要求：\n"
            "- 标题：💰 应收周报 - {week}\n"
            "- 用表格展示：客户 | 应收余额 | 已收款 | 净应收 | 账龄\n"
            "- 净应收 > 0 的用 🔴 标注逾期\n"
            "- 给出回款建议（2-3句话）"
        ),
    },
    "inventory_monthly": {
        "name": "库存月报",
        "description": "库存金额 + 周转率 + 呆滞物料预警",
        "cron": "0 9 1 * *",           # 每月1日 09:00
        "form_id": "STK_Inventory",
        "prompt": (
            "请执行以下查询并生成库存月报：\n"
            "1. 查询当前库存总金额和总数量，按物料类别汇总\n"
            "2. 查询本月入库汇总（采购入库 + 生产入库 + 其他入库），按仓库分组\n"
            "3. 查询本月出库汇总（销售出库 + 生产领料 + 其他出库），按仓库分组\n"
            "4. 计算本月净变动 = 入库 − 出库，期末库存 = 期初 + 净变动\n"
            "5. 查询超过90天无出入库记录的呆滞物料（Top 10）\n"
            "6. 计算库存周转天数 = 平均库存 / 日均出库\n\n"
            "格式要求：\n"
            "- 标题：📦 库存月报 - {month}\n"
            "- 表格：仓库 | 期初 | 入库 | 出库 | 期末 | 周转天数\n"
            "- 呆滞物料用 ⚠️ 标注\n"
            "- 给出库存优化建议（2-3句话）"
        ),
    },
    "finance_monthly": {
        "name": "财务月报",
        "description": "利润表 + 关键指标 + 异动科目",
        "cron": "0 10 1 * *",          # 每月1日 10:00
        "form_id": "GLR_ProfitStatement",
        "prompt": (
            "请执行以下查询并生成财务月报：\n"
            "1. 查询本月利润表：营业收入（入）、营业成本（出）、期间费用（出）、净利润\n"
            "2. 对比上月各项变化金额和变化率\n"
            "3. 标注异动科目（变化率>20%），说明是增利还是减利\n"
            "4. 计算毛利率 = (收入 − 成本) / 收入、净利率 = 净利润 / 收入\n\n"
            "格式要求：\n"
            "- 标题：📈 财务月报 - {month}\n"
            "- 表格：科目 | 本月金额 | 上月金额 | 变化额 | 变化率\n"
            "- 毛利率/净利率单独列示\n"
            "- 异动科目用 ⚠️ 标注，标注方向（增利/减利）\n"
            "- 给出经营建议（2-3句话）"
        ),
    },
}


def list_templates() -> List[Dict[str, Any]]:
    """列出所有预定义报表模板。"""
    result = []
    for key, tpl in REPORT_TEMPLATES.items():
        result.append({
            "id": key,
            "name": tpl["name"],
            "description": tpl["description"],
            "cron": tpl["cron"],
            "form_id": tpl["form_id"],
        })
    return result


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    """获取单个报表模板。"""
    tpl = REPORT_TEMPLATES.get(template_id)
    if not tpl:
        return None
    return {
        "id": template_id,
        **tpl,
    }


def build_prompt(template_id: str) -> str:
    """根据模板生成 Agent prompt（替换日期占位符）。"""
    tpl = REPORT_TEMPLATES.get(template_id)
    if not tpl:
        raise ValueError(f"未知的报表模板: {template_id}")

    now = datetime.now()
    prompt = tpl["prompt"]
    prompt = prompt.replace("{date}", now.strftime("%Y-%m-%d"))
    prompt = prompt.replace("{week}", f"W{now.isocalendar()[1]}")
    prompt = prompt.replace("{month}", now.strftime("%Y-%m"))

    return prompt


def build_cron_jobs_config() -> List[Dict[str, Any]]:
    """构建所有预定义 Cron Job 的配置列表。

    返回格式供 QwenPaw CronJobManager 使用：
    {
        "name": str,
        "cron_expr": str,
        "task_type": "agent",
        "prompt": str,
        "enabled": bool,
    }
    """
    jobs = []
    for key, tpl in REPORT_TEMPLATES.items():
        jobs.append({
            "name": f"erp_digest_{key}",
            "label": tpl["name"],
            "cron_expr": tpl["cron"],
            "task_type": "agent",
            "prompt": build_prompt(key),
            "enabled": False,  # 默认不启用，需用户手动开启
        })
    return jobs

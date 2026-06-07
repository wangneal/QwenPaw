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

from .prompts import REPORT_TEMPLATES

logger = logging.getLogger("erp_report_digest")


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

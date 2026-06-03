# -*- coding: utf-8 -*-
"""金蝶后端 - 金蝶云星空 WebAPI 的 ERPBackend 实现"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from erp_backend import ERPBackend, with_request_id
from erp_config import ConfigManager
from erp_permissions import PermissionManager, register_settings_routes
from .domains import get_domain_map, BASE_PREFIXES
from .config_fields import KINGDEE_CONFIG_FIELDS, BACKEND_NAME, BACKEND_LABEL, BACKEND_ICON
from .sdk import KingdeeClient

logger = logging.getLogger(__name__)


class KingdeeBackend:
    """ERPBackend implementation for Kingdee Cloud K/3."""

    def __init__(self):
        self._system_name = "kingdee"
        self._display_name = "金蝶云星空"
        self._base_prefixes = BASE_PREFIXES

    @property
    def system_name(self) -> str:
        return self._system_name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def label(self) -> str:
        return "金蝶"

    @property
    def config_fields(self) -> List[Dict[str, Any]]:
        return KINGDEE_CONFIG_FIELDS

    @property
    def domains(self) -> Dict[str, List[str]]:
        """动态获取业务域映射（从元数据加载 + 用户自定义覆盖）。"""
        return get_domain_map()

    def register_tools(self, api: "PluginApi") -> int:
        """注册全部金蝶工具到 QwenPaw"""
        from . import tools as kingdee_tools

        TOOL_DEFS = [
            ("kingdee_list_user_orgs", "查询当前用户有权限的组织列表。⚠️ 任何业务操作前必须先调用此工具获取org_id，不得编造或猜测org_id值", "🏢"),
            ("kingdee_query_bill", "查询金蝶单据数据。⚠️硬性防护：1)FormId校验(非法ID被拒绝)2)空结果强制声明(防止编造)。防幻觉：不确定FormId先调kingdee_search_form；不确定字段名先调kingdee_query_metadata；不得编造过滤值", "📊"),
            ("kingdee_view_bill", "查看金蝶单据完整详情。⚠️ FormId校验+空结果声明。单据编号必须来自查询结果或用户明确提供，不得编造", "📄"),
            ("kingdee_get_report", "查询金蝶报表数据（余额表、利润表等）。⚠️ FormId校验+空结果声明。form_id和scheme_id不得猜测", "📈"),
            ("kingdee_get_kds_report", "查询金蝶合并报表数据。⚠️ 所有编号参数（核算体系/会计政策/币别等）必须从实际配置获取，不得使用示例值或猜测值", "📊"),
            ("kingdee_save_bill", "保存/新增金蝶单据。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验(非法ID被拒绝)3)防跳步(未预览过拒绝执行)。防幻觉：编码值必须查询获取禁止猜测，基础资料必须{\"FNumber\":\"编码\"}包裹", "💾"),
            ("kingdee_delete_bill", "删除金蝶单据。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验3)防跳步。删除不可逆！单号必须来自查询结果", "🗑️"),
            ("kingdee_submit_bill", "提交金蝶单据审批。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验3)防跳步。单号必须来自查询结果", "📤"),
            ("kingdee_audit_bill", "审核金蝶单据。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验3)防跳步。审核后不可修改！", "✅"),
            ("kingdee_unaudit_bill", "反审核金蝶单据。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验3)防跳步", "↩️"),
            ("kingdee_push_bill", "下推金蝶单据（如订单→出库单）。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验3)防跳步。源单编号和目标单ID必须来自查询结果", "⬇️"),
            ("kingdee_execute_operation", "执行金蝶自定义操作（禁用/启用等）。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验3)防跳步。op_number和op_data不得猜测", "⚙️"),
            ("kingdee_workflow_audit", "工作流审批金蝶单据（通过/驳回/终止）。⚠️三重防护：1)双步调用(execute=False预览→True执行)2)FormId校验3)防跳步。审批类型必须用户指定，user_id不得猜测", "📝"),
            ("kingdee_switch_org", "切换金蝶组织。⚠️ org_number必须来自kingdee_list_user_orgs的查询结果，不得猜测", "🔄"),
            ("kingdee_query_metadata", "查询金蝶表单字段定义（字段名、类型、中文名）。在调用写入工具或构建查询字段前，应先调用此工具确认字段类型和名称", "🔍"),
            ("kingdee_search_form", "模糊搜索金蝶表单，返回匹配的FormId列表。在调用kingdee_query_bill前，如果不确定FormId，应先调用此工具搜索确认", "🔎"),
            ("kingdee_product_qa", "金蝶产品智能问答：解答产品使用问题、操作指导、报错解决", "❓"),
            ("kingdee_list_digest_templates", "列出所有预定义的高管报表摘要模板（销售日报/应收周报/库存月报/财务月报）", "📋"),
        ]

        for name, desc, icon in TOOL_DEFS:
            func = getattr(kingdee_tools, name)
            wrapped = with_request_id(name)(func)
            api.register_tool(tool_name=name, tool_func=wrapped,
                              description=desc, icon=icon)

        logger.info(f"Kingdee backend: {len(TOOL_DEFS)} tools registered")
        return len(TOOL_DEFS)

    def _get_config(self) -> Dict[str, Any]:
        """获取金蝶连接配置。

        优先从 ConfigManager 读取自管 JSON 文件，
        回退到 QwenPaw get_tool_config()（兼容旧配置），
        再回退到直接读默认 agent 的 agent.json。
        """
        # 1. 优先：自管 JSON 文件
        cfg = ConfigManager.get_config(self._system_name)
        if cfg and any(v for k, v in cfg.items() if k in ("server_url", "acct_id", "app_id")):
            return cfg

        # 2. 回退：QwenPaw get_tool_config
        try:
            from qwenpaw.plugins import get_tool_config
            cfg = get_tool_config("kingdee_query_bill")
            if cfg:
                logger.debug("Config loaded from QwenPaw get_tool_config (fallback)")
                return cfg
        except ImportError:
            pass
        except Exception as e:
            logger.debug("get_tool_config fallback failed: %s", e)

        # 3. 最终回退：直接读默认 agent.json
        try:
            working_dir = os.environ.get("QWENPAW_WORKING_DIR", os.path.expanduser("~/.qwenpaw"))
            default_json = Path(working_dir) / "workspaces" / "default" / "agent.json"
            if default_json.exists():
                data = json.loads(default_json.read_text(encoding="utf-8"))
                tool_cfg = (data.get("tools", {})
                            .get("builtin_tools", {})
                            .get("kingdee_query_bill", {})
                            .get("config", {}))
                if tool_cfg:
                    logger.debug("Config loaded from default agent.json (fallback)")
                    return tool_cfg
        except Exception as e:
            logger.debug("Fallback config read failed: %s", e)

        return {}

    def register_routes(self, api: "PluginApi") -> None:
        """注册金蝶权限管理 REST 路由"""
        router = APIRouter()
        mgr = PermissionManager()

        class PermBody(BaseModel):
            """权限请求体"""
            key: str
            org_id: str = "*"
            display_name: str = ""
            domains: list = []
            access: str = "readonly"

        async def _enrich_with_org_names(items):
            org_ids = [item.get("org_id") for item in items if item.get("org_id") and item.get("org_id") != "*"]
            if not org_ids:
                for item in items:
                    item["org_name"] = "全部" if item.get("org_id") == "*" else item.get("org_id", "")
                return items
            try:
                client = self.get_client(self._get_config())
                names = await client.get_org_names(org_ids)
            except Exception as e:
                logger.debug("获取组织名称失败，降级显示ID: %s", e)
                names = {}
            for item in items:
                oid = item.get("org_id", "")
                item["org_name"] = names.get(oid, oid if oid != "*" else "全部")
            return items

        # 注册共享配置和字段映射路由
        register_settings_routes(router, mgr)

        # ── 元数据路由（必须在 /{key} 之前注册，否则会被拦截）──

        @router.get("/audit-log")
        def get_audit_log(
            limit: int = Query(100, ge=1, le=1000),
            operator: str = Query(""),
            action: str = Query(""),
            form_id: str = Query(""),
        ):
            """查询审计日志"""
            return mgr.list_audit_log(
                limit=limit, operator=operator,
                action=action, form_id=form_id,
            )

        @router.get("/meta/orgs")
        async def list_all_orgs():
            """查询金蝶全部组织列表（用于前端组织选择器）"""
            try:
                cfg = self._get_config()
                if not cfg:
                    return {"orgs": [], "error": "金蝶连接配置为空，请在「连接配置」中填写金蝶连接参数"}
                client = self.get_client(cfg)
                result = await client.execute_bill_query(
                    "ORG_Organizations", "FNumber,FName", "", "", 500,
                )
                orgs = [{"org_id": row[0], "org_name": row[1]} for row in result if len(row) >= 2]
                return {"orgs": orgs}
            except ValueError as e:
                logger.warning("配置不完整: %s", e)
                return {"orgs": [], "error": str(e)}
            except Exception as e:
                logger.warning("查询组织列表失败: %s", e)
                return {"orgs": [], "error": f"查询金蝶组织失败: {e}"}

        @router.get("/meta/domains")
        def list_domains():
            """查询系统可用的业务域列表（用于前端业务域选择器）"""
            # 域名 → 中文名映射
            domain_labels = {
                "finance": "财务", "sales": "销售", "procurement": "采购",
                "inventory": "库存", "production": "生产", "hr": "人事",
                "base": "基础资料", "other": "其他",
            }
            domains_with_label = {}
            for k, v in self.domains.items():
                domains_with_label[k] = {
                    "label": domain_labels.get(k, k),
                    "prefixes": v,
                }
            return {
                "systems": {
                    self.system_name: {
                        "display_name": self.display_name,
                        "domains": domains_with_label,
                    }
                }
            }

        # ── CRUD 路由 ──

        @router.get("/")
        async def list_perms():
            """查询全部权限列表（含组织名称）"""
            items = mgr.list_permissions()
            return {"items": await _enrich_with_org_names(items)}

        @router.post("/")
        def set_perm(body: PermBody):
            """新增或更新单个组织权限"""
            mgr.set_permission(
                key=body.key, org_id=body.org_id,
                display_name=body.display_name, domains=body.domains,
                access=body.access,
            )
            return {"status": "ok", "key": body.key, "org_id": body.org_id}

        @router.delete("/{key}/{org_id}")
        def del_perm(key: str, org_id: str):
            """删除指定用户的指定组织权限"""
            mgr.remove_permission(key, org_id)
            return {"status": "ok"}

        # ── 参数路由（必须在具体路径之后注册）──

        @router.get("/{key}")
        async def list_user_perms(key: str):
            """查询指定用户的全部组织权限（含组织名称）"""
            items = mgr.list_user_permissions(key)
            return {"items": await _enrich_with_org_names(items)}

        @router.delete("/{key}")
        def del_user(key: str):
            """删除指定用户的全部权限"""
            mgr.remove_user(key)
            return {"status": "ok"}

        # ── 多厂商配置 API ──

        class ConfigSaveBody(BaseModel):
            config: dict

        @router.get("/config/backends")
        def list_backends():
            """列出所有已注册后端及配置状态"""
            from erp_config import ConfigManager
            return {"backends": ConfigManager.list_backends()}

        @router.get("/config/{backend_name}")
        def get_backend_config(backend_name: str):
            """获取指定后端的配置和字段定义"""
            from erp_config import ConfigManager
            meta = ConfigManager._backends.get(backend_name)
            if not meta:
                return {"error": f"未知后端: {backend_name}"}
            config = ConfigManager.get_config(backend_name)
            safe_config = {}
            for k, v in config.items():
                if k in ("app_secret", "api_key", "secret", "password", "token"):
                    safe_config[k] = "***"
                else:
                    safe_config[k] = v
            return {
                "name": backend_name,
                "label": meta["label"],
                "icon": meta["icon"],
                "config_fields": meta["config_fields"],
                "config": safe_config,
            }

        @router.post("/config/{backend_name}")
        def save_backend_config(backend_name: str, body: ConfigSaveBody):
            """保存指定后端的配置"""
            from erp_config import ConfigManager
            meta = ConfigManager._backends.get(backend_name)
            if not meta:
                return {"error": f"未知后端: {backend_name}"}
            config = body.config
            existing = ConfigManager.get_config(backend_name)
            for field_def in meta["config_fields"]:
                fname = field_def.get("name", "")
                if field_def.get("type") == "password" and config.get(fname) == "***":
                    if existing.get(fname):
                        config[fname] = existing[fname]
            ConfigManager.save_config(backend_name, config)
            return {"status": "ok", "backend": backend_name}

        @router.post("/config/{backend_name}/test")
        async def test_backend_connection(backend_name: str, body: ConfigSaveBody = None):
            """测试指定后端的连接"""
            from erp_config import ConfigManager
            config_data = body.config if body else ConfigManager.get_config(backend_name)
            if not config_data:
                return {"success": False, "message": "无配置，请先填写连接参数"}
            result = await ConfigManager.test_connection(backend_name, config_data)
            return result

        # ── 报表摘要路由 ──────────────────────────────────

        digest_router = APIRouter()

        @digest_router.get("/templates")
        def list_digest_templates():
            """列出预定义报表摘要模板"""
            from .erp_report_digest import list_templates, get_template, REPORT_TEMPLATES
            templates = list_templates()
            # 补充每个模板的 prompt
            for t in templates:
                tpl = get_template(t["id"])
                if tpl:
                    t["prompt"] = tpl["prompt"]
            return {"templates": templates}

        @digest_router.get("/templates/{template_id}")
        def get_digest_template_detail(template_id: str):
            """获取单个报表模板详情（含完整 prompt）"""
            from .erp_report_digest import get_template, build_prompt, REPORT_TEMPLATES
            tpl = get_template(template_id)
            if not tpl:
                return {"error": f"未找到模板: {template_id}", "available": list(REPORT_TEMPLATES.keys())}
            prompt = build_prompt(template_id)
            return {
                "id": template_id,
                "name": tpl["name"],
                "description": tpl["description"],
                "cron": tpl["cron"],
                "form_id": tpl["form_id"],
                "prompt": prompt,
            }

        @digest_router.post("/templates/{template_id}/create")
        async def create_digest_cron(
            template_id: str,
            body: dict,
        ):
            """一键创建 Cron Job（使用 QwenPaw Cron API）

            通过 QwenPaw 的 CronJobManager 创建定时推送任务，
            task_type="agent" 让 Agent 自动调用金蝶工具生成报表并推送到指定渠道。

            body 格式:
                {
                    "channel": "推送渠道 (dingtalk/wecom/console)",
                    "user_id": "目标用户 ID",
                    "session_id": "目标会话 ID (可选)",
                    "enabled": 是否立即启用 (默认 false)
                }
            """
            from .erp_report_digest import build_cron_jobs_config, REPORT_TEMPLATES

            tpl = REPORT_TEMPLATES.get(template_id)
            if not tpl:
                return {"error": f"未找到模板: {template_id}", "available": list(REPORT_TEMPLATES.keys())}

            # 构建 prompt
            from .erp_report_digest import build_prompt
            prompt_text = build_prompt(template_id)

            config = {
                "name": f"erp_digest_{template_id}",
                "label": tpl["name"],
                "cron_expr": tpl["cron"],
                "task_type": "agent",
                "prompt": prompt_text,
                "channel": body.get("channel", "console"),
                "target_user_id": body.get("user_id", ""),
                "target_session_id": body.get("session_id", ""),
                "enabled": body.get("enabled", False),
            }

            # 调用 QwenPaw CronJobManager API
            try:
                from qwenpaw.app.crons.manager import CronManager
                workspace = CronManager()
                job = await workspace.create_or_replace_job(config)
                return {
                    "status": "ok",
                    "job_id": job.id if job else None,
                    "message": f"定时推送已创建: {tpl['name']} ({template_id})",
                    "config": config,
                }
            except ImportError:
                logger.warning("QwenPaw CronManager 不可用，定时推送功能需要 QwenPaw >= 1.1.7")
                return {
                    "status": "error",
                    "message": "QwenPaw CronManager 不可用。请升级 QwenPaw 到 >= 1.1.7",
                    "config": config,
                }
            except Exception as e:
                logger.error("创建 Cron Job 失败: %s", e)
                return {
                    "status": "error",
                    "message": f"创建定时推送失败: {e}",
                    "config": config,
                }

        api.register_http_router(router, prefix="/erp-permissions",
                                     tags=["erp"])
        api.register_http_router(digest_router, prefix="/erp/digest",
                                     tags=["erp"])

        logger.info("Kingdee backend: routes registered (including digest)")

    def get_client(self, config: Dict[str, Any]) -> Any:
        """根据配置创建金蝶客户端"""
        required = ["server_url", "acct_id", "user_name", "app_id", "app_secret"]
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(f"金蝶连接配置不完整，缺少: {', '.join(missing)}。请在「连接配置」中填写。")
        return KingdeeClient(
            server_url=config["server_url"],
            acct_id=config["acct_id"],
            user_name=config["user_name"],
            app_id=config["app_id"],
            app_secret=config["app_secret"],
        )

    async def health_check(self, config: Dict[str, Any]) -> bool:
        """健康检查：验证金蝶 WebAPI 连接"""
        try:
            client = self.get_client(config)
            return await client.health_check()
        except Exception as e:
            logger.error(f"金蝶健康检查失败: {e}")
            return False

    async def test_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试金蝶 WebAPI 连接。"""
        try:
            client = self.get_client(config)
            ok = await client.health_check()
            if ok:
                # 连接成功，顺便查一下有多少组织
                try:
                    result = await client.execute_bill_query(
                        "ORG_Organizations", "FNumber,FName", "", "", 100,
                    )
                    org_count = len(result)
                    return {"success": True, "message": f"连接成功，可访问 {org_count} 个组织"}
                except Exception:
                    return {"success": True, "message": "连接成功"}
            return {"success": False, "message": "连接失败，请检查配置参数"}
        except ValueError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"连接测试失败: {e}"}

    def get_metadata_dir(self) -> Optional[Path]:
        """返回金蝶元数据目录路径"""
        return Path(__file__).parent / "metadata"

    def get_health_check_tool(self) -> Optional[str]:
        """返回健康检查使用的工具名"""
        return "kingdee_query_bill"

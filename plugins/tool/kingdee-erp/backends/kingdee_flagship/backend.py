# -*- coding: utf-8 -*-
"""金蝶云星空旗舰版后端 - ERPBackend 实现"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from erp_backend import ERPBackend, with_request_id
from erp_config import ConfigManager
from erp_permissions import (
    PermissionManager, register_settings_routes,
    OPERATIONS, BUILTIN_ROLES, TOOL_OP_MAP,
)
from .domains import get_domain_map, BASE_PREFIXES
from .config_fields import FLAGSHIP_CONFIG_FIELDS, BACKEND_NAME, BACKEND_LABEL, BACKEND_ICON
from .sdk import KingdeeFlagshipClient

logger = logging.getLogger(__name__)


class KingdeeFlagshipBackend:
    """ERPBackend implementation for Kingdee Cloud Flagship (旗舰版)."""

    # ── ERPBackend Protocol 属性 ─────────────────────────────

    @property
    def system_name(self) -> str:
        return BACKEND_NAME  # "kingdee_flagship"

    @property
    def display_name(self) -> str:
        return BACKEND_LABEL  # "金蝶云星空旗舰版"

    @property
    def label(self) -> str:
        return "旗舰版"

    @property
    def config_fields(self) -> List[Dict[str, Any]]:
        return FLAGSHIP_CONFIG_FIELDS

    @property
    def domains(self) -> Dict[str, List[str]]:
        return get_domain_map()

    # ── ERPBackend Protocol 方法 ─────────────────────────────

    def register_tools(self, api) -> int:
        """注册旗舰版工具函数"""
        from .tools import (
            kingdee_flagship_describe_form,
            kingdee_flagship_request_v2,
            kingdee_flagship_list_user_orgs,
            kingdee_flagship_search_form,
            kingdee_flagship_switch_org,
        )

        tools = [
            ("kingdee_flagship_describe_form", kingdee_flagship_describe_form,
             "旗舰版：查询表单的 V2 API 请求参数定义，调用 V2 API 前先用此工具了解参数"),
            ("kingdee_flagship_request_v2", kingdee_flagship_request_v2,
             "旗舰版 V2 RESTful API 通用请求，先用 describe_form 查看参数格式再调用"),
            ("kingdee_flagship_list_user_orgs", kingdee_flagship_list_user_orgs,
             "旗舰版：查询用户有权限的组织列表"),
            ("kingdee_flagship_search_form", kingdee_flagship_search_form,
             "旗舰版：模糊搜索表单，返回匹配的 FormId 列表"),
            ("kingdee_flagship_switch_org", kingdee_flagship_switch_org,
             "旗舰版：切换当前默认组织（本地记录）"),
        ]

        count = 0
        for tool_name, tool_func, description in tools:
            try:
                wrapped = with_request_id(tool_name)(tool_func)
                api.register_tool(
                    tool_name=tool_name,
                    tool_func=wrapped,
                    description=description,
                )
                count += 1
            except Exception as e:
                logger.warning("注册工具 %s 失败: %s", tool_name, e)

        logger.info("Kingdee Flagship backend: %d tools registered", count)
        return count

    def register_routes(self, api) -> None:
        """注册旗舰版路由"""
        router = APIRouter()

        @router.get("/health")
        async def flagship_health():
            """旗舰版健康检查"""
            cfg = ConfigManager.get_config("kingdee_flagship")
            if not cfg:
                return {"status": "not_configured", "message": "旗舰版未配置"}
            try:
                client = self.get_client(cfg)
                ok = await client.health_check()
                return {"status": "ok" if ok else "error",
                        "message": "连接正常" if ok else "连接失败"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @router.post("/test-connection")
        async def flagship_test_connection():
            """旗舰版连接测试"""
            cfg = ConfigManager.get_config("kingdee_flagship")
            if not cfg:
                return {"success": False, "message": "旗舰版未配置"}
            try:
                result = await self.test_connection(cfg)
                return result
            except Exception as e:
                return {"success": False, "message": str(e)}

        # ── 元数据路由（注册到 perm_router，前缀 /erp-flagship-permissions）──

        perm_router = APIRouter()
        perm_mgr = PermissionManager()

        @perm_router.get("/meta/orgs")
        async def flagship_list_orgs():
            """查询旗舰版全部组织列表（用于前端组织选择器）"""
            try:
                cfg = ConfigManager.get_config("kingdee_flagship")
                if not cfg:
                    return {"orgs": [], "error": "旗舰版连接配置为空，请在「连接配置」中填写连接参数"}
                client = self.get_client(cfg)
                result = await client.request_v2("bos_org", "getList", {})
                rows = result if isinstance(result, list) else result.get("data", []) if isinstance(result, dict) else []
                if rows and isinstance(rows[0], dict):
                    orgs = [{"org_id": row.get("number", ""), "org_name": row.get("name", "")} for row in rows]
                else:
                    orgs = [{"org_id": row[0], "org_name": row[1]} for row in rows if len(row) >= 2]
                return {"orgs": orgs}
            except ValueError as e:
                logger.warning("旗舰版配置不完整: %s", e)
                return {"orgs": [], "error": str(e)}
            except Exception as e:
                logger.warning("旗舰版查询组织列表失败: %s", e)
                return {"orgs": [], "error": f"查询旗舰版组织失败: {e}"}

        @perm_router.get("/meta/domains")
        def flagship_list_domains():
            """查询旗舰版可用的业务域列表（用于前端业务域选择器）"""
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

        # ── 审计日志路由 ────────────────────────────────────────

        @perm_router.get("/audit")
        def flagship_audit_log(
            limit: int = Query(100, ge=1, le=1000),
            operator: str = Query(""),
            action: str = Query(""),
            form_id: str = Query(""),
        ):
            """查询旗舰版审计日志"""
            return perm_mgr.list_audit_log(
                limit=limit, operator=operator,
                action=action, form_id=form_id,
            )

        @perm_router.get("/audit/export")
        def flagship_audit_export(
            limit: int = Query(5000, ge=1, le=10000),
            operator: str = Query(""),
            action: str = Query(""),
            form_id: str = Query(""),
        ):
            """导出旗舰版审计日志为 Excel 文件"""
            rows = perm_mgr.list_audit_log(
                limit=limit, operator=operator,
                action=action, form_id=form_id,
            )
            filepath = perm_mgr._export_audit_to_excel(rows)
            if not filepath:
                return {"error": "导出失败"}
            return StreamingResponse(
                open(filepath, "rb"),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f'attachment; filename="flagship_audit_log.xlsx"'
                },
            )

        # 注册权限设置路由（复用经典版权限框架）
        register_settings_routes(perm_router, "kingdee_flagship")

        api.register_http_router(router, prefix="/erp-flagship", tags=["erp-flagship"])
        api.register_http_router(perm_router, prefix="/erp-flagship-permissions",
                                  tags=["erp-flagship"])
        logger.info("Kingdee Flagship backend: routes registered")

    def get_client(self, config: Dict[str, Any]) -> Any:
        """根据配置创建旗舰版客户端"""
        required = ["server_url", "app_id", "app_secret", "tenantid", "account_id", "user_name"]
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(
                f"旗舰版连接配置不完整，缺少: {', '.join(missing)}。请在「连接配置」中填写。"
            )
        return KingdeeFlagshipClient(
            server_url=config["server_url"],
            app_id=config["app_id"],
            app_secret=config["app_secret"],
            tenantid=config["tenantid"],
            account_id=config["account_id"],
            user_name=config["user_name"],
            kd_language=config.get("kd_language", "zh_CN"),
        )

    async def health_check(self, config: Dict[str, Any]) -> bool:
        """健康检查：验证旗舰版连接"""
        try:
            client = self.get_client(config)
            return await client.health_check()
        except Exception as e:
            logger.error(f"旗舰版健康检查失败: {e}")
            return False

    async def test_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试旗舰版连接"""
        try:
            client = self.get_client(config)
            ok = await client.health_check()
            if ok:
                return {"success": True, "message": "旗舰版连接成功"}
            return {"success": False, "message": "旗舰版连接失败，请检查配置参数"}
        except ValueError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"连接测试失败: {e}"}

    def get_metadata_dir(self) -> Optional[Path]:
        """旗舰版复用经典版的元数据目录"""
        return Path(__file__).parent.parent / "kingdee" / "metadata"

    def get_health_check_tool(self) -> Optional[str]:
        return "kingdee_flagship_describe_form"

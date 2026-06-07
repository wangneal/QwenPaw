# -*- coding: utf-8 -*-
"""金蝶后端 - 金蝶云星空 WebAPI 的 ERPBackend 实现"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from erp_backend import ERPBackend, with_request_id
from erp_config import ConfigManager
from erp_permissions import (
    PermissionManager, register_settings_routes,
    OPERATIONS, BUILTIN_ROLES, TOOL_OP_MAP,
    resolve_row_filter,
    make_org_context_key, set_default_org_context,
)
from .domains import get_domain_map, BASE_PREFIXES
from .config_fields import KINGDEE_CONFIG_FIELDS, BACKEND_NAME, BACKEND_LABEL, BACKEND_ICON
from .prompts import TOOL_DEFINITIONS
from .sdk import KingdeeClient

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 内置文档 HTML — 教程 / FAQ / 更新日志
# ═══════════════════════════════════════════════════════════════════════════

def _docs_html(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - 星智 StarMind</title>
<style>
:root {{--bg:#fff;--fg:#1a1a2e;--muted:#6b7280;--accent:#4f46e5;--card:#f9fafb;--border:#e5e7eb;}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f172a;--fg:#e2e8f0;--muted:#94a3b8;--accent:#818cf8;--card:#1e293b;--border:#334155;}}}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--fg);line-height:1.75;padding:2rem;max-width:800px;margin:0 auto;}}
h1{{font-size:1.75rem;margin-bottom:1rem;color:var(--accent);}}
h2{{font-size:1.25rem;margin:1.5rem 0 0.75rem;border-bottom:1px solid var(--border);padding-bottom:0.25rem;}}
h3{{font-size:1.05rem;margin:1rem 0 0.5rem;}}
p,li{{margin:0.4rem 0;}}
ul,ol{{padding-left:1.5rem;}}
code{{background:var(--card);padding:0.15rem 0.4rem;border-radius:4px;font-size:0.9em;border:1px solid var(--border);}}
pre{{background:var(--card);padding:1rem;border-radius:8px;overflow-x:auto;margin:0.75rem 0;border:1px solid var(--border);}}
pre code{{background:none;padding:0;border:none;}}
.tip{{background:var(--card);border-left:3px solid var(--accent);padding:0.75rem 1rem;border-radius:0 8px 8px 0;margin:1rem 0;}}
.tip strong{{color:var(--accent);}}
a{{color:var(--accent);text-decoration:none;}}
a:hover{{text-decoration:underline;}}
</style>
</head>
<body>
{content}
</body>
</html>"""

_DOCS_HTML_ZH = _docs_html("使用教程", """
<h1>星智 StarMind 使用教程</h1>

<h2>一、快速开始</h2>
<p>星智 StarMind 是一个 AI 智能助手平台，集成了金蝶云星空 ERP 能力，可以通过自然语言完成业务操作。</p>

<div class="tip"><strong>提示：</strong>首次使用前，请确保管理员已在「设置」中配置金蝶 ERP 连接信息。</div>

<h2>二、与 AI 对话</h2>
<p>在对话框中输入自然语言即可与 AI 交流，AI 会自动调用合适的工具完成任务。</p>
<h3>示例对话</h3>
<ul>
<li><code>查询最近10条销售订单</code></li>
<li><code>查看客户"华为技术"的详细信息</code></li>
<li><code>查询物料 F001 的库存</code></li>
<li><code>查询今天的收款单据</code></li>
</ul>

<h2>三、金蝶 ERP 工具</h2>
<p>星智内置以下金蝶云星空工具，AI 会根据你的需求自动选择：</p>
<ul>
<li><strong>查询单据</strong>：按编号或条件查询单据详情</li>
<li><strong>查询列表</strong>：按条件查询单据列表，支持分页</li>
<li><strong>保存单据</strong>：创建或修改单据（需确认）</li>
<li><strong>删除单据</strong>：删除指定单据（需确认）</li>
<li><strong>提交/审核</strong>：单据流程操作</li>
<li><strong>查询物料库存</strong>：查询物料的实时库存</li>
<li><strong>查询客户/供应商</strong>：查询基础资料信息</li>
</ul>

<div class="tip"><strong>安全提示：</strong>涉及写入、删除、审核等操作时，AI 会展示操作摘要并要求你确认后才会执行。</div>

<h2>四、代码模式</h2>
<p>点击顶部的「代码模式」切换按钮，可以查看和编辑 Agent 的工作区文件。</p>
<p>工作区中存放 Agent 的配置文件、技能文件等。你可以自由编辑这些文件来定制 Agent 行为。</p>

<div class="tip"><strong>注意：</strong>系统源码和内置插件代码为只读，不可修改。</div>

<h2>五、权限管理</h2>
<p>管理员可通过「ERP 权限管理」页面为不同渠道配置金蝶 ERP 的操作权限：</p>
<ul>
<li>按渠道（如微信、钉钉、飞书）配置不同的权限策略</li>
<li>限制可操作的表单类型（如只允许查询，不允许修改）</li>
<li>限制可查询的数据范围</li>
</ul>

<h2>六、多语言支持</h2>
<p>星智支持中文、英文、俄文界面，点击顶部语言切换按钮即可切换。</p>
""")

_DOCS_HTML_EN = _docs_html("Tutorial", """
<h1>StarMind Tutorial</h1>

<h2>1. Getting Started</h2>
<p>StarMind is an AI assistant platform integrated with Kingdee Cloud ERP capabilities. You can complete business operations using natural language.</p>

<div class="tip"><strong>Tip:</strong> Before first use, make sure the administrator has configured the Kingdee ERP connection in Settings.</div>

<h2>2. Chat with AI</h2>
<p>Simply type in natural language and the AI will automatically invoke the appropriate tools.</p>
<h3>Example Prompts</h3>
<ul>
<li><code>Query the last 10 sales orders</code></li>
<li><code>View details for customer "Huawei"</code></li>
<li><code>Check inventory for material F001</code></li>
<li><code>Query today's payment receipts</code></li>
</ul>

<h2>3. Kingdee ERP Tools</h2>
<p>StarMind includes the following Kingdee Cloud tools — the AI selects the right one automatically:</p>
<ul>
<li><strong>Query Bill</strong>: Look up bill details by number or conditions</li>
<li><strong>Query List</strong>: Search bill lists with filters and pagination</li>
<li><strong>Save Bill</strong>: Create or modify bills (confirmation required)</li>
<li><strong>Delete Bill</strong>: Remove bills (confirmation required)</li>
<li><strong>Submit/Approve</strong>: Workflow operations</li>
<li><strong>Query Inventory</strong>: Real-time stock levels</li>
<li><strong>Query Customer/Vendor</strong>: Master data lookup</li>
</ul>

<div class="tip"><strong>Security:</strong> Write, delete, and approve operations require your confirmation before execution.</div>

<h2>4. Coding Mode</h2>
<p>Toggle "Coding Mode" in the header to view and edit Agent workspace files such as configurations and skills.</p>

<div class="tip"><strong>Note:</strong> System source code and built-in plugins are read-only.</div>

<h2>5. Permission Management</h2>
<p>Administrators can configure Kingdee ERP permissions per channel (WeChat, DingTalk, Feishu, etc.) through the ERP Admin panel.</p>

<h2>6. Multi-language</h2>
<p>StarMind supports Chinese, English, and Russian UI. Use the language switcher in the header.</p>
""")

_FAQ_HTML_ZH = _docs_html("常见问题", """
<h1>常见问题</h1>

<h2>Q: 如何配置金蝶 ERP 连接？</h2>
<p>A: 管理员登录后，进入「设置 → ERP 配置」，填写金蝶云星空的 API 地址、数据库标识、用户名和密码，保存即可。</p>

<h2>Q: AI 调用金蝶接口时报错怎么办？</h2>
<p>A: 常见原因：</p>
<ul>
<li>连接信息未配置或配置错误 — 请检查设置中的 ERP 配置</li>
<li>金蝶账号权限不足 — 请联系金蝶管理员分配相应权限</li>
<li>网络不通 — 请确认服务器可以访问金蝶 API 地址</li>
</ul>

<h2>Q: 如何限制 AI 只能查询不能修改？</h2>
<p>A: 在「ERP 权限管理」中，可以为渠道配置权限策略，选择"只读"模式即可限制为仅查询操作。</p>

<h2>Q: 代码模式中为什么有些文件无法编辑？</h2>
<p>A: 系统源码和内置插件代码为只读保护，防止误操作导致系统异常。你只能编辑 Agent 工作区中的文件。</p>

<h2>Q: 如何添加新的 AI Agent？</h2>
<p>A: 在左侧导航栏点击「+ 新建对话」，选择或创建一个 Agent 即可。Agent 的行为由 Persona（角色）和 Skill（技能）文件定义。</p>

<h2>Q: 数据存储在哪里？安全吗？</h2>
<p>A: 所有数据存储在 Docker 数据卷中，不会外传。金蝶连接信息以加密方式存储。建议在生产环境中使用 HTTPS 和适当的网络安全策略。</p>

<h2>Q: 支持哪些金蝶云星空版本？</h2>
<p>A: 支持金蝶云星空 V8 及以上版本的 WebAPI 接口。如果你的版本较旧，请联系技术支持确认兼容性。</p>

<h2>Q: 如何更新星智？</h2>
<p>A: 点击顶部的版本号查看更新指南。自托管部署通过重建 Docker 镜像更新，数据卷会自动保留。</p>
""")

_FAQ_HTML_EN = _docs_html("FAQ", """
<h1>Frequently Asked Questions</h1>

<h2>Q: How to configure Kingdee ERP connection?</h2>
<p>A: After logging in as admin, go to Settings → ERP Configuration, fill in the Kingdee Cloud API URL, database ID, username and password, then save.</p>

<h2>Q: What if the AI returns an error when calling Kingdee APIs?</h2>
<p>A: Common causes:</p>
<ul>
<li>Missing or incorrect connection info — check ERP configuration in Settings</li>
<li>Insufficient Kingdee account permissions — contact your Kingdee admin</li>
<li>Network unreachable — verify the server can access the Kingdee API URL</li>
</ul>

<h2>Q: How to restrict AI to read-only mode?</h2>
<p>A: In ERP Permission Management, configure a "Read-Only" policy for the channel to restrict to query operations only.</p>

<h2>Q: Why are some files not editable in Coding Mode?</h2>
<p>A: System source code and built-in plugins are read-only to prevent accidental damage. You can only edit files in the Agent workspace.</p>

<h2>Q: How to add a new AI Agent?</h2>
<p>A: Click "+ New Conversation" in the sidebar, then select or create an Agent. Agent behavior is defined by Persona and Skill files.</p>

<h2>Q: Where is data stored? Is it secure?</h2>
<p>A: All data is stored in Docker volumes and never transmitted externally. Kingdee credentials are encrypted. Use HTTPS and proper network security in production.</p>

<h2>Q: Which Kingdee Cloud versions are supported?</h2>
<p>A: Kingdee Cloud V8+ WebAPI interfaces are supported. Contact support for older version compatibility.</p>

<h2>Q: How to update StarMind?</h2>
<p>A: Click the version badge in the header for the update guide. Self-hosted deployments update by rebuilding the Docker image; data volumes are preserved.</p>
""")

_RELEASE_NOTES_HTML_ZH = _docs_html("更新日志", """
<h1>星智 StarMind 更新日志</h1>

<h2>v1.0.0 — 初始版本</h2>
<ul>
<li>基于 QwenPaw 白标定制</li>
<li>集成金蝶云星空 WebAPI 全量工具</li>
<li>ERP 权限管理前端</li>
<li>内置金蝶 ERP Agent Persona 和 Skill</li>
<li>代码模式路径保护（系统源码只读）</li>
<li>内置文档（教程 / FAQ / 更新日志）</li>
<li>品牌定制：星智 StarMind</li>
</ul>
""")

_RELEASE_NOTES_HTML_EN = _docs_html("Release Notes", """
<h1>StarMind Release Notes</h1>

<h2>v1.0.0 — Initial Release</h2>
<ul>
<li>White-label customization based on QwenPaw</li>
<li>Integrated Kingdee Cloud WebAPI tools</li>
<li>ERP Permission Management UI</li>
<li>Built-in Kingdee ERP Agent Persona and Skills</li>
<li>Coding Mode path protection (system code read-only)</li>
<li>Built-in documentation (Tutorial / FAQ / Release Notes)</li>
<li>Brand customization: StarMind</li>
</ul>
""")


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

        for item in TOOL_DEFINITIONS:
            name = item["name"]
            func = getattr(kingdee_tools, name)
            wrapped = with_request_id(name)(func)
            api.register_tool(tool_name=name, tool_func=wrapped,
                              description=item["description"],
                              icon=item.get("icon", "erp"))

        logger.info(f"Kingdee backend: {len(TOOL_DEFINITIONS)} tools registered")
        return len(TOOL_DEFINITIONS)

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
            """权限请求体（向后兼容 access 字段）"""
            key: str
            org_id: str = "*"
            display_name: str = ""
            domains: list = []
            access: str = "readonly"
            role: str = ""
            operations: list = []

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

        def _request_context_scope(
            request: Request,
            channel: str = "",
            user_id: str = "",
            agent_id: str = "",
        ) -> dict:
            """Resolve the same default-org scope used by console chat tools."""
            resolved_channel = (channel or "").strip() or "console"
            resolved_user = (user_id or "").strip() or "default"
            resolved_agent = (
                (agent_id or "").strip()
                or request.headers.get("X-Agent-Id", "").strip()
            )
            if not resolved_agent:
                try:
                    from qwenpaw.app.agent_context import get_active_agent_id
                    resolved_agent = get_active_agent_id()
                except Exception:
                    resolved_agent = "default"
            return {
                "channel": resolved_channel,
                "user_id": resolved_user,
                "agent_id": resolved_agent or "default",
                "context_key": make_org_context_key(
                    resolved_channel,
                    resolved_user,
                    resolved_agent or "default",
                ),
            }

        async def _org_name(org_id: str) -> str:
            if not org_id:
                return ""
            enriched = await _enrich_with_org_names([{"org_id": org_id}])
            return enriched[0].get("org_name", org_id) if enriched else org_id

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

        # ── 默认组织上下文（WebUI/Console 首次使用闭环）──

        class OrgContextBody(BaseModel):
            """当前用户默认组织请求体"""
            org_id: str
            channel: str = ""
            user_id: str = ""
            agent_id: str = ""

        @router.get("/org-context")
        async def get_org_context(
            request: Request,
            channel: str = Query(""),
            user_id: str = Query(""),
            agent_id: str = Query(""),
        ):
            """查询当前 agent/channel/user 作用域下的默认金蝶组织。"""
            scope = _request_context_scope(request, channel, user_id, agent_id)
            org_id = mgr.get_default_org(scope["context_key"], self.system_name) or ""
            return {
                **scope,
                "system_name": self.system_name,
                "org_id": org_id,
                "org_name": await _org_name(org_id),
            }

        @router.put("/org-context")
        async def set_org_context(request: Request, body: OrgContextBody):
            """设置当前 agent/channel/user 作用域下的默认金蝶组织。"""
            scope = _request_context_scope(
                request,
                body.channel,
                body.user_id,
                body.agent_id,
            )
            ok, err = set_default_org_context(
                mgr,
                scope["channel"],
                scope["user_id"],
                self.system_name,
                body.org_id,
                scope["agent_id"],
            )
            if not ok:
                return {"status": "error", "message": err, **scope}
            return {
                "status": "ok",
                **scope,
                "system_name": self.system_name,
                "org_id": body.org_id,
                "org_name": await _org_name(body.org_id),
            }

        @router.delete("/org-context")
        def clear_org_context(
            request: Request,
            channel: str = Query(""),
            user_id: str = Query(""),
            agent_id: str = Query(""),
        ):
            """清除当前 agent/channel/user 作用域下的默认金蝶组织。"""
            scope = _request_context_scope(request, channel, user_id, agent_id)
            mgr.clear_default_org(scope["context_key"], self.system_name)
            return {
                "status": "ok",
                **scope,
                "system_name": self.system_name,
                "org_id": "",
            }

        # ── CRUD 路由 ──

        @router.get("/")
        async def list_perms():
            """查询全部权限列表（含组织名称）"""
            items = mgr.list_permissions()
            return {"items": await _enrich_with_org_names(items)}

        @router.post("/")
        def set_perm(body: PermBody):
            """新增或更新单个组织权限（支持 role/operations，向后兼容 access）"""
            # 角色解析：优先 role 字段，回退到 access 映射
            role = body.role
            if not role:
                # 向后兼容：readonly→viewer，writeable→operator。
                # 旧 access 只有两档，不能安全表达删除/审核等高风险权限。
                role = "viewer" if body.access == "readonly" else "operator"
            # 如果 role 是内置角色且未指定 operations，使用角色默认操作码
            operations = body.operations if body.operations else None
            mgr.set_permission(
                key=body.key, org_id=body.org_id,
                display_name=body.display_name, domains=body.domains,
                access=body.access, role=role, operations=operations,
            )
            return {"status": "ok", "key": body.key, "org_id": body.org_id, "role": role}

        @router.delete("/{key}/{org_id}")
        def del_perm(key: str, org_id: str):
            """删除指定用户的指定组织权限"""
            mgr.remove_permission(key, org_id)
            return {"status": "ok"}

        # ── 角色管理端点（必须在 /{key} 之前注册）──

        class RoleBody(BaseModel):
            """自定义角色请求体"""
            name: str
            label: str = ""
            operations: list = []

        @router.get("/roles")
        def list_roles():
            """列出所有角色（内置 + 自定义）"""
            return {"roles": mgr.list_roles()}

        @router.post("/roles")
        def create_role(body: RoleBody):
            """创建自定义角色"""
            try:
                mgr.set_role(name=body.name, label=body.label, operations=body.operations)
                return {"status": "ok", "name": body.name}
            except ValueError as e:
                return {"status": "error", "message": str(e)}

        @router.put("/roles/{name}")
        def update_role(name: str, body: RoleBody):
            """更新自定义角色"""
            try:
                mgr.set_role(name=name, label=body.label, operations=body.operations)
                return {"status": "ok", "name": name}
            except ValueError as e:
                return {"status": "error", "message": str(e)}

        @router.delete("/roles/{name}")
        def delete_role(name: str):
            """删除自定义角色（内置角色不可删）"""
            try:
                mgr.delete_role(name)
                return {"status": "ok", "name": name}
            except ValueError as e:
                return {"status": "error", "message": str(e)}

        # ── 操作码元数据端点 ──

        @router.get("/operations")
        def list_operations():
            """返回所有操作码定义（label, tools, risk）"""
            return {"operations": OPERATIONS}

        # ── 字段级权限端点（必须在 /{key} 之前注册）──

        class FieldPermBody(BaseModel):
            """字段权限请求体"""
            key: str
            org_id: str = "*"
            form_id: str
            field_name: str
            permission: str = "visible"

        @router.get("/field-permissions")
        def list_field_perms(
            key: str = Query(""),
            org_id: str = Query(""),
            form_id: str = Query(""),
        ):
            """列出字段权限（支持可选过滤）"""
            items = mgr.list_field_permissions(key=key, org_id=org_id, form_id=form_id)
            return {"items": items}

        @router.post("/field-permissions")
        def set_field_perm(body: FieldPermBody):
            """设置字段权限"""
            try:
                mgr.set_field_permission(
                    key=body.key, org_id=body.org_id,
                    form_id=body.form_id, field_name=body.field_name,
                    permission=body.permission,
                )
                return {"status": "ok"}
            except ValueError as e:
                return {"status": "error", "message": str(e)}

        @router.delete("/field-permissions")
        def delete_field_perm(
            key: str = Query(...),
            org_id: str = Query(...),
            form_id: str = Query(...),
            field_name: str = Query(...),
        ):
            """删除指定字段权限"""
            mgr.remove_field_permission(key, org_id, form_id, field_name)
            return {"status": "ok"}

        @router.get("/field-permissions/{key}/{org_id}/{form_id}")
        def get_field_perms(key: str, org_id: str, form_id: str):
            """获取用户+组织+表单的所有字段权限"""
            perms = mgr.get_field_permissions(key, org_id, form_id)
            return {"key": key, "org_id": org_id, "form_id": form_id, "permissions": perms}

        # ── 用户操作权限查询端点（必须在 /{key} 之前注册）──

        @router.get("/{key}/operations")
        def get_user_operations(
            key: str,
            org_id: str = Query(""),
            domain: str = Query(""),
        ):
            """查询用户在指定上下文下允许的操作列表"""
            if not org_id:
                return {"error": "请指定 org_id 参数", "operations": []}
            operations = mgr.get_user_operations(key, org_id, domain)
            return {"key": key, "org_id": org_id, "domain": domain, "operations": operations}

        # ── 行级过滤端点（必须在 /{key} 之前注册）──

        class RowFilterBody(BaseModel):
            """行级过滤请求体"""
            key: str
            org_id: str = "*"
            form_id: str
            filter_expr: str = ""

        @router.get("/row-filters")
        def list_row_filters(
            key: str = Query(""),
            org_id: str = Query(""),
            form_id: str = Query(""),
        ):
            """列出行级过滤规则（支持可选过滤条件）"""
            items = mgr.list_row_filters(key=key, org_id=org_id, form_id=form_id)
            return {"items": items}

        @router.post("/row-filters")
        def set_row_filter(body: RowFilterBody):
            """设置行级过滤规则"""
            mgr.set_row_filter(
                key=body.key, org_id=body.org_id,
                form_id=body.form_id, filter_expr=body.filter_expr,
            )
            return {
                "status": "ok",
                "key": body.key,
                "org_id": body.org_id,
                "form_id": body.form_id,
            }

        @router.delete("/row-filters")
        def delete_row_filter(
            key: str = Query(...),
            org_id: str = Query(...),
            form_id: str = Query(...),
        ):
            """删除行级过滤规则"""
            mgr.remove_row_filter(key=key, org_id=org_id, form_id=form_id)
            return {"status": "ok"}

        @router.get("/row-filters/{key}/{org_id}/{form_id}")
        def get_row_filter(key: str, org_id: str, form_id: str):
            """获取指定用户+组织+表单的行级过滤规则"""
            expr = mgr.get_row_filter(key=key, org_id=org_id, form_id=form_id)
            if expr is None:
                return {"key": key, "org_id": org_id, "form_id": form_id, "filter_expr": None}
            return {
                "key": key,
                "org_id": org_id,
                "form_id": form_id,
                "filter_expr": expr,
            }

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

        # ── 内置文档路由（教程 / FAQ）──────────────────────────

        docs_router = APIRouter()

        @docs_router.get("")
        async def docs_page(lang: str = "zh"):
            """返回内置教程文档 HTML 页面"""
            from fastapi.responses import HTMLResponse
            if lang == "zh":
                html = _DOCS_HTML_ZH
            else:
                html = _DOCS_HTML_EN
            return HTMLResponse(content=html)

        @docs_router.get("/faq")
        async def faq_page(lang: str = "zh"):
            """返回内置 FAQ 文档 HTML 页面"""
            from fastapi.responses import HTMLResponse
            if lang == "zh":
                html = _FAQ_HTML_ZH
            else:
                html = _FAQ_HTML_EN
            return HTMLResponse(content=html)

        @docs_router.get("/release-notes")
        async def release_notes_page(lang: str = "zh"):
            """返回更新日志 HTML 页面"""
            from fastapi.responses import HTMLResponse
            if lang == "zh":
                html = _RELEASE_NOTES_HTML_ZH
            else:
                html = _RELEASE_NOTES_HTML_EN
            return HTMLResponse(content=html)

        api.register_http_router(docs_router, prefix="/erp/docs",
                                      tags=["erp"])
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

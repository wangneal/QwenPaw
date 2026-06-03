# -*- coding: utf-8 -*-
"""ERP Permission filtering for multi-backend support.

SQLite-backed per-user, per-org data access control:
- Per-organization business domain restrictions
- Per-organization read/write access levels
- Organization scope filtering for queries
- Domain resolution from registered backends
"""

import asyncio
import csv
import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from erp_backend import get_registry, get_current_request_id

logger = logging.getLogger(__name__)

DEFAULT_DB_DIR = os.path.expanduser("~/.qwenpaw/plugin_data/erp")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "permissions.db")
DEFAULT_ARCHIVE_DIR = os.path.join(DEFAULT_DB_DIR, "audit_archive")
AUDIT_LOG_MAX = 10000
AUDIT_LOG_EXPORT_BATCH = 5000


def _get_admin_contact(system_name: str = "") -> str:
    """Get admin contact info from backend config."""
    try:
        from erp_config import ConfigManager
        cfg = ConfigManager.get_config(system_name)
        if cfg and cfg.get("admin_contact"):
            return f"\n管理员联系方式: {cfg['admin_contact']}"
    except Exception as e:
        logger.debug("从 ConfigManager 获取管理员联系方式失败: %s", e)

    # Fallback: 从 backend config_fields 的 placeholder 读取
    try:
        reg = get_registry()
        backend = reg.get(system_name) if system_name else None
        if backend:
            for field in backend.config_fields:
                if field.get("name") == "admin_contact":
                    placeholder = field.get("placeholder", "")
                    if placeholder:
                        return f"\n管理员联系方式: {placeholder}"
    except Exception as e:
        logger.debug("获取管理员联系方式失败: %s", e)
    return ""


class PermissionManager:
    """SQLite-backed per-user, per-org permission manager.

    Schema v2: PRIMARY KEY (key, org_id)
    Each row = one user's permissions for one organization.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_permissions (
                    key TEXT NOT NULL,
                    display_name TEXT,
                    org_id TEXT NOT NULL DEFAULT '*',
                    domains TEXT DEFAULT '[]',
                    access TEXT DEFAULT 'readonly',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (key, org_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perm_key
                ON user_permissions(key)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT DEFAULT '',
                    operator TEXT NOT NULL,
                    action TEXT NOT NULL,
                    form_id TEXT,
                    target TEXT,
                    detail TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_created
                ON audit_log(created_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_request_id
                ON audit_log(request_id)
            """)
            # 自定义字段映射表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kd_field_mappings (
                    form_id TEXT PRIMARY KEY,
                    form_name TEXT,
                    fields TEXT DEFAULT '[]',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────

    def set_permission(
        self, key: str, org_id: str, display_name: str = "",
        domains: list = None, access: str = "readonly",
    ):
        """Set permission for a user+org combination.

        Args:
            key: User identifier ("channel:user_id")
            org_id: Organization ID ("01", "02", or "*" for wildcard)
            display_name: Display name
            domains: List of allowed business domains
            access: "readonly" or "writeable"
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_permissions
                (key, display_name, org_id, domains, access, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, display_name, org_id, json.dumps(domains or []), access))
            conn.commit()

    def get_permission(self, key: str, org_id: str) -> Optional[Dict]:
        """Get permission for a specific user+org."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM user_permissions WHERE key = ? AND org_id = ?",
                (key, org_id),
            ).fetchone()
            if row:
                return {
                    "key": row["key"],
                    "display_name": row["display_name"],
                    "org_id": row["org_id"],
                    "domains": json.loads(row["domains"]),
                    "access": row["access"],
                }
        return None

    def list_user_orgs(self, key: str) -> List[Dict]:
        """List all org permissions for a user.

        Returns:
            List of {"org_id": "...", "domains": [...], "access": "..."}
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT org_id, domains, access FROM user_permissions WHERE key = ? ORDER BY org_id",
                (key,),
            ).fetchall()
            return [
                {
                    "org_id": r["org_id"],
                    "domains": json.loads(r["domains"]),
                    "access": r["access"],
                }
                for r in rows
            ]

    def list_user_permissions(self, key: str) -> List[Dict]:
        """List all permissions for a user (across all orgs)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM user_permissions WHERE key = ? ORDER BY org_id",
                (key,),
            ).fetchall()
            return [
                {
                    "key": r["key"],
                    "display_name": r["display_name"],
                    "org_id": r["org_id"],
                    "domains": json.loads(r["domains"]),
                    "access": r["access"],
                }
                for r in rows
            ]

    def list_permissions(self) -> List[Dict]:
        """List all permissions (all users, all orgs)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM user_permissions ORDER BY key, org_id"
            ).fetchall()
            return [
                {
                    "key": r["key"],
                    "display_name": r["display_name"],
                    "org_id": r["org_id"],
                    "domains": json.loads(r["domains"]),
                    "access": r["access"],
                }
                for r in rows
            ]

    def remove_permission(self, key: str, org_id: str):
        """Remove permission for a specific user+org."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM user_permissions WHERE key = ? AND org_id = ?",
                (key, org_id),
            )
            conn.commit()

    def remove_user(self, key: str):
        """Remove all permissions for a user (all orgs)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM user_permissions WHERE key = ?", (key,))
            conn.commit()

    # ── Audit Log ─────────────────────────────────────────────────

    async def log_operation(
        self, operator: str, action: str,
        form_id: str = "", target: str = "", detail: str = "",
    ):
        """记录写入操作审计日志（异步归档）。request_id 从 ContextVar 自动读取。"""
        req_id = get_current_request_id()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO audit_log (request_id, operator, action, form_id, target, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (req_id, operator, action, form_id, target, detail))
            conn.commit()

        # 异步归档：文件 IO 移到线程池，不阻塞主线程
        try:
            await asyncio.to_thread(self._auto_cleanup_audit_log)
        except Exception as e:
            logger.warning(f"审计日志异步归档失败: {e}")

    def _auto_cleanup_audit_log(self):
        """Export old audit logs to Excel and delete from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

        if count <= AUDIT_LOG_MAX:
            return

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id ASC LIMIT ?",
                (AUDIT_LOG_EXPORT_BATCH,),
            ).fetchall()

        if not rows:
            return

        archive_path = self._export_audit_to_excel(rows)
        if not archive_path:
            logger.error("Audit log export failed, skipping cleanup")
            return

        min_id = rows[0]["id"]
        max_id = rows[-1]["id"]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM audit_log WHERE id >= ? AND id <= ?",
                (min_id, max_id),
            )
            conn.commit()

        logger.info(
            f"Audit log cleanup: exported {len(rows)} entries to {archive_path}, "
            f"deleted from SQLite (id {min_id}~{max_id})"
        )

    def _export_audit_to_excel(self, rows) -> Optional[str]:
        """Export audit log rows to an Excel file."""
        try:
            import openpyxl
        except ImportError:
            logger.warning("openpyxl not installed, falling back to CSV")
            return self._export_audit_to_csv(rows)

        os.makedirs(DEFAULT_ARCHIVE_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(DEFAULT_ARCHIVE_DIR, f"audit_{timestamp}.xlsx")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "审计日志"

        headers = ["ID", "请求ID", "操作人", "操作", "表单", "目标", "详情", "时间"]
        ws.append(headers)

        for r in rows:
            ws.append([
                r["id"], r["request_id"], r["operator"], r["action"],
                r["form_id"], r["target"], r["detail"], r["created_at"],
            ])

        for col in ws.columns:
            max_length = 0
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

        wb.save(filepath)
        return filepath

    def _export_audit_to_csv(self, rows) -> Optional[str]:
        """Fallback: export audit log rows to CSV if openpyxl unavailable."""
        os.makedirs(DEFAULT_ARCHIVE_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(DEFAULT_ARCHIVE_DIR, f"audit_{timestamp}.csv")

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "请求ID", "操作人", "操作", "表单", "目标", "详情", "时间"])
            for r in rows:
                writer.writerow([
                    r["id"], r["request_id"], r["operator"], r["action"],
                    r["form_id"], r["target"], r["detail"], r["created_at"],
                ])
        return filepath

    def list_audit_log(
        self, limit: int = 100, operator: str = "",
        action: str = "", form_id: str = "",
    ) -> List[Dict]:
        """Query audit log with optional filters."""
        query = "SELECT * FROM audit_log WHERE 1=1"
        params: list = []
        if operator:
            query += " AND operator = ?"
            params.append(operator)
        if action:
            query += " AND action = ?"
            params.append(action)
        if form_id:
            query += " AND form_id = ?"
            params.append(form_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "request_id": r["request_id"],
                    "operator": r["operator"],
                    "action": r["action"],
                    "form_id": r["form_id"],
                    "target": r["target"],
                    "detail": r["detail"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    # ── Field Mappings ─────────────────────────────────────────────

    def get_field_mapping(self, form_id: str) -> Optional[Dict]:
        """获取指定表单的自定义字段映射。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM kd_field_mappings WHERE form_id = ?", (form_id,)
            ).fetchone()
            if row:
                return {
                    "form_id": row["form_id"],
                    "form_name": row["form_name"],
                    "fields": json.loads(row["fields"]),
                    "updated_at": row["updated_at"],
                }
        return None

    def list_field_mappings(self, domain: str = "", search: str = "") -> List[Dict]:
        """列出所有自定义字段映射，支持域过滤和搜索。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM kd_field_mappings ORDER BY form_id"
            ).fetchall()
            results = []
            for r in rows:
                item = {
                    "form_id": r["form_id"],
                    "form_name": r["form_name"],
                    "fields": json.loads(r["fields"]),
                    "updated_at": r["updated_at"],
                }
                # 搜索过滤
                if search:
                    search_lower = search.lower()
                    if (search_lower not in item["form_id"].lower() and
                            search_lower not in (item["form_name"] or "").lower()):
                        continue
                results.append(item)
            return results

    def set_field_mapping(self, form_id: str, form_name: str, fields: List[Dict]):
        """保存自定义字段映射。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO kd_field_mappings
                (form_id, form_name, fields, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (form_id, form_name, json.dumps(fields, ensure_ascii=False)))
            conn.commit()

    def delete_field_mapping(self, form_id: str):
        """删除自定义字段映射。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM kd_field_mappings WHERE form_id = ?", (form_id,)
            )
            conn.commit()


# ── 权限检查函数 ───────────────────────────────────────────


def _resolve_domain_map(system_name: str) -> Tuple[Dict[str, List[str]], List[str]]:
    """从后端注册表解析业务域映射。"""
    try:
        reg = get_registry()
        backend = reg.get(system_name)
        if backend is not None:
            return backend.domains, getattr(backend, '_base_prefixes', ["BD_"])
    except Exception as e:
        logger.warning("解析后端域映射失败(%s): %s", system_name, e)

    if system_name == "kingdee":
        try:
            from backends.kingdee.domains import get_domain_map, BASE_PREFIXES
            return get_domain_map(), BASE_PREFIXES
        except ImportError as e:
            logger.debug("金蝶域模块导入失败: %s", e)

    return {}, []


def _check_domain_access(
    perm: Dict, system_name: str, form_id: str,
) -> Tuple[bool, List[str]]:
    """Check if a permission record allows access to a form_id.

    Returns:
        (allowed, allowed_prefixes)
    """
    domain_form_map, base_prefixes = _resolve_domain_map(system_name)

    if not domain_form_map:
        return True, []

    allowed_prefixes = []
    for domain in perm.get("domains", []):
        if ":" in domain:
            # 厂商特定域（如 "kingdee:finance" 或 "sap:finance"）
            vendor, pure_domain = domain.split(":", 1)
            if vendor and pure_domain and vendor == system_name and pure_domain in domain_form_map:
                allowed_prefixes.extend(domain_form_map[pure_domain])
        else:
            # 纯域名（如 "finance"）：向后兼容，匹配当前系统的域
            prefixed = f"{system_name}:{domain}"
            if prefixed in domain_form_map:
                allowed_prefixes.extend(domain_form_map[prefixed])
            elif domain in domain_form_map:
                allowed_prefixes.extend(domain_form_map[domain])

    if not allowed_prefixes:
        return False, []
    if any(form_id.startswith(p) for p in allowed_prefixes):
        return True, allowed_prefixes
    if any(form_id.startswith(bp) for bp in base_prefixes):
        return True, allowed_prefixes
    return False, allowed_prefixes


def check_query_permission(
    perm_mgr: PermissionManager, channel: str, user_id: str,
    system_name: str, form_id: str, org_id: str = "",
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check query permission for a specific org.

    Args:
        perm_mgr: PermissionManager instance
        channel: User channel
        user_id: User identifier
        system_name: ERP system name
        form_id: FormId being queried
        org_id: Organization ID (required)

    Returns:
        (allowed, error_message, org_filter_string)
    """
    key = f"{channel}:{user_id}"

    if not org_id:
        # No org specified — list available orgs for the user
        user_orgs = perm_mgr.list_user_orgs(key)
        if not user_orgs:
            return False, (
                f"您的 {system_name} 权限尚未配置（身份: {key}）。\n"
                "请联系管理员在 QwenPaw 管理页面配置您的权限。"
                + _get_admin_contact(system_name)
            ), None
        org_ids = [o["org_id"] for o in user_orgs]
        return False, (
            f"请先指定要操作的组织。您有权限的组织: {', '.join(org_ids)}"
        ), None

    perm = perm_mgr.get_permission(key, org_id)
    if perm is None:
        # Check wildcard org
        perm = perm_mgr.get_permission(key, "*")
    if perm is None:
        user_orgs = perm_mgr.list_user_orgs(key)
        if not user_orgs:
            return False, (
                f"您的 {system_name} 权限尚未配置（身份: {key}）。\n"
                "请联系管理员在 QwenPaw 管理页面配置您的权限。"
                + _get_admin_contact(system_name)
            ), None
        org_ids = [o["org_id"] for o in user_orgs]
        return False, (
            f"您没有组织 {org_id} 的权限（身份: {key}）。\n"
            f"您有权限的组织: {', '.join(org_ids)}"
            + _get_admin_contact(system_name)
        ), None

    # Domain check
    allowed, _ = _check_domain_access(perm, system_name, form_id)
    if not allowed:
        return False, (
            f"您没有在组织 {org_id} 查询 {form_id} 的权限。\n"
            f"您的业务域: {', '.join(perm['domains'])}"
            + _get_admin_contact(system_name)
        ), None

    # 注意：不生成 SQL org_filter。
    # 金蝶 WebAPI 通过登录上下文（org_num）做组织隔离，
    # SQL 注入 `FOrgId.FNumber = '{org_id}'` 在不同表单中字段名不同
    # （SAL 用 FSaleOrgId、PUR 用 FPurchaseOrgId、GL 用 FOrgId），
    # 硬编码会导致查询失败。
    return True, None, None


def check_write_permission(
    perm_mgr: PermissionManager, channel: str, user_id: str,
    system_name: str = "", form_id: str = "", org_id: str = "",
) -> Tuple[bool, Optional[str]]:
    """Check write permission for a specific org.

    Args:
        perm_mgr: PermissionManager instance
        channel: User channel
        user_id: User identifier
        system_name: ERP system name
        form_id: FormId being written
        org_id: Organization ID (required)

    Returns:
        (allowed, error_message)
    """
    key = f"{channel}:{user_id}"

    if not org_id:
        user_orgs = perm_mgr.list_user_orgs(key)
        if not user_orgs:
            sys_label = f" {system_name}" if system_name else ""
            return False, f"您的{sys_label}权限尚未配置（身份: {key}）。"
        org_ids = [o["org_id"] for o in user_orgs]
        return False, f"请先指定要操作的组织。您有权限的组织: {', '.join(org_ids)}"

    perm = perm_mgr.get_permission(key, org_id)
    if perm is None:
        perm = perm_mgr.get_permission(key, "*")
    if perm is None:
        user_orgs = perm_mgr.list_user_orgs(key)
        org_ids = [o["org_id"] for o in user_orgs]
        return False, (
            f"您没有组织 {org_id} 的权限（身份: {key}）。\n"
            f"您有权限的组织: {', '.join(org_ids) if org_ids else '无'}"
        )

    if perm["access"] != "writeable":
        return False, (
            f"您在组织 {org_id} 没有写入权限，当前为只读。请联系管理员。"
            + _get_admin_contact(system_name)
        )

    # Domain check
    if form_id:
        allowed, _ = _check_domain_access(perm, system_name, form_id)
        if not allowed:
            return False, (
                f"您没有在组织 {org_id} 写入 {form_id} 的权限。\n"
                f"您的业务域: {', '.join(perm['domains'])}"
                + _get_admin_contact(system_name)
            )

    return True, None


def check_integration_permission(
    perm_mgr: PermissionManager, channel: str, user_id: str,
    systems: list, action: str = "read", mode: str = "any",
) -> Tuple[bool, Optional[str], List[str]]:
    """Check permission for cross-system integration operations.

    Args:
        perm_mgr: PermissionManager instance
        channel: User channel
        user_id: User identifier
        systems: List of ERP system names
        action: "read" or "write"
        mode: "any" or "all"

    Returns:
        (allowed, error_message, allowed_systems)
    """
    key = f"{channel}:{user_id}"
    user_orgs = perm_mgr.list_user_orgs(key)

    if not user_orgs:
        return False, (
            f"您的权限尚未配置（身份: {key}）。\n"
            "请联系管理员在 QwenPaw 管理页面配置您的权限。"
        ), []

    # Collect all domains across all orgs
    all_domains = set()
    has_write = False
    for org_perm in user_orgs:
        all_domains.update(org_perm.get("domains", []))
        if org_perm.get("access") == "writeable":
            has_write = True

    if action == "write" and not has_write:
        return False, "您没有写入权限，当前为只读。请联系管理员。", []

    allowed_systems = []
    denied_systems = []

    for sys_name in systems:
        domain_form_map, _ = _resolve_domain_map(sys_name)
        if not domain_form_map:
            allowed_systems.append(sys_name)
            continue

        has_matching = False
        for domain in all_domains:
            if ":" in domain:
                # 厂商特定域：只有 vendor 匹配当前系统才放行
                vendor, pure = domain.split(":", 1)
                if vendor and pure and vendor == sys_name and pure in domain_form_map:
                    has_matching = True
                    break
            else:
                # 纯域名：向后兼容
                prefixed = f"{sys_name}:{domain}"
                if prefixed in domain_form_map or domain in domain_form_map:
                    has_matching = True
                    break

        if has_matching:
            allowed_systems.append(sys_name)
        else:
            denied_systems.append(sys_name)

    if mode == "all":
        if len(allowed_systems) == len(systems):
            return True, None, allowed_systems
        return False, (
            f"整合操作需要所有系统权限，但以下系统无权限: {', '.join(denied_systems)}"
        ), allowed_systems

    if allowed_systems:
        return True, None, allowed_systems
    return False, (
        f"您没有任何目标系统的访问权限。目标系统: {', '.join(systems)}"
    ), []


# ── 共享配置路由注册 ────────────────────────────────────────

def register_settings_routes(router, mgr: PermissionManager = None):
    """注册共享配置和字段映射路由到现有 router。

    Args:
        router: FastAPI APIRouter 实例
        mgr: PermissionManager 实例（可选，默认创建新实例）
    """
    from fastapi import Query as FastAPIQuery
    from pydantic import BaseModel
    from typing import List, Optional

    if mgr is None:
        mgr = PermissionManager()

    # ── 请求体模型 ──

    class FieldMappingBody(BaseModel):
        """字段映射请求体"""
        form_id: str
        form_name: str = ""
        fields: List[dict] = []

    # ── 字段映射路由 ──

    @router.get("/field-mappings")
    def list_field_mappings(
        domain: str = FastAPIQuery(""),
        search: str = FastAPIQuery(""),
    ):
        """获取字段映射列表（自定义 + 元数据）"""
        import re as _re

        # UUID 正则：过滤形如 8b8c65f3-fb08-45dd-adf6-b14079f222e8 的 form_id
        _uuid_pattern = _re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re.IGNORECASE)

        # 获取自定义映射
        custom_mappings = mgr.list_field_mappings(domain=domain, search=search)

        # 预加载 common_tables.json 的字段索引（form_id → fields）
        common_fields_map: dict = {}
        try:
            import os as _os
            import json as _json_mod
            _meta_dir = _os.path.join(_os.path.dirname(__file__), "backends", "kingdee", "metadata")
            _common_path = _os.path.join(_meta_dir, "common_tables.json")
            if _os.path.exists(_common_path):
                with open(_common_path, "r", encoding="utf-8") as _f:
                    _common_data = _json_mod.load(_f)
                for _tbl in _common_data.get("tables", []):
                    _fid = _tbl.get("form_id", "")
                    _flds = _tbl.get("fields", [])
                    if _fid and _flds:
                        common_fields_map[_fid] = _flds
        except Exception:
            pass  # common_tables.json 不存在则忽略

        # 尝试加载元数据中的表单
        try:
            import os
            import json as json_mod
            meta_dir = os.path.join(os.path.dirname(__file__), "backends", "kingdee", "metadata")
            domain_tables_path = os.path.join(meta_dir, "domain_tables.json")
            if os.path.exists(domain_tables_path):
                with open(domain_tables_path, "r", encoding="utf-8") as f:
                    domain_tables = json_mod.load(f)

                # 按域过滤
                domain_prefixes = {
                    "sales": ["SAL_"],
                    "procurement": ["PUR_"],
                    "inventory": ["STK_"],
                    "finance": ["GL_", "AR_", "AP_"],
                    "production": ["PRD_"],
                    "hr": ["HR_", "BD_Employee"],
                    "base": ["BD_"],
                }
                prefixes = domain_prefixes.get(domain, []) if domain else []

                target_domains = [domain] if domain in domain_tables else (domain_tables.keys() if not domain else [])

                for d_key in target_domains:
                    for form in domain_tables.get(d_key, []):
                        form_id = form.get("form_id", "")
                        form_name = form.get("name", "")

                        # 过滤 UUID 格式的 form_id
                        if _uuid_pattern.match(form_id):
                            continue

                        # 域过滤
                        if prefixes and not any(form_id.startswith(p) for p in prefixes):
                            continue

                        # 搜索过滤
                        if search:
                            search_lower = search.lower()
                            if (search_lower not in form_id.lower() and
                                    search_lower not in form_name.lower()):
                                continue

                        # 检查是否有自定义映射覆盖
                        custom = next(
                            (m for m in custom_mappings if m["form_id"] == form_id), None
                        )
                        if custom:
                            continue  # 自定义映射已包含此表单

                        # 从 common_tables.json 填充预设字段
                        preset_fields = common_fields_map.get(form_id, [])

                        custom_mappings.append({
                            "form_id": form_id,
                            "form_name": form_name,
                            "fields": preset_fields,
                            "source": "metadata",
                        })
        except Exception as e:
            logger.debug("加载元数据表单失败: %s", e)

        return {"items": custom_mappings}

    @router.put("/field-mappings")
    def save_field_mapping(body: FieldMappingBody):
        """保存自定义字段映射"""
        mgr.set_field_mapping(
            form_id=body.form_id,
            form_name=body.form_name,
            fields=body.fields,
        )
        return {"status": "ok", "form_id": body.form_id}

    @router.delete("/field-mappings/{form_id}")
    def delete_field_mapping(form_id: str):
        """删除自定义字段映射"""
        mgr.delete_field_mapping(form_id)
        return {"status": "ok", "form_id": form_id}

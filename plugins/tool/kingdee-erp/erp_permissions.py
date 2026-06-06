# -*- coding: utf-8 -*-
"""ERP Permission filtering for multi-backend support.

SQLite-backed per-user, per-org data access control:
- Per-organization business domain restrictions
- Per-organization role-based access (viewer/operator/manager/admin/custom)
- Per-operation permission granularity (query/view/save/submit/audit/delete/etc.)
- Organization scope filtering for queries
- Domain resolution from registered backends
- Schema versioning with automatic migration
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
SCHEMA_VERSION = 4

# ── 操作码定义 ──────────────────────────────────────────────
# 每个操作码关联一组 MCP 工具名和风险等级
OPERATIONS: Dict[str, Dict] = {
    "query":    {"label": "查询", "tools": ["kingdee_query_bill"], "risk": "low"},
    "view":     {"label": "查看详情", "tools": ["kingdee_view_bill"], "risk": "low"},
    "report":   {"label": "报表", "tools": ["kingdee_get_report", "kingdee_get_kds_report"], "risk": "low"},
    "save":     {"label": "保存/新增", "tools": ["kingdee_save_bill"], "risk": "medium"},
    "submit":   {"label": "提交审批", "tools": ["kingdee_submit_bill"], "risk": "medium"},
    "push":     {"label": "下推", "tools": ["kingdee_push_bill"], "risk": "medium"},
    "execute":  {"label": "自定义操作", "tools": ["kingdee_execute_operation"], "risk": "medium"},
    "workflow": {"label": "工作流审批", "tools": ["kingdee_workflow_audit"], "risk": "medium"},
    "audit":    {"label": "审核", "tools": ["kingdee_audit_bill"], "risk": "high"},
    "unaudit":  {"label": "反审核", "tools": ["kingdee_unaudit_bill"], "risk": "high"},
    "delete":   {"label": "删除", "tools": ["kingdee_delete_bill"], "risk": "high"},
}

# ── 内置角色定义 ─────────────────────────────────────────────
# 每个角色关联一组操作码；"*" 表示全部操作；"custom" 由用户自定义
BUILTIN_ROLES: Dict[str, Dict] = {
    "viewer":   {"label": "查看者", "operations": ["query", "view", "report"]},
    "operator": {"label": "操作员", "operations": ["query", "view", "report", "save", "submit"]},
    "manager":  {"label": "管理者", "operations": ["query", "view", "report", "save", "submit", "audit", "push"]},
    "admin":    {"label": "管理员", "operations": ["*"]},
    "custom":   {"label": "自定义", "operations": []},
}

# 工具名→操作码 反向映射（模块加载时自动构建）
TOOL_OP_MAP: Dict[str, str] = {}
for _op_code, _op_info in OPERATIONS.items():
    for _tool in _op_info["tools"]:
        TOOL_OP_MAP[_tool] = _op_code

# 旧 access 字段→新角色 映射表（用于 v3→v4 迁移和向后兼容）
_ACCESS_TO_ROLE_MAP: Dict[str, str] = {
    "readonly": "viewer",
    "writeable": "operator",
}

# ═══════════════════════════════════════════════════════════════════════════


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

    Schema v4: PRIMARY KEY (key, org_id)
    Each row = one user's permissions for one organization.
    支持基于角色（viewer/operator/manager/admin/custom）的细粒度操作权限。
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # ── 核心权限表 ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_permissions (
                    key TEXT NOT NULL,
                    display_name TEXT,
                    org_id TEXT NOT NULL DEFAULT '*',
                    domains TEXT DEFAULT '[]',
                    access TEXT DEFAULT 'readonly',
                    role TEXT DEFAULT 'viewer',
                    operations TEXT DEFAULT '[]',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (key, org_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perm_key
                ON user_permissions(key)
            """)
            # ── 角色定义表 ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    name TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    operations TEXT DEFAULT '[]',
                    is_builtin INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # ── 字段级权限表（P2 预留） ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS field_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    org_id TEXT NOT NULL DEFAULT '*',
                    form_id TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    permission TEXT DEFAULT 'visible',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(key, org_id, form_id, field_name)
                )
            """)
            # ── 行级过滤表（P3 预留） ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS row_filters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    org_id TEXT NOT NULL DEFAULT '*',
                    form_id TEXT NOT NULL,
                    filter_expr TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(key, org_id, form_id)
                )
            """)
            # ── 审计日志表 ──
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
            # ── 自定义字段映射表 ──
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kd_field_mappings (
                    form_id TEXT PRIMARY KEY,
                    form_name TEXT,
                    fields TEXT DEFAULT '[]',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        # 执行 schema 迁移
        self._migrate_schema()

    def _get_schema_version(self) -> int:
        """获取当前数据库 schema 版本。"""
        with sqlite3.connect(self.db_path) as conn:
            try:
                row = conn.execute(
                    "SELECT value FROM kd_meta WHERE key = 'schema_version'"
                ).fetchone()
                return int(row[0]) if row else 0
            except sqlite3.OperationalError:
                # kd_meta 表不存在说明是旧版本
                return 0

    def _set_schema_version(self, version: int):
        """写入 schema 版本号。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kd_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO kd_meta (key, value) VALUES ('schema_version', ?)",
                (str(version),),
            )
            conn.commit()

    def _migrate_schema(self):
        """执行增量 schema 迁移。按版本号逐步升级，保证不丢数据。"""
        current = self._get_schema_version()
        if current >= SCHEMA_VERSION:
            return

        logger.info("权限数据库 schema 迁移: v%d → v%d", current, SCHEMA_VERSION)

        if current < 4:
            self._migrate_v3_to_v4()

        self._set_schema_version(SCHEMA_VERSION)
        logger.info("权限数据库 schema 迁移完成: v%d", SCHEMA_VERSION)

    def _migrate_v3_to_v4(self):
        """v3→v4 迁移：添加 role/operations 列，自动映射旧 access 数据。"""
        with sqlite3.connect(self.db_path) as conn:
            # 检查 role 列是否已存在（防止重复迁移）
            cursor = conn.execute("PRAGMA table_info(user_permissions)")
            columns = {row[1] for row in cursor.fetchall()}

            if "role" not in columns:
                conn.execute(
                    "ALTER TABLE user_permissions ADD COLUMN role TEXT DEFAULT 'viewer'"
                )
                logger.info("已添加 role 列")

            if "operations" not in columns:
                conn.execute(
                    "ALTER TABLE user_permissions ADD COLUMN operations TEXT DEFAULT '[]'"
                )
                logger.info("已添加 operations 列")

            # 自动映射旧数据：access="readonly"→role="viewer"，access="writeable"→role="operator"
            for old_access, new_role in _ACCESS_TO_ROLE_MAP.items():
                conn.execute(
                    "UPDATE user_permissions SET role = ? WHERE access = ? AND (role IS NULL OR role = 'viewer')",
                    (new_role, old_access),
                )

            # 初始化内置角色到 roles 表
            for role_name, role_info in BUILTIN_ROLES.items():
                conn.execute("""
                    INSERT OR IGNORE INTO roles (name, display_name, operations, is_builtin)
                    VALUES (?, ?, ?, 1)
                """, (
                    role_name,
                    role_info["label"],
                    json.dumps(role_info["operations"]),
                ))

            conn.commit()
        logger.info("v3→v4 迁移完成：旧 access 数据已映射到 role 字段")

    # ── CRUD ──────────────────────────────────────────────────────

    def set_permission(
        self, key: str, org_id: str, display_name: str = "",
        domains: list = None, access: str = "readonly",
        role: str = "", operations: list = None,
    ):
        """Set permission for a user+org combination.

        Args:
            key: User identifier ("channel:user_id")
            org_id: Organization ID ("01", "02", or "*" for wildcard)
            display_name: Display name
            domains: List of allowed business domains
            access: "readonly" or "writeable"（向后兼容）
            role: Role name (viewer/operator/manager/admin/custom)，空则从 access 推导
            operations: Custom operations list (仅 role="custom" 时生效)
        """
        # 向后兼容：如果没有显式指定 role，从 access 推导
        if not role:
            role = _ACCESS_TO_ROLE_MAP.get(access, "viewer")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_permissions
                (key, display_name, org_id, domains, access, role, operations, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                key, display_name, org_id,
                json.dumps(domains or []), access,
                role, json.dumps(operations or []),
            ))
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
                    "role": row["role"] if row["role"] else _ACCESS_TO_ROLE_MAP.get(row["access"], "viewer"),
                    "operations": json.loads(row["operations"]) if row["operations"] else [],
                }
        return None

    def list_user_orgs(self, key: str) -> List[Dict]:
        """List all org permissions for a user.

        Returns:
            List of {"org_id": "...", "domains": [...], "access": "...", "role": "...", "operations": [...]}
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT org_id, domains, access, role, operations FROM user_permissions WHERE key = ? ORDER BY org_id",
                (key,),
            ).fetchall()
            return [
                {
                    "org_id": r["org_id"],
                    "domains": json.loads(r["domains"]),
                    "access": r["access"],
                    "role": r["role"] if r["role"] else _ACCESS_TO_ROLE_MAP.get(r["access"], "viewer"),
                    "operations": json.loads(r["operations"]) if r["operations"] else [],
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
                    "role": r["role"] if r["role"] else _ACCESS_TO_ROLE_MAP.get(r["access"], "viewer"),
                    "operations": json.loads(r["operations"]) if r["operations"] else [],
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
                    "role": r["role"] if r["role"] else _ACCESS_TO_ROLE_MAP.get(r["access"], "viewer"),
                    "operations": json.loads(r["operations"]) if r["operations"] else [],
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

    # ── 角色权限管理 ────────────────────────────────────────────

    def update_permission_role(
        self, key: str, org_id: str,
        role: str, operations: list = None,
    ):
        """更新用户权限的角色和自定义操作列表。

        Args:
            key: User identifier ("channel:user_id")
            org_id: Organization ID
            role: New role name
            operations: Custom operations list (仅 role="custom" 时生效)
        """
        with sqlite3.connect(self.db_path) as conn:
            # 同步更新 access 字段以保持向后兼容
            access = "writeable" if role in ("admin", "manager") else "readonly"
            conn.execute("""
                UPDATE user_permissions
                SET role = ?, operations = ?, access = ?, updated_at = CURRENT_TIMESTAMP
                WHERE key = ? AND org_id = ?
            """, (role, json.dumps(operations or []), access, key, org_id))
            conn.commit()

    # ── 角色管理 ──────────────────────────────────────────────

    def list_roles(self) -> List[Dict]:
        """列出所有角色（内置 + 自定义）。"""
        roles = []
        # 内置角色
        for name, info in BUILTIN_ROLES.items():
            roles.append({
                "name": name,
                "label": info["label"],
                "operations": info["operations"],
                "builtin": True,
            })
        # 自定义角色（从 DB 加载）
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM roles WHERE is_builtin = 0 ORDER BY name"
            ).fetchall()
            for r in rows:
                roles.append({
                    "name": r["name"],
                    "label": r["display_name"],
                    "operations": json.loads(r["operations"]),
                    "builtin": False,
                })
        return roles

    def get_role(self, name: str) -> Optional[Dict]:
        """获取指定角色定义。"""
        # 先查内置角色
        if name in BUILTIN_ROLES:
            info = BUILTIN_ROLES[name]
            return {
                "name": name,
                "label": info["label"],
                "operations": info["operations"],
                "builtin": True,
            }
        # 再查自定义角色
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM roles WHERE name = ? AND is_builtin = 0",
                (name,),
            ).fetchone()
            if row:
                return {
                    "name": row["name"],
                    "label": row["display_name"],
                    "operations": json.loads(row["operations"]),
                    "builtin": False,
                }
        return None

    def set_role(self, name: str, label: str = "", operations: list = None):
        """创建或更新自定义角色。内置角色不可覆盖。"""
        if name in BUILTIN_ROLES:
            raise ValueError(f"内置角色 '{name}' 不可修改")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO roles (name, display_name, operations, is_builtin, updated_at)
                VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)
            """, (name, label or name, json.dumps(operations or [])))
            conn.commit()

    def delete_role(self, name: str):
        """删除自定义角色。内置角色不可删除。"""
        if name in BUILTIN_ROLES:
            raise ValueError(f"内置角色 '{name}' 不可删除")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM roles WHERE name = ? AND is_builtin = 0", (name,))
            conn.commit()

    def get_user_operations(
        self, key: str, org_id: str, domain: str = "",
    ) -> List[str]:
        """查询用户在指定上下文下允许的操作列表。

        Args:
            key: User identifier ("channel:user_id")
            org_id: Organization ID
            domain: Business domain filter (optional)

        Returns:
            List of allowed operation codes
        """
        perm = self.get_permission(key, org_id)
        if perm is None:
            perm = self.get_permission(key, "*")
        if perm is None:
            return []

        # 检查域访问权限
        if domain:
            allowed, _ = _check_domain_access(perm, "kingdee", domain)
            if not allowed:
                return []

        # 解析操作码
        operations = perm.get("operations", [])
        if not operations:
            # 回退到角色默认操作码
            role_name = perm.get("role", "viewer")
            role_def = self.get_role(role_name)
            if role_def:
                operations = role_def.get("operations", [])
        # "*" 表示全部操作
        if "*" in operations:
            return list(OPERATIONS.keys())
        return operations

    # ── 字段级权限管理（P2） ────────────────────────────────────────

    def set_field_permission(
        self, key: str, org_id: str, form_id: str,
        field_name: str, permission: str = "visible",
    ):
        """设置字段级权限。

        Args:
            key: 用户标识（"channel:user_id"）
            org_id: 组织ID（"*" 表示通配）
            form_id: 表单ID
            field_name: 字段名
            permission: 权限模式（visible/masked/readonly/hidden）
        """
        valid_modes = ("visible", "masked", "readonly", "hidden")
        if permission not in valid_modes:
            raise ValueError(f"无效的权限模式: {permission}，有效值: {', '.join(valid_modes)}")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO field_permissions
                (key, org_id, form_id, field_name, permission, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, org_id, form_id, field_name, permission))
            conn.commit()

    def get_field_permissions(self, key: str, org_id: str, form_id: str) -> Dict[str, str]:
        """获取用户+组织+表单的所有字段权限。

        Returns:
            {field_name: permission} 字典
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT field_name, permission FROM field_permissions "
                "WHERE key = ? AND org_id = ? AND form_id = ?",
                (key, org_id, form_id),
            ).fetchall()
            return {r["field_name"]: r["permission"] for r in rows}

    def remove_field_permission(
        self, key: str, org_id: str, form_id: str, field_name: str,
    ):
        """删除指定字段权限。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM field_permissions "
                "WHERE key = ? AND org_id = ? AND form_id = ? AND field_name = ?",
                (key, org_id, form_id, field_name),
            )
            conn.commit()

    def list_field_permissions(
        self, key: str = "", org_id: str = "", form_id: str = "",
    ) -> List[Dict]:
        """列出字段权限，支持可选过滤条件。

        Args:
            key: 用户标识过滤（空=不过滤）
            org_id: 组织ID过滤（空=不过滤）
            form_id: 表单ID过滤（空=不过滤）

        Returns:
            字段权限列表
        """
        query = "SELECT * FROM field_permissions WHERE 1=1"
        params: list = []
        if key:
            query += " AND key = ?"
            params.append(key)
        if org_id:
            query += " AND org_id = ?"
            params.append(org_id)
        if form_id:
            query += " AND form_id = ?"
            params.append(form_id)
        query += " ORDER BY key, org_id, form_id, field_name"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "key": r["key"],
                    "org_id": r["org_id"],
                    "form_id": r["form_id"],
                    "field_name": r["field_name"],
                    "permission": r["permission"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]

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

    # ── 行级过滤管理 ───────────────────────────────────────────

    def set_row_filter(self, key: str, org_id: str, form_id: str, filter_expr: str):
        """设置行级过滤规则。

        Args:
            key: 用户标识 ("channel:user_id")
            org_id: 组织ID ("01", "02", 或 "*" 表示通配)
            form_id: 表单ID (如 "SAL_SaleOrder")
            filter_expr: 金蝶 FilterString 表达式
                        (如 "FSaleOrgId.FNumber = '01'")
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO row_filters
                (key, org_id, form_id, filter_expr, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, org_id, form_id, filter_expr))
            conn.commit()

    def get_row_filter(self, key: str, org_id: str, form_id: str) -> Optional[str]:
        """获取指定用户+组织+表单的行级过滤表达式。

        Returns:
            filter_expr 字符串，未找到返回 None
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT filter_expr FROM row_filters WHERE key = ? AND org_id = ? AND form_id = ?",
                (key, org_id, form_id),
            ).fetchone()
            return row[0] if row else None

    def remove_row_filter(self, key: str, org_id: str, form_id: str):
        """删除指定的行级过滤规则。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM row_filters WHERE key = ? AND org_id = ? AND form_id = ?",
                (key, org_id, form_id),
            )
            conn.commit()

    def list_row_filters(
        self, key: str = "", org_id: str = "", form_id: str = "",
    ) -> List[Dict]:
        """列出行级过滤规则（支持可选过滤条件）。

        Args:
            key: 按用户标识过滤（可选）
            org_id: 按组织ID过滤（可选）
            form_id: 按表单ID过滤（可选）

        Returns:
            过滤规则列表，每项包含 key, org_id, form_id, filter_expr, updated_at
        """
        query = "SELECT * FROM row_filters WHERE 1=1"
        params: list = []
        if key:
            query += " AND key = ?"
            params.append(key)
        if org_id:
            query += " AND org_id = ?"
            params.append(org_id)
        if form_id:
            query += " AND form_id = ?"
            params.append(form_id)
        query += " ORDER BY key, org_id, form_id"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "key": r["key"],
                    "org_id": r["org_id"],
                    "form_id": r["form_id"],
                    "filter_expr": r["filter_expr"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]


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


# ── 操作码 & 角色工具函数 ─────────────────────────────────


def tool_to_operation(tool_name: str) -> Optional[str]:
    """将 MCP 工具名映射到操作码。

    Args:
        tool_name: MCP 工具名（如 "kingdee_save_bill"）

    Returns:
        操作码（如 "save"），未找到返回 None
    """
    return TOOL_OP_MAP.get(tool_name)


def resolve_role_operations(role: str, operations_json: str = "[]") -> List[str]:
    """解析角色对应的操作码列表。

    Args:
        role: 角色名（viewer/operator/manager/admin/custom）
        operations_json: 自定义操作码 JSON 字符串（仅 role="custom" 时使用）

    Returns:
        操作码列表；admin 返回全部操作码
    """
    if role == "admin":
        return list(OPERATIONS.keys())

    if role == "custom":
        try:
            # 兼容 JSON 字符串和已反序列化的列表
            if isinstance(operations_json, list):
                ops = operations_json
            else:
                ops = json.loads(operations_json) if operations_json else []
            # 过滤掉无效的操作码
            return [op for op in ops if op in OPERATIONS]
        except (json.JSONDecodeError, TypeError):
            return []

    # 内置角色：从 BUILTIN_ROLES 查找
    builtin = BUILTIN_ROLES.get(role)
    if builtin:
        return list(builtin["operations"])

    # 未知角色：回退到 viewer
    logger.warning("未知角色 '%s'，回退到 viewer", role)
    return list(BUILTIN_ROLES["viewer"]["operations"])


def get_user_operations(
    perm_mgr: PermissionManager, channel: str, user_id: str,
    system_name: str, form_id: str, org_id: str,
) -> List[str]:
    """获取用户在指定上下文下允许的所有操作码。

    先查找用户在该组织的权限记录，解析角色→操作码列表。
    如果 form_id 不在允许的业务域内，返回空列表。

    Args:
        perm_mgr: PermissionManager 实例
        channel: 用户渠道
        user_id: 用户标识
        system_name: ERP 系统名
        form_id: 表单 ID
        org_id: 组织 ID

    Returns:
        允许的操作码列表
    """
    key = f"{channel}:{user_id}"
    perm = perm_mgr.get_permission(key, org_id)
    if perm is None:
        perm = perm_mgr.get_permission(key, "*")
    if perm is None:
        return []

    # 业务域检查
    allowed, _ = _check_domain_access(perm, system_name, form_id)
    if not allowed:
        return []

    # 解析角色→操作码
    return resolve_role_operations(perm.get("role", "viewer"), perm.get("operations", "[]"))


def check_operation_permission(
    perm_mgr: PermissionManager, channel: str, user_id: str,
    system_name: str, form_id: str, org_id: str,
    operation: str,
) -> Tuple[bool, Optional[str]]:
    """检查用户是否有执行指定操作的权限。

    替代 check_write_permission 的核心新函数。
    检查流程：组织权限 → 业务域 → 角色→操作码。

    Args:
        perm_mgr: PermissionManager 实例
        channel: 用户渠道
        user_id: 用户标识
        system_name: ERP 系统名
        form_id: 表单 ID
        org_id: 组织 ID
        operation: 操作码（如 "save", "audit", "delete"）

    Returns:
        (allowed, error_message)
    """
    key = f"{channel}:{user_id}"

    # 1. 检查操作码是否有效
    if operation not in OPERATIONS:
        return False, f"未知的操作码: {operation}"

    # 2. 检查组织权限
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
            + _get_admin_contact(system_name)
        )

    # 3. 业务域检查
    if form_id:
        allowed, _ = _check_domain_access(perm, system_name, form_id)
        if not allowed:
            return False, (
                f"您没有在组织 {org_id} 操作 {form_id} 的权限。\n"
                f"您的业务域: {', '.join(perm['domains'])}"
                + _get_admin_contact(system_name)
            )

    # 4. 角色→操作码检查
    role = perm.get("role", "viewer")
    operations_json = perm.get("operations", "[]")
    allowed_ops = resolve_role_operations(role, operations_json)

    if operation not in allowed_ops:
        role_label = BUILTIN_ROLES.get(role, {}).get("label", role)
        op_label = OPERATIONS[operation]["label"]
        return False, (
            f"您的角色「{role_label}」没有「{op_label}」权限（组织: {org_id}）。\n"
            f"当前允许的操作: {', '.join(OPERATIONS[op]['label'] for op in allowed_ops if op in OPERATIONS)}"
            + _get_admin_contact(system_name)
        )

    return True, None


def add_role(
    perm_mgr: PermissionManager, name: str, display_name: str,
    operations: list, is_builtin: bool = False,
):
    """添加自定义角色到 roles 表。

    Args:
        perm_mgr: PermissionManager 实例
        name: 角色标识名
        display_name: 角色显示名
        operations: 操作码列表
        is_builtin: 是否内置角色
    """
    with sqlite3.connect(perm_mgr.db_path) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO roles (name, display_name, operations, is_builtin, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (name, display_name, json.dumps(operations), 1 if is_builtin else 0))
        conn.commit()
    logger.info("已添加角色: %s (%s), 操作: %s", name, display_name, operations)


def list_roles(perm_mgr: PermissionManager) -> List[Dict]:
    """列出所有角色定义。

    Returns:
        角色列表，每项包含 name, display_name, operations, is_builtin
    """
    with sqlite3.connect(perm_mgr.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM roles ORDER BY is_builtin DESC, name").fetchall()
        result = []
        for r in rows:
            result.append({
                "name": r["name"],
                "display_name": r["display_name"],
                "operations": json.loads(r["operations"]) if r["operations"] else [],
                "is_builtin": bool(r["is_builtin"]),
            })
        # 补充 BUILTIN_ROLES 中可能未入库的角色
        existing_names = {r["name"] for r in result}
        for role_name, role_info in BUILTIN_ROLES.items():
            if role_name not in existing_names:
                result.append({
                    "name": role_name,
                    "display_name": role_info["label"],
                    "operations": role_info["operations"],
                    "is_builtin": True,
                })
        return result


# ── 字段级权限工具函数 ─────────────────────────────────────


def get_field_permission_mode(
    perm_mgr: PermissionManager, key: str, org_id: str,
    form_id: str, field_name: str,
) -> str:
    """获取单个字段的权限模式。

    优先精确匹配，回退到通配 org_id="*" 的规则。
    未配置的字段默认返回 "visible"。

    Args:
        perm_mgr: PermissionManager 实例
        key: 用户标识（"channel:user_id"）
        org_id: 组织ID
        form_id: 表单ID
        field_name: 字段名

    Returns:
        权限模式: "visible", "masked", "readonly", "hidden"
    """
    # 1. 精确匹配
    perms = perm_mgr.get_field_permissions(key, org_id, form_id)
    if field_name in perms:
        return perms[field_name]

    # 2. 通配 org_id 回退
    if org_id != "*":
        perms_wildcard = perm_mgr.get_field_permissions(key, "*", form_id)
        if field_name in perms_wildcard:
            return perms_wildcard[field_name]

    # 3. 默认可见
    return "visible"


def filter_fields_by_permission(
    perm_mgr: PermissionManager, key: str, org_id: str,
    form_id: str, data: dict,
) -> dict:
    """根据字段级权限过滤查询结果。

    Args:
        perm_mgr: PermissionManager 实例
        key: 用户标识（"channel:user_id"）
        org_id: 组织ID
        form_id: 表单ID
        data: 查询结果字典 {field_name: value}

    Returns:
        过滤后的字典:
        - hidden 字段: 移除
        - masked 字段: 替换为 "***"
        - readonly 字段: 保留原值（由 UI 层控制不可编辑）
        - visible 字段: 保留原值
    """
    if not data or not isinstance(data, dict):
        return data

    # 批量获取该用户+组织+表单的所有字段权限
    perms = perm_mgr.get_field_permissions(key, org_id, form_id)
    # 回退到通配 org_id
    if org_id != "*" and perms:
        pass  # 有精确匹配就不需要回退
    elif org_id != "*":
        perms = perm_mgr.get_field_permissions(key, "*", form_id)

    if not perms:
        return data  # 无字段权限配置，原样返回

    result = {}
    for field_name, value in data.items():
        mode = perms.get(field_name, "visible")
        if mode == "hidden":
            continue  # 移除隐藏字段
        elif mode == "masked":
            result[field_name] = "***"
        else:
            # visible 或 readonly 都保留原值
            result[field_name] = value
    return result


# ── 原有权限检查函数 ───────────────────────────────────────


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

    .. deprecated::
        请使用 check_operation_permission() 替代，以获取基于角色的细粒度操作权限检查。
        本函数保留仅为向后兼容，内部已委托给 check_operation_permission(operation="save")。

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
    import warnings
    warnings.warn(
        "check_write_permission 已废弃，请使用 check_operation_permission() 替代",
        DeprecationWarning,
        stacklevel=2,
    )
    # 委托给新的操作级权限检查（save 代表通用写入操作）
    return check_operation_permission(
        perm_mgr, channel, user_id, system_name, form_id, org_id, "save",
    )


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


# ── 行级过滤解析 ───────────────────────────────────────────


def resolve_row_filter(
    perm_mgr: PermissionManager, key: str, org_id: str, form_id: str,
) -> str:
    """解析用户在指定上下文下的行级 FilterString。

    查找顺序：
    1. 精确匹配 (key, org_id, form_id)
    2. 通配符组织 (key, "*", form_id)

    Args:
        perm_mgr: PermissionManager 实例
        key: 用户标识 ("channel:user_id")
        org_id: 组织ID
        form_id: 表单ID

    Returns:
        FilterString 表达式；未配置时返回空字符串 ""
    """
    # 1. 精确匹配
    expr = perm_mgr.get_row_filter(key, org_id, form_id)
    if expr is not None:
        return expr

    # 2. 通配符组织回退
    expr = perm_mgr.get_row_filter(key, "*", form_id)
    if expr is not None:
        return expr

    return ""


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

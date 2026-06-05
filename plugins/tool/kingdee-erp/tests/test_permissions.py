# -*- coding: utf-8 -*-
"""Tests for role-based operation permission system.

覆盖：
1. TestConstants - 模块级常量验证
2. TestResolveRoleOperations - 角色→操作码解析
3. TestPermissionManager - CRUD + role/operations + 向后兼容
4. TestRoleManagement - 内置/自定义角色管理
5. TestCheckOperationPermission - 操作级权限检查
6. TestCheckWritePermissionBackwardCompat - check_write_permission 向后兼容
7. TestCheckQueryPermission - 查询权限（原有测试保留）
8. TestAuditLog - 审计日志（原有测试保留）
9. TestBackendRegistry - 后端注册表（原有测试保留）
10. TestCrossVendorIsolation - 跨厂商域隔离（原有测试保留 + 新增）
"""

import asyncio
import json
import os
import tempfile

import pytest

from erp_permissions import (
    PermissionManager,
    OPERATIONS,
    BUILTIN_ROLES,
    TOOL_OP_MAP,
    check_query_permission,
    check_write_permission,
    check_operation_permission,
    check_integration_permission,
    resolve_role_operations,
    get_user_operations,
    tool_to_operation,
    add_role,
    list_roles,
)
from erp_backend import BackendRegistry


# ── 共享辅助 ─────────────────────────────────────────────────


def _ensure_kingdee_backend():
    """确保 kingdee 后端已注册（用于域检查）。幂等，可重复调用。"""
    from erp_backend import get_registry
    try:
        from backends.kingdee.backend import KingdeeBackend
        reg = get_registry()
        if reg.get("kingdee") is None:
            reg.register(KingdeeBackend())
    except ImportError:
        pass  # 测试环境中后端不可用时跳过


# ═══════════════════════════════════════════════════════════════
# 1. TestConstants — 模块级常量验证
# ═══════════════════════════════════════════════════════════════


class TestConstants:
    """验证 OPERATIONS、BUILTIN_ROLES、TOOL_OP_MAP、tool_to_operation。"""

    def test_operations_count(self):
        """OPERATIONS 应包含 11 个操作码。"""
        assert len(OPERATIONS) == 11

    def test_operations_keys(self):
        expected = {
            "query", "view", "report", "save", "submit",
            "push", "execute", "workflow", "audit", "unaudit", "delete",
        }
        assert set(OPERATIONS.keys()) == expected

    def test_operations_have_required_fields(self):
        """每个操作码应有 label、tools、risk 字段。"""
        for op_code, op_info in OPERATIONS.items():
            assert "label" in op_info, f"{op_code} 缺少 label"
            assert "tools" in op_info, f"{op_code} 缺少 tools"
            assert "risk" in op_info, f"{op_code} 缺少 risk"
            assert isinstance(op_info["tools"], list)
            assert op_info["risk"] in ("low", "medium", "high")

    def test_builtin_roles_count(self):
        """BUILTIN_ROLES 应包含 5 个内置角色。"""
        assert len(BUILTIN_ROLES) == 5

    def test_builtin_roles_keys(self):
        expected = {"viewer", "operator", "manager", "admin", "custom"}
        assert set(BUILTIN_ROLES.keys()) == expected

    def test_builtin_roles_have_label_and_operations(self):
        for role_name, role_info in BUILTIN_ROLES.items():
            assert "label" in role_info, f"{role_name} 缺少 label"
            assert "operations" in role_info, f"{role_name} 缺少 operations"

    def test_tool_op_map_not_empty(self):
        assert len(TOOL_OP_MAP) > 0

    def test_tool_op_map_coverage(self):
        """TOOL_OP_MAP 中每个工具名都应映射到有效的操作码。"""
        for tool_name, op_code in TOOL_OP_MAP.items():
            assert op_code in OPERATIONS, (
                f"TOOL_OP_MAP[{tool_name!r}] = {op_code!r} 不在 OPERATIONS 中"
            )

    def test_tool_op_map_bidirectional(self):
        """OPERATIONS 中每个工具都应在 TOOL_OP_MAP 中有反向映射。"""
        for op_code, op_info in OPERATIONS.items():
            for tool_name in op_info["tools"]:
                assert tool_name in TOOL_OP_MAP, (
                    f"工具 {tool_name!r}（属于 {op_code}）未在 TOOL_OP_MAP 中"
                )
                assert TOOL_OP_MAP[tool_name] == op_code

    def test_tool_to_operation_known(self):
        assert tool_to_operation("kingdee_save_bill") == "save"
        assert tool_to_operation("kingdee_query_bill") == "query"
        assert tool_to_operation("kingdee_audit_bill") == "audit"
        assert tool_to_operation("kingdee_delete_bill") == "delete"
        assert tool_to_operation("kingdee_view_bill") == "view"
        assert tool_to_operation("kingdee_submit_bill") == "submit"

    def test_tool_to_operation_unknown(self):
        assert tool_to_operation("nonexistent_tool") is None
        assert tool_to_operation("") is None


# ═══════════════════════════════════════════════════════════════
# 2. TestResolveRoleOperations — 角色→操作码解析
# ═══════════════════════════════════════════════════════════════


class TestResolveRoleOperations:
    """验证 resolve_role_operations 函数的各种场景。"""

    def test_admin_returns_all(self):
        """admin 角色应返回全部操作码。"""
        ops = resolve_role_operations("admin")
        assert set(ops) == set(OPERATIONS.keys())

    def test_viewer_returns_low_risk(self):
        """viewer 角色应只包含查询类低风险操作。"""
        ops = resolve_role_operations("viewer")
        assert "query" in ops
        assert "view" in ops
        assert "report" in ops
        assert "save" not in ops
        assert "delete" not in ops
        assert "audit" not in ops

    def test_operator_includes_save_submit(self):
        """operator 角色应包含 save 和 submit，但不含 audit。"""
        ops = resolve_role_operations("operator")
        assert "save" in ops
        assert "submit" in ops
        assert "query" in ops
        assert "audit" not in ops
        assert "delete" not in ops

    def test_manager_includes_audit_push(self):
        """manager 角色应包含 audit 和 push，但不含 delete。"""
        ops = resolve_role_operations("manager")
        assert "audit" in ops
        assert "push" in ops
        assert "save" in ops
        assert "delete" not in ops
        assert "unaudit" not in ops

    def test_custom_with_operations(self):
        """custom 角色应精确返回指定的操作码。"""
        ops = resolve_role_operations("custom", '["query", "save"]')
        assert ops == ["query", "save"]

    def test_custom_filters_invalid(self):
        """custom 角色应过滤掉无效的操作码。"""
        ops = resolve_role_operations("custom", '["query", "nonexistent_op", "save"]')
        assert "nonexistent_op" not in ops
        assert ops == ["query", "save"]

    def test_custom_empty(self):
        ops = resolve_role_operations("custom", "[]")
        assert ops == []

    def test_custom_none(self):
        ops = resolve_role_operations("custom", None)
        assert ops == []

    def test_custom_invalid_json(self):
        ops = resolve_role_operations("custom", "not-valid-json")
        assert ops == []

    def test_unknown_falls_back_to_viewer(self):
        """未知角色应回退到 viewer。"""
        ops = resolve_role_operations("unknown_role")
        assert ops == list(BUILTIN_ROLES["viewer"]["operations"])


# ═══════════════════════════════════════════════════════════════
# 3. TestPermissionManager — CRUD + role/operations + 向后兼容
# ═══════════════════════════════════════════════════════════════


class TestPermissionManager:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    # ── 基础 CRUD ──

    def test_set_and_get(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["finance"], "readonly")
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm is not None
        assert perm["key"] == "wecom:user1"
        assert perm["org_id"] == "01"
        assert perm["display_name"] == "张三"
        assert perm["domains"] == ["finance"]
        assert perm["access"] == "readonly"

    def test_get_missing(self):
        assert self.pm.get_permission("wecom:user1", "01") is None

    def test_multi_org(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["finance"], "readonly")
        self.pm.set_permission("wecom:user1", "02", "张三", ["sales"], "writeable")

        orgs = self.pm.list_user_orgs("wecom:user1")
        assert len(orgs) == 2
        assert orgs[0]["org_id"] == "01"
        assert orgs[1]["org_id"] == "02"
        assert orgs[0]["domains"] == ["finance"]
        assert orgs[1]["domains"] == ["sales"]

    def test_remove_single_org(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["finance"], "readonly")
        self.pm.set_permission("wecom:user1", "02", "张三", ["sales"], "writeable")
        self.pm.remove_permission("wecom:user1", "01")

        assert self.pm.get_permission("wecom:user1", "01") is None
        assert self.pm.get_permission("wecom:user1", "02") is not None

    def test_remove_user(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["finance"], "readonly")
        self.pm.set_permission("wecom:user1", "02", "张三", ["sales"], "writeable")
        self.pm.remove_user("wecom:user1")

        assert self.pm.list_user_orgs("wecom:user1") == []

    def test_list_permissions(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["finance"], "readonly")
        self.pm.set_permission("wecom:user2", "02", "李四", ["sales"], "writeable")
        perms = self.pm.list_permissions()
        assert len(perms) == 2

    def test_wildcard_org(self):
        self.pm.set_permission("wecom:user1", "*", "张三", ["finance"], "readonly")
        perm = self.pm.get_permission("wecom:user1", "*")
        assert perm is not None
        assert perm["org_id"] == "*"

    # ── role / operations 字段 ──

    def test_set_permission_with_role(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="operator")
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm["role"] == "operator"
        assert perm["operations"] == []

    def test_set_permission_with_custom_operations(self):
        self.pm.set_permission(
            "wecom:user1", "01", "张三", ["sales"],
            role="custom", operations=["query", "save"],
        )
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm["role"] == "custom"
        assert perm["operations"] == ["query", "save"]

    def test_list_user_orgs_includes_role(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="operator")
        orgs = self.pm.list_user_orgs("wecom:user1")
        assert len(orgs) == 1
        assert orgs[0]["role"] == "operator"

    def test_list_user_permissions_includes_role(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="manager")
        perms = self.pm.list_user_permissions("wecom:user1")
        assert len(perms) == 1
        assert perms[0]["role"] == "manager"

    # ── 向后兼容：access → role 映射 ──

    def test_backward_compat_readonly_to_viewer(self):
        """未指定 role 时，access="readonly" 应映射为 role="viewer"。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], access="readonly")
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm["role"] == "viewer"

    def test_backward_compat_writeable_to_admin(self):
        """未指定 role 时，access="writeable" 应映射为 role="admin"。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], access="writeable")
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm["role"] == "admin"

    # ── update_permission_role ──

    def test_update_permission_role(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        self.pm.update_permission_role("wecom:user1", "01", "manager")
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm["role"] == "manager"
        # manager → access 同步为 "writeable"
        assert perm["access"] == "writeable"

    def test_update_permission_role_custom(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        self.pm.update_permission_role(
            "wecom:user1", "01", "custom", operations=["query", "audit"],
        )
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm["role"] == "custom"
        assert perm["operations"] == ["query", "audit"]
        # custom → access 同步为 "readonly"
        assert perm["access"] == "readonly"

    def test_update_permission_role_to_admin(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        self.pm.update_permission_role("wecom:user1", "01", "admin")
        perm = self.pm.get_permission("wecom:user1", "01")
        assert perm["role"] == "admin"
        assert perm["access"] == "writeable"


# ═══════════════════════════════════════════════════════════════
# 4. TestRoleManagement — 内置/自定义角色管理
# ═══════════════════════════════════════════════════════════════


class TestRoleManagement:
    """角色管理：内置角色查询、自定义角色 CRUD、add_role 独立函数。"""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    def test_list_builtin_roles(self):
        roles = self.pm.list_roles()
        builtin_names = [r["name"] for r in roles if r["builtin"]]
        assert "viewer" in builtin_names
        assert "operator" in builtin_names
        assert "manager" in builtin_names
        assert "admin" in builtin_names
        assert "custom" in builtin_names
        assert len(builtin_names) == 5

    def test_get_role_builtin(self):
        role = self.pm.get_role("viewer")
        assert role is not None
        assert role["name"] == "viewer"
        assert role["builtin"] is True
        assert "query" in role["operations"]

    def test_get_role_missing(self):
        assert self.pm.get_role("nonexistent") is None

    def test_create_custom_role(self):
        self.pm.set_role("auditor", label="审计员", operations=["query", "view", "audit"])
        role = self.pm.get_role("auditor")
        assert role is not None
        assert role["name"] == "auditor"
        assert role["label"] == "审计员"
        assert role["operations"] == ["query", "view", "audit"]
        assert role["builtin"] is False

    def test_update_custom_role(self):
        self.pm.set_role("auditor", label="审计员", operations=["query"])
        self.pm.set_role("auditor", label="高级审计员", operations=["query", "audit"])
        role = self.pm.get_role("auditor")
        assert role["label"] == "高级审计员"
        assert role["operations"] == ["query", "audit"]

    def test_delete_custom_role(self):
        self.pm.set_role("temp_role", label="临时角色", operations=["query"])
        assert self.pm.get_role("temp_role") is not None
        self.pm.delete_role("temp_role")
        assert self.pm.get_role("temp_role") is None

    def test_cannot_modify_builtin_role(self):
        with pytest.raises(ValueError, match="内置角色"):
            self.pm.set_role("admin", label="修改管理员", operations=["query"])

    def test_cannot_modify_builtin_role_viewer(self):
        with pytest.raises(ValueError, match="内置角色"):
            self.pm.set_role("viewer", label="修改查看者", operations=[])

    def test_cannot_delete_builtin_role(self):
        with pytest.raises(ValueError, match="内置角色"):
            self.pm.delete_role("admin")

    def test_cannot_delete_builtin_role_viewer(self):
        with pytest.raises(ValueError, match="内置角色"):
            self.pm.delete_role("viewer")

    def test_list_roles_includes_custom(self):
        self.pm.set_role("custom1", label="自定义1", operations=["query"])
        roles = list_roles(self.pm)
        custom_roles = [r for r in roles if r["name"] == "custom1"]
        assert len(custom_roles) == 1
        assert custom_roles[0]["display_name"] == "自定义1"
        assert custom_roles[0]["is_builtin"] is False

    def test_add_role_standalone_function(self):
        """add_role 独立函数应能添加自定义角色。"""
        add_role(self.pm, "reporter", "报表员", ["query", "report"])
        roles = list_roles(self.pm)
        reporter = [r for r in roles if r["name"] == "reporter"]
        assert len(reporter) == 1
        assert reporter[0]["display_name"] == "报表员"
        assert reporter[0]["operations"] == ["query", "report"]
        assert reporter[0]["is_builtin"] is False

    def test_add_role_builtin_flag(self):
        """add_role 的 is_builtin 参数应正确设置。"""
        add_role(self.pm, "sys_admin", "系统管理员", ["*"], is_builtin=True)
        roles = list_roles(self.pm)
        sys_admin = [r for r in roles if r["name"] == "sys_admin"]
        assert len(sys_admin) == 1
        assert sys_admin[0]["is_builtin"] is True


# ═══════════════════════════════════════════════════════════════
# 5. TestCheckOperationPermission — 操作级权限检查
# ═══════════════════════════════════════════════════════════════


class TestCheckOperationPermission:
    """check_operation_permission 核心测试。"""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)
        _ensure_kingdee_backend()

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    # ── 前置条件检查 ──

    def test_no_permission(self):
        """未配置权限时应返回错误（org_id 已指定 → 提示无该组织权限）。"""
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "query",
        )
        assert ok is False
        assert "01" in err

    def test_no_permission_no_org(self):
        """未配置权限且未指定组织 → 提示尚未配置。"""
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "", "query",
        )
        assert ok is False
        assert "尚未配置" in err

    def test_no_org(self):
        """未指定组织时应返回 请先指定。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "", "query",
        )
        assert ok is False
        assert "请先指定" in err

    def test_wrong_org(self):
        """无权限的组织应被拒绝。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "02", "query",
        )
        assert ok is False
        assert "02" in err

    # ── 各角色权限边界 ──

    def test_viewer_can_query(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "query",
        )
        assert ok is True

    def test_viewer_can_view(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "view",
        )
        assert ok is True

    def test_viewer_can_report(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "report",
        )
        assert ok is True

    def test_viewer_cannot_save(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "save",
        )
        assert ok is False
        assert "查看者" in err

    def test_viewer_cannot_delete(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "delete",
        )
        assert ok is False

    def test_operator_can_save(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="operator")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "save",
        )
        assert ok is True

    def test_operator_can_submit(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="operator")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "submit",
        )
        assert ok is True

    def test_operator_cannot_audit(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="operator")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "audit",
        )
        assert ok is False
        assert "操作员" in err

    def test_operator_cannot_delete(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="operator")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "delete",
        )
        assert ok is False

    def test_manager_can_audit(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="manager")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "audit",
        )
        assert ok is True

    def test_manager_can_push(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="manager")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "push",
        )
        assert ok is True

    def test_manager_cannot_delete(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="manager")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "delete",
        )
        assert ok is False
        assert "管理者" in err

    def test_manager_cannot_unaudit(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="manager")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "unaudit",
        )
        assert ok is False

    def test_admin_can_all(self):
        """admin 角色应有权执行所有操作。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")
        for op_code in OPERATIONS:
            ok, err = check_operation_permission(
                self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", op_code,
            )
            assert ok is True, f"admin 应有权执行 {op_code}，但被拒绝: {err}"

    # ── 自定义角色 ──

    def test_custom_role_with_specific_ops(self):
        """自定义角色应精确控制允许的操作。"""
        self.pm.set_permission(
            "wecom:user1", "01", "张三", ["sales"],
            role="custom", operations=["query", "save"],
        )
        # 允许的操作
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "query",
        )
        assert ok is True
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "save",
        )
        assert ok is True
        # 未授权的操作
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "audit",
        )
        assert ok is False
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "delete",
        )
        assert ok is False

    # ── 通配符组织 ──

    def test_wildcard_org(self):
        """通配符组织 "*" 应匹配任意组织。"""
        self.pm.set_permission("wecom:user1", "*", "张三", ["sales"], role="viewer")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "query",
        )
        assert ok is True

    def test_wildcard_org_different_org(self):
        self.pm.set_permission("wecom:user1", "*", "张三", ["sales"], role="admin")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "99", "save",
        )
        assert ok is True

    # ── 业务域检查 ──

    def test_domain_blocked(self):
        """不在允许域内的表单应被拒绝。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01", "query",
        )
        assert ok is False
        assert "GL_Voucher" in err

    def test_domain_allowed(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "query",
        )
        assert ok is True

    def test_base_data_always_allowed(self):
        """基础数据（BD_ 前缀）应始终允许访问。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "BD_Material", "01", "query",
        )
        assert ok is True

    # ── 无效操作码 ──

    def test_invalid_operation_code(self):
        """无效操作码应返回 未知 错误。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "nonexistent",
        )
        assert ok is False
        assert "未知" in err

    def test_empty_operation_code(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01", "",
        )
        assert ok is False
        assert "未知" in err

    # ── get_user_operations ──

    def test_get_user_operations_admin(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")
        ops = get_user_operations(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01",
        )
        assert set(ops) == set(OPERATIONS.keys())

    def test_get_user_operations_viewer(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        ops = get_user_operations(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01",
        )
        assert "query" in ops
        assert "save" not in ops

    def test_get_user_operations_domain_blocked(self):
        """域不匹配时应返回空列表。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")
        ops = get_user_operations(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01",
        )
        assert ops == []

    def test_get_user_operations_no_permission(self):
        ops = get_user_operations(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01",
        )
        assert ops == []

    def test_get_user_operations_custom_role(self):
        self.pm.set_permission(
            "wecom:user1", "01", "张三", ["sales"],
            role="custom", operations=["query", "audit"],
        )
        ops = get_user_operations(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01",
        )
        assert ops == ["query", "audit"]


# ═══════════════════════════════════════════════════════════════
# 6. TestCheckWritePermissionBackwardCompat — 向后兼容
# ═══════════════════════════════════════════════════════════════


class TestCheckWritePermissionBackwardCompat:
    """check_write_permission 已废弃，委托给 check_operation_permission(operation="save")。"""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)
        _ensure_kingdee_backend()

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    def test_readonly_blocked(self):
        """readonly → viewer 角色 → 无 save 权限 → 被拒绝。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], access="readonly")
        with pytest.warns(DeprecationWarning):
            ok, err = check_write_permission(
                self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01",
            )
        assert ok is False
        assert "查看者" in err

    def test_writeable_allowed(self):
        """writeable → admin 角色 → 有 save 权限 → 允许。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], access="writeable")
        with pytest.warns(DeprecationWarning):
            ok, err = check_write_permission(
                self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01",
            )
        assert ok is True

    def test_writeable_domain_blocked(self):
        """writeable 但域不匹配 → 被拒绝。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], access="writeable")
        with pytest.warns(DeprecationWarning):
            ok, err = check_write_permission(
                self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01",
            )
        assert ok is False
        assert "GL_Voucher" in err

    def test_no_permission(self):
        """未配置权限 → 被拒绝。"""
        with pytest.warns(DeprecationWarning):
            ok, err = check_write_permission(
                self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01",
            )
        assert ok is False

    def test_no_org_specified(self):
        """未指定组织 → 返回错误提示。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], access="writeable")
        with pytest.warns(DeprecationWarning):
            ok, err = check_write_permission(
                self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "",
            )
        assert ok is False
        assert "请先指定" in err


# ═══════════════════════════════════════════════════════════════
# 7. TestCheckQueryPermission — 查询权限（原有测试保留）
# ═══════════════════════════════════════════════════════════════


class TestCheckQueryPermission:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    def test_no_permission_configured(self):
        ok, err, org_filter = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01"
        )
        assert ok is False
        assert "尚未配置" in err

    def test_no_org_specified(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "readonly")
        ok, err, _ = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", ""
        )
        assert ok is False
        assert "请先指定" in err

    def test_wrong_org(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "readonly")
        ok, err, _ = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "02"
        )
        assert ok is False
        assert "02" in err

    def test_readonly_allowed(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "readonly")
        ok, err, org_filter = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01"
        )
        assert ok is True
        assert org_filter is None

    def test_domain_blocked(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "readonly")
        ok, err, _ = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01"
        )
        assert ok is False

    def test_base_data_always_allowed(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "readonly")
        ok, _, _ = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "BD_Material", "01"
        )
        assert ok is True

    def test_wildcard_org(self):
        self.pm.set_permission("wecom:user1", "*", "张三", ["sales"], "readonly")
        ok, _, org_filter = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01"
        )
        assert ok is True
        assert org_filter is None


# ═══════════════════════════════════════════════════════════════
# 8. TestAuditLog — 审计日志（原有测试保留）
# ═══════════════════════════════════════════════════════════════


class TestAuditLog:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    def test_log_and_query(self):
        asyncio.run(self.pm.log_operation("wecom:user1", "save", "SAL_SaleOrder", "BILL001"))
        asyncio.run(self.pm.log_operation("wecom:user1", "delete", "SAL_SaleOrder", "BILL002"))
        asyncio.run(self.pm.log_operation("dingtalk:user2", "audit", "GL_Voucher", "V001"))

        logs = self.pm.list_audit_log()
        assert len(logs) == 3
        assert logs[0]["action"] == "audit"

    def test_query_filter_operator(self):
        asyncio.run(self.pm.log_operation("wecom:user1", "save", "SAL_SaleOrder"))
        asyncio.run(self.pm.log_operation("dingtalk:user2", "audit", "GL_Voucher"))

        logs = self.pm.list_audit_log(operator="wecom:user1")
        assert len(logs) == 1

    def test_query_filter_action(self):
        asyncio.run(self.pm.log_operation("wecom:user1", "save", "SAL_SaleOrder"))
        asyncio.run(self.pm.log_operation("wecom:user1", "delete", "SAL_SaleOrder"))

        logs = self.pm.list_audit_log(action="save")
        assert len(logs) == 1

    def test_query_filter_form_id(self):
        asyncio.run(self.pm.log_operation("wecom:user1", "save", "SAL_SaleOrder"))
        asyncio.run(self.pm.log_operation("wecom:user1", "save", "GL_Voucher"))

        logs = self.pm.list_audit_log(form_id="GL_Voucher")
        assert len(logs) == 1

    def test_query_limit(self):
        for i in range(10):
            asyncio.run(self.pm.log_operation("wecom:user1", "save", "SAL_SaleOrder", f"B{i}"))

        logs = self.pm.list_audit_log(limit=5)
        assert len(logs) == 5

    def test_cleanup_exports_and_deletes(self, tmp_path):
        import erp_permissions
        original_max = erp_permissions.AUDIT_LOG_MAX
        original_batch = erp_permissions.AUDIT_LOG_EXPORT_BATCH
        original_archive = erp_permissions.DEFAULT_ARCHIVE_DIR
        try:
            erp_permissions.AUDIT_LOG_MAX = 5
            erp_permissions.AUDIT_LOG_EXPORT_BATCH = 3
            erp_permissions.DEFAULT_ARCHIVE_DIR = str(tmp_path / "archive")

            pm = PermissionManager(db_path=str(tmp_path / "test.db"))
            for i in range(7):
                asyncio.run(pm.log_operation(f"user{i}", "save", "SAL_SaleOrder", f"B{i}"))

            logs = pm.list_audit_log(limit=100)
            assert len(logs) == 4

            archive_dir = tmp_path / "archive"
            assert archive_dir.exists()
            archive_files = list(archive_dir.iterdir())
            assert len(archive_files) == 1
        finally:
            erp_permissions.AUDIT_LOG_MAX = original_max
            erp_permissions.AUDIT_LOG_EXPORT_BATCH = original_batch
            erp_permissions.DEFAULT_ARCHIVE_DIR = original_archive


# ═══════════════════════════════════════════════════════════════
# 9. TestBackendRegistry — 后端注册表（原有测试保留）
# ═══════════════════════════════════════════════════════════════


class TestBackendRegistry:
    def test_register_and_get(self):
        reg = BackendRegistry()
        from backends.kingdee.backend import KingdeeBackend
        kb = KingdeeBackend()
        reg.register(kb)
        assert reg.get("kingdee") is kb
        assert "kingdee" in reg.list_all()

    def test_register_duplicate(self):
        reg = BackendRegistry()
        from backends.kingdee.backend import KingdeeBackend
        reg.register(KingdeeBackend())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(KingdeeBackend())

    def test_get_missing(self):
        reg = BackendRegistry()
        assert reg.get("nonexistent") is None

    def test_get_all_domains(self):
        reg = BackendRegistry()
        from backends.kingdee.backend import KingdeeBackend
        reg.register(KingdeeBackend())
        domains = reg.get_all_domains()
        assert "kingdee:finance" in domains
        assert "finance" in domains


# ═══════════════════════════════════════════════════════════════
# 10. TestCrossVendorIsolation — 跨厂商域隔离
# ═══════════════════════════════════════════════════════════════


class TestCrossVendorIsolation:
    """跨厂商域隔离测试：确保 "sap:finance" 权限无法访问 kingdee 工具。"""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)
        # 确保 kingdee 后端已注册，否则 domain_form_map 为空会导致测试非预期通过
        _ensure_kingdee_backend()

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    # ── 原有测试保留 ──

    def test_cross_vendor_query_blocked(self):
        """sap:finance 权限不应允许查询 kingdee 的财务单据。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sap:finance"], "readonly")
        ok, err, _ = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01"
        )
        assert ok is False

    def test_cross_vendor_write_blocked(self):
        """sap:finance 权限不应允许写入 kingdee 的财务单据。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sap:finance"], "writeable")
        with pytest.warns(DeprecationWarning):
            ok, err = check_write_permission(
                self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01"
            )
        assert ok is False

    def test_same_vendor_prefixed_allowed(self):
        """kingdee:finance 权限应允许访问 kingdee 工具。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["kingdee:finance"], "readonly")
        ok, _, _ = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01"
        )
        assert ok is True

    def test_pure_domain_backward_compat(self):
        """纯域名 "finance" 应继续向后兼容（任何系统都可匹配）。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["finance"], "readonly")
        ok, _, _ = check_query_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01"
        )
        assert ok is True

    def test_cross_vendor_integration_blocked(self):
        """sap:finance 权限不应被计入 kingdee 的整合操作允许系统。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sap:finance"], "readonly")
        ok, err, allowed_systems = check_integration_permission(
            self.pm, "wecom", "user1", ["kingdee"], action="read"
        )
        assert ok is False
        assert "kingdee" not in allowed_systems

    def test_same_vendor_integration_allowed(self):
        """kingdee:finance 权限应被计入 kingdee 的整合操作允许系统。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["kingdee:finance"], "readonly")
        ok, _, allowed_systems = check_integration_permission(
            self.pm, "wecom", "user1", ["kingdee"], action="read"
        )
        assert ok is True
        assert "kingdee" in allowed_systems

    # ── 新增：使用 check_operation_permission 的跨厂商测试 ──

    def test_cross_vendor_operation_permission_blocked(self):
        """sap:finance 权限不应允许执行 kingdee 的操作。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sap:finance"], role="admin")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01", "save",
        )
        assert ok is False

    def test_cross_vendor_operation_audit_blocked(self):
        """sap:finance 权限不应允许审核 kingdee 单据。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["sap:finance"], role="admin")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01", "audit",
        )
        assert ok is False

    def test_same_vendor_operation_permission_allowed(self):
        """kingdee:finance 权限应允许执行 kingdee 的操作。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["kingdee:finance"], role="admin")
        ok, err = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01", "save",
        )
        assert ok is True

    def test_pure_domain_operation_permission_allowed(self):
        """纯域名 "finance" 应向后兼容，允许 kingdee 操作。"""
        self.pm.set_permission("wecom:user1", "01", "张三", ["finance"], role="operator")
        ok, _ = check_operation_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01", "save",
        )
        assert ok is True

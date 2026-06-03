# -*- coding: utf-8 -*-
"""Tests for per-org permission management."""

import asyncio
import json
import os
import tempfile

import pytest

from erp_permissions import (
    PermissionManager,
    check_query_permission,
    check_write_permission,
    check_integration_permission,
)
from erp_backend import BackendRegistry


class TestPermissionManager:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

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


class TestCheckWritePermission:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    def test_no_permission(self):
        ok, err = check_write_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01"
        )
        assert ok is False

    def test_readonly_blocked(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "readonly")
        ok, err = check_write_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01"
        )
        assert ok is False
        assert "只读" in err

    def test_writeable_allowed(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "writeable")
        ok, err = check_write_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01"
        )
        assert ok is True

    def test_writeable_domain_allowed(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "writeable")
        ok, err = check_write_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", "01"
        )
        assert ok is True

    def test_writeable_domain_blocked(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "writeable")
        ok, err = check_write_permission(
            self.pm, "wecom", "user1", "kingdee", "GL_Voucher", "01"
        )
        assert ok is False
        assert "GL_Voucher" in err

    def test_no_org_specified(self):
        self.pm.set_permission("wecom:user1", "01", "张三", ["sales"], "writeable")
        ok, err = check_write_permission(
            self.pm, "wecom", "user1", "kingdee", "SAL_SaleOrder", ""
        )
        assert ok is False
        assert "请先指定" in err


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


class TestCrossVendorIsolation:
    """跨厂商域隔离测试：确保 "sap:finance" 权限无法访问 kingdee 工具。"""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.pm = PermissionManager(db_path=self.tmp)
        # 确保 kingdee 后端已注册，否则 domain_form_map 为空会导致测试非预期通过
        from erp_backend import get_registry
        from backends.kingdee.backend import KingdeeBackend
        reg = get_registry()
        if reg.get("kingdee") is None:
            reg.register(KingdeeBackend())

    def teardown_method(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

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

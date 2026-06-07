# -*- coding: utf-8 -*-
"""Integration tests for frontend REST API routing and cross-system glue tools."""

import asyncio
import json
import os
import tempfile
import sys
from unittest.mock import MagicMock, patch

# Mock agentscope prior to any other imports that might depend on it
mock_agentscope = MagicMock()
mock_agentscope.message = MagicMock()
# TextBlock and ToolResponse are used as classes
class DummyTextBlock:
    def __init__(self, text=None, **kwargs):
        self.text = text

class DummyToolResponse:
    def __init__(self, content=None, *args, **kwargs):
        self.content = content
        self.blocks = content

mock_agentscope.message.TextBlock = DummyTextBlock
mock_agentscope.tool = MagicMock()
mock_agentscope.tool.ToolResponse = DummyToolResponse

sys.modules["agentscope"] = mock_agentscope
sys.modules["agentscope.message"] = mock_agentscope.message
sys.modules["agentscope.tool"] = mock_agentscope.tool

# Mock qwenpaw plugins prior to importing any tools
mock_qwenpaw = MagicMock()
mock_qwenpaw.plugins = MagicMock()
sys.modules["qwenpaw"] = mock_qwenpaw
sys.modules["qwenpaw.plugins"] = mock_qwenpaw.plugins

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from erp_backend import BackendRegistry, get_registry
from erp_permissions import PermissionManager
from backends.kingdee.backend import KingdeeBackend
from integration.tools import erp_unified_query, erp_compare_data


class MockPluginApi:
    """Mock QwenPaw PluginApi to capture router registration and run TestClient."""
    def __init__(self):
        self.app = FastAPI()

    def register_http_router(self, router, prefix="", tags=None):
        self.app.include_router(router, prefix=prefix, tags=tags)

    def register_tool(self, tool_name, tool_func, description, icon):
        pass


class TestFrontendBackendIntegration:
    def setup_method(self):
        self.tmp_db = tempfile.mktemp(suffix=".db")
        # 用我们的临时 DB 初始化 PermissionManager
        self.pm = PermissionManager(db_path=self.tmp_db)
        
        # 创建 Mock API 和 Backend，注册路由
        self.api = MockPluginApi()
        self.backend = KingdeeBackend()
        
        # 使用 patch 保证后端路由初始化时使用的是我们的测试 DB 实例
        with patch("backends.kingdee.backend.PermissionManager", return_value=self.pm), \
             patch("erp_permissions.PermissionManager", return_value=self.pm):
            self.backend.register_routes(self.api)
            
        self.client = TestClient(self.api.app)

    def teardown_method(self):
        if os.path.exists(self.tmp_db):
            os.unlink(self.tmp_db)

    def test_list_field_mappings_empty(self):
        """测试获取自定义字段映射（当数据库为空时只加载元数据表单）"""
        response = self.client.get("/erp-permissions/field-mappings?domain=sales")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        # 我们之前在 domain_tables.json 查出了 139 个销售域表单，这里应该包含它们
        items = data["items"]
        assert len(items) > 0
        # 验证每个元素包含的字段与前端 TS 契约一致
        for item in items:
            assert "form_id" in item
            assert "form_name" in item
            assert "fields" in item
            assert "source" in item
            if item["form_id"] == "SAL_SaleOrder":
                assert item["source"] == "metadata"

    def test_save_and_get_custom_field_mapping(self):
        """测试保存自定义字段映射及去重覆盖逻辑"""
        # 1. 验证保存自定义映射接口
        body = {
            "form_id": "SAL_SaleOrder",
            "form_name": "销售订单(自定义)",
            "fields": [{"field_key": "FBillNo", "display_name": "我的单据编号", "field_type": "文本"}]
        }
        put_resp = self.client.put("/erp-permissions/field-mappings", json=body)
        assert put_resp.status_code == 200
        assert put_resp.json() == {"status": "ok", "form_id": "SAL_SaleOrder"}

        # 2. 验证获取接口中自定义映射覆盖元数据的效果
        get_resp = self.client.get("/erp-permissions/field-mappings?domain=sales")
        assert get_resp.status_code == 200
        items = get_resp.json()["items"]
        
        # 查找 SAL_SaleOrder 表单，它应该已经被我们的自定义映射覆盖，且 source 应该改变
        custom_orders = [i for i in items if i["form_id"] == "SAL_SaleOrder"]
        assert len(custom_orders) == 1
        custom_order = custom_orders[0]
        assert custom_order["form_name"] == "销售订单(自定义)"
        assert len(custom_order["fields"]) == 1
        assert custom_order["fields"][0]["display_name"] == "我的单据编号"
        assert custom_order.get("source") != "metadata"  # 自定义保存的不再带 metadata 标记

        # 3. 验证删除接口
        del_resp = self.client.delete("/erp-permissions/field-mappings/SAL_SaleOrder")
        assert del_resp.status_code == 200
        assert del_resp.json() == {"status": "ok", "form_id": "SAL_SaleOrder"}

        # 删除后应当重新 fallback 回元数据表单
        get_resp_after = self.client.get("/erp-permissions/field-mappings?domain=sales")
        items_after = get_resp_after.json()["items"]
        fallback_order = [i for i in items_after if i["form_id"] == "SAL_SaleOrder"][0]
        assert fallback_order["form_name"] == "销售订单"
        assert fallback_order["source"] == "metadata"

    def test_permission_crud_endpoints(self):
        """测试权限配置管理的完整 CRUD API 契约"""
        # 1. 验证空列表状态
        list_resp = self.client.get("/erp-permissions/")
        assert list_resp.status_code == 200
        assert list_resp.json()["items"] == []

        # 2. 注入一个新权限 (POST)
        body = {
            "key": "wecom:user_test",
            "org_id": "01",
            "display_name": "测试员",
            "domains": ["sales", "finance"],
            "access": "writeable"
        }
        post_resp = self.client.post("/erp-permissions/", json=body)
        assert post_resp.status_code == 200
        assert post_resp.json()["status"] == "ok"

        # 3. 再次列表查询验证，包含 mock 获取组织名称逻辑
        with patch.object(self.backend, "get_client") as mock_client_factory:
            mock_client = MagicMock()
            # 模拟 get_org_names 异步返回组织字典
            future = asyncio.Future()
            future.set_result({"01": "测试第一分公司"})
            mock_client.get_org_names.return_value = future
            mock_client_factory.return_value = mock_client

            list_resp_2 = self.client.get("/erp-permissions/")
            assert list_resp_2.status_code == 200
            items = list_resp_2.json()["items"]
            assert len(items) == 1
            assert items[0]["key"] == "wecom:user_test"
            assert items[0]["org_id"] == "01"
            assert items[0]["org_name"] == "测试第一分公司"
            assert items[0]["access"] == "writeable"
            assert items[0]["domains"] == ["sales", "finance"]

        # 4. 删除此权限
        del_resp = self.client.delete("/erp-permissions/wecom:user_test/01")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "ok"

        # 验证已删除
        list_resp_3 = self.client.get("/erp-permissions/")
        assert len(list_resp_3.json()["items"]) == 0

    def test_get_audit_log_endpoint(self):
        """测试审计日志查询接口"""
        # 预先向 DB 写入两条操作日志
        asyncio.run(self.pm.log_operation("wecom:admin", "save", "SAL_SaleOrder", "SO-001", "新建销售单"))
        asyncio.run(self.pm.log_operation("wecom:admin", "delete", "SAL_SaleOrder", "SO-001", "删除销售单"))

        # 查询接口验证
        response = self.client.get("/erp-permissions/audit-log?limit=10")
        assert response.status_code == 200
        logs = response.json()
        assert len(logs) == 2
        assert logs[0]["operator"] == "wecom:admin"
        assert logs[0]["action"] == "delete"
        assert logs[1]["action"] == "save"

    def test_digest_templates_endpoints(self):
        """测试高管报表摘要模板相关的 HTTP 路由接口"""
        # 1. 测试获取全部模板
        response = self.client.get("/erp/digest/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert len(data["templates"]) == 4
        assert any(t["id"] == "sales_daily" for t in data["templates"])

        # 2. 测试获取单个模板详情
        detail_resp = self.client.get("/erp/digest/templates/sales_daily")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == "sales_daily"
        assert "prompt" in detail
        assert "任务: 生成销售日报。" in detail["prompt"]
        assert "查询要求:" in detail["prompt"]
        assert "输出要求:" in detail["prompt"]

        # 3. 测试不存在的模板返回错误信息
        bad_resp = self.client.get("/erp/digest/templates/invalid_id")
        assert bad_resp.status_code == 200
        assert "error" in bad_resp.json()

        # 4. 测试一键创建 Cron Job (模拟 CronManager 不可用的回退输出)
        create_resp = self.client.post("/erp/digest/templates/sales_daily/create", json={
            "channel": "wecom",
            "user_id": "admin_user",
            "enabled": True
        })
        assert create_resp.status_code == 200
        res_data = create_resp.json()
        assert res_data["status"] == "error"
        assert "CronManager 不可用" in res_data["message"]


class TestCrossSystemGlueTools:
    """对 integration/tools.py 里的胶水工具进行集成与模拟测试"""
    @pytest.mark.asyncio
    async def test_erp_unified_query_integration(self):
        # 1. 模拟两个 Backend 的注册
        reg = get_registry()
        
        mock_kingdee = MagicMock()
        mock_kingdee.system_name = "kingdee"
        mock_kingdee.display_name = "金蝶云星空"
        
        mock_sap = MagicMock()
        mock_sap.system_name = "sap"
        mock_sap.display_name = "SAP ERP"
        
        with patch.object(reg, "list_all", return_value=["kingdee", "sap"]), \
             patch.object(reg, "get", side_effect=lambda name: mock_kingdee if name == "kingdee" else mock_sap):
             
            # 2. 模拟客户端 API 查询结果
            kd_client = MagicMock()
            kd_future = asyncio.Future()
            kd_future.set_result([["SO001", "金蝶销售单1", "100.0"], ["SO002", "金蝶销售单2", "200.0"]])
            kd_client.execute_bill_query.return_value = kd_future
            mock_kingdee.get_client.return_value = kd_client
            
            sap_client = MagicMock()
            sap_future = asyncio.Future()
            sap_future.set_result([["SAP001", "SAP销售单1", "150.0"]])
            sap_client.execute_bill_query.return_value = sap_future
            mock_sap.get_client.return_value = sap_client

            # 3. 执行跨系统合并查询
            with patch("erp_config.ConfigManager.get_config", return_value={"server_url": "mock"}):
                res = await erp_unified_query(
                    systems="kingdee,sap",
                    query_params='{"form_id":"SAL_SaleOrder","field_keys":"FNumber,FName,FAmount"}'
                )
                
                assert res is not None
                text = res.blocks[0].text
                assert "统一查询结果" in text
                assert "金蝶云星空 (kingdee)" in text
                assert "SAP ERP (sap)" in text
                assert "SO001" in text
                assert "SAP001" in text

    @pytest.mark.asyncio
    async def test_erp_compare_data_integration(self):
        reg = get_registry()
        
        mock_kingdee = MagicMock()
        mock_kingdee.system_name = "kingdee"
        mock_kingdee.display_name = "金蝶云星空"
        
        mock_sap = MagicMock()
        mock_sap.system_name = "sap"
        mock_sap.display_name = "SAP ERP"
        
        with patch.object(reg, "list_all", return_value=["kingdee", "sap"]), \
             patch.object(reg, "get", side_effect=lambda name: mock_kingdee if name == "kingdee" else mock_sap):
             
            # 模拟金蝶返回 2 条数据 (SO001 金额 100, SO002 金额 200)
            kd_client = MagicMock()
            kd_future = asyncio.Future()
            kd_future.set_result([
                {"FNumber": "SO001", "FAmount": 100},
                {"FNumber": "SO002", "FAmount": 200}
            ])
            kd_client.execute_bill_query.return_value = kd_future
            mock_kingdee.get_client.return_value = kd_client
            
            # 模拟 SAP 返回 2 条数据 (SO001 金额 105 [金额值不一致], SO003 [只在 SAP 存在])
            sap_client = MagicMock()
            sap_future = asyncio.Future()
            sap_future.set_result([
                {"FNumber": "SO001", "FAmount": 105},
                {"FNumber": "SO003", "FAmount": 300}
            ])
            sap_client.execute_bill_query.return_value = sap_future
            mock_sap.get_client.return_value = sap_client

            with patch("erp_config.ConfigManager.get_config", return_value={"server_url": "mock"}):
                # 4. 执行数据比对，关键字段 FNumber，对比字段 FAmount
                res = await erp_compare_data(
                    left_system="kingdee",
                    left_query='{"form_id":"SAL_SaleOrder","field_keys":"FNumber,FAmount"}',
                    right_system="sap",
                    right_query='{"form_id":"SAL_SaleOrder","field_keys":"FNumber,FAmount"}',
                    key_field="FNumber",
                    compare_fields="FAmount"
                )
                
                assert res is not None
                text = res.blocks[0].text
                assert "数据比对：kingdee vs sap" in text
                assert "仅在 kingdee: 1 条" in text    # SO002
                assert "仅在 sap: 1 条" in text        # SO003
                assert "值差异: 1 处" in text          # SO001 的 FAmount
                assert "100 vs 105" in text

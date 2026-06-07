# -*- coding: utf-8 -*-
"""Focused tests for Kingdee business-level helper logic."""

import sys
import types
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

if "agentscope.message" not in sys.modules:
    agentscope_mod = types.ModuleType("agentscope")
    message_mod = types.ModuleType("agentscope.message")
    tool_mod = types.ModuleType("agentscope.tool")

    @dataclass
    class TextBlock:
        type: str
        text: str

    @dataclass
    class ToolResponse:
        content: list

    message_mod.TextBlock = TextBlock
    tool_mod.ToolResponse = ToolResponse
    sys.modules["agentscope"] = agentscope_mod
    sys.modules["agentscope.message"] = message_mod
    sys.modules["agentscope.tool"] = tool_mod

from backends.kingdee import tools
from backends.kingdee import prompts
from erp_permissions import OPERATIONS, PermissionManager, make_org_context_key


def _contains_emoji(text: str) -> bool:
    return any(
        0x1F300 <= ord(ch) <= 0x1FAFF
        or 0x2600 <= ord(ch) <= 0x27BF
        for ch in text
    )


def test_tool_prompt_definitions_are_centralized_and_plain_text():
    assert prompts.TOOL_DEFINITIONS
    for item in prompts.TOOL_DEFINITIONS:
        assert item["name"].startswith("kingdee_")
        assert item["description"]
        assert item["icon"] == prompts.DEFAULT_TOOL_ICON
        assert not _contains_emoji(item["description"])
        assert not _contains_emoji(item["icon"])


def test_centralized_tool_definitions_have_implementations():
    for item in prompts.TOOL_DEFINITIONS:
        assert hasattr(tools, item["name"]), f"{item['name']} 缺少工具实现"


def test_permission_operation_tools_are_in_centralized_definitions():
    defined = {item["name"] for item in prompts.TOOL_DEFINITIONS}
    mapped = {
        tool_name
        for op in OPERATIONS.values()
        for tool_name in op["tools"]
    }

    assert mapped <= defined


def test_manifest_tools_match_centralized_prompt_definitions():
    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["meta"]["tools"] == prompts.build_manifest_tools()


def test_report_templates_use_engineering_style_without_emoji():
    for template in prompts.REPORT_TEMPLATES.values():
        assert "任务:" in template["prompt"]
        assert "查询要求:" in template["prompt"]
        assert "输出要求:" in template["prompt"]
        assert not _contains_emoji(template["prompt"])


def test_collect_and_match_group_from_need_return_data():
    result = {
        "Result": {
            "NeedReturnData": (
                '{"Rows":[{"GroupPkId":101,"FNumber":"GN01","FName":"国内客户"}]}'
            ),
        },
    }

    candidates = tools._collect_group_candidates(result)
    parent_id, err = tools._match_group(candidates, parent_name="国内客户")

    assert err is None
    assert parent_id == "101"


def test_match_group_requires_disambiguation_for_duplicate_name():
    candidates = [
        {"id": "101", "number": "GN01", "name": "国内客户"},
        {"id": "102", "number": "GN02", "name": "国内客户"},
    ]

    parent_id, err = tools._match_group(candidates, parent_name="国内客户")

    assert parent_id == ""
    assert "匹配到多条" in err


def test_match_group_number_disambiguates_duplicate_name():
    candidates = [
        {"id": "101", "number": "GN01", "name": "国内客户"},
        {"id": "102", "number": "GN02", "name": "国内客户"},
    ]

    parent_id, err = tools._match_group(
        candidates,
        parent_name="国内客户",
        parent_number="GN02",
    )

    assert err is None
    assert parent_id == "102"


def test_match_group_custom_label_for_delete():
    candidates = [
        {"id": "101", "number": "GN01", "name": "国内客户"},
        {"id": "102", "number": "GN02", "name": "国内客户"},
    ]

    group_id, err = tools._match_group(
        candidates,
        parent_name="国内客户",
        label="分组",
    )

    assert group_id == ""
    assert "分组匹配到多条" in err
    assert "父分组" not in err


def test_normalize_inner_id_list_rejects_zero_and_text():
    ids, err = tools._normalize_inner_id_list("0", "客户内码")
    assert ids == ""
    assert "不能为0" in err

    ids, err = tools._normalize_inner_id_list("100,a", "客户内码")
    assert ids == ""
    assert "只能包含数字内码" in err


def test_kingdee_response_failure_detects_false_status():
    result = {
        "Result": {
            "ResponseStatus": {
                "IsSuccess": "false",
                "ErrorCode": "500",
                "Errors": [{"Message": "编码重复"}],
            }
        }
    }

    failure = tools._kingdee_response_failure(result)

    assert failure is not None
    assert "编码重复" in failure
    assert "ErrorCode=500" in failure


def test_kingdee_response_failure_ignores_success_status():
    result = {
        "Result": {
            "ResponseStatus": {
                "IsSuccess": True,
                "Errors": [],
            }
        }
    }

    assert tools._kingdee_response_failure(result) is None


def test_query_failure_response_blocks_failed_query_result():
    result = {
        "Result": {
            "ResponseStatus": {
                "IsSuccess": False,
                "Errors": [{"Message": "过滤条件错误"}],
            }
        }
    }

    response = tools._build_kingdee_query_failure("查询 BD_Supplier", result)

    assert response is not None
    assert "查询 BD_Supplier失败" in response.content[0].text
    assert "过滤条件错误" in response.content[0].text


def test_extract_success_entities_from_save_response():
    result = {
        "Result": {
            "ResponseStatus": {
                "IsSuccess": True,
                "SuccessEntitys": [
                    {"Id": 2001, "Number": "SUP001"},
                ],
            }
        }
    }

    assert tools._extract_success_entities(result) == [{"id": "2001", "number": "SUP001"}]


def test_recent_entity_registry_round_trip():
    caller = "console:tester:session-a"
    tools._clear_recent_entity(caller)

    tools._remember_recent_entity(
        caller,
        form_id="BD_Supplier",
        org_id="100",
        action="save",
        result={
            "Result": {
                "ResponseStatus": {
                    "IsSuccess": True,
                    "SuccessEntitys": [{"Id": 2001, "Number": "SUP001"}],
                }
            }
        },
    )
    recent = tools._get_recent_entity(caller)

    assert recent["form_id"] == "BD_Supplier"
    assert recent["org_id"] == "100"
    assert recent["entity"] == {"id": "2001", "number": "SUP001"}
    tools._clear_recent_entity(caller)
    assert tools._get_recent_entity(caller) is None


def test_recent_entity_registry_ignores_ambiguous_save_response():
    caller = "console:tester:session-b"
    tools._clear_recent_entity(caller)

    tools._remember_recent_entity(
        caller,
        form_id="BD_Supplier",
        org_id="100",
        action="save",
        result={
            "Result": {
                "ResponseStatus": {
                    "IsSuccess": True,
                    "SuccessEntitys": [
                        {"Id": 2001, "Number": "SUP001"},
                        {"Id": 2002, "Number": "SUP002"},
                    ],
                }
            }
        },
    )

    assert tools._get_recent_entity(caller) is None


def test_preview_token_is_single_use_and_parameter_bound():
    caller = "console:tester:session-c"
    first_key = tools._preview_key("BD_Supplier", "100", action="delete", ids="1")
    second_key = tools._preview_key("BD_Supplier", "100", action="delete", ids="2")

    tools._register_preview(caller, first_key)

    assert tools._check_previewed(caller, second_key) is False
    assert tools._check_previewed(caller, first_key) is True
    assert tools._check_previewed(caller, first_key) is False


def test_get_context_falls_back_to_unknown_identity(monkeypatch):
    monkeypatch.setattr(tools, "get_current_channel", None)
    monkeypatch.setattr(tools, "get_current_user_id", None)

    assert tools._get_context() == ("unknown", "unknown")


def test_validate_kingdee_config_reports_missing_fields():
    with pytest.raises(RuntimeError) as exc:
        tools._validate_kingdee_config({
            "server_url": "http://example/k3cloud/",
            "user_name": "demo",
            "app_id": "app",
        })

    text = str(exc.value)
    assert "金蝶连接配置不完整" in text
    assert "账套ID(acct_id)" in text
    assert "应用密钥(app_secret)" in text
    assert "'acct_id'" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "kwargs"),
    [
        (tools.kingdee_query_bill, {"form_id": "BAD_FORM", "field_keys": "FNumber"}),
        (tools.kingdee_view_bill, {"form_id": "BAD_FORM", "number": "B001"}),
        (tools.kingdee_get_report, {"form_id": "BAD_FORM", "field_keys": "FNumber"}),
    ],
)
async def test_read_tools_reject_invalid_form_id_before_runtime_context(monkeypatch, func, kwargs):
    async def fail_perm_mgr():
        raise AssertionError("权限链路不应在非法 FormId 时执行")

    async def fail_client():
        raise AssertionError("金蝶客户端不应在非法 FormId 时执行")

    monkeypatch.setattr(tools, "_is_valid_form_id", lambda form_id: False)
    monkeypatch.setattr(tools, "_get_perm_mgr", fail_perm_mgr)
    monkeypatch.setattr(tools, "_get_client", fail_client)

    response = await func(**kwargs)

    assert "不合法" in response.content[0].text


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute_bill_query(
        self,
        form_id,
        field_keys,
        filter_string="",
        order_string="",
        top_row_count=100,
        use_cache=True,
    ):
        self.calls.append({
            "form_id": form_id,
            "field_keys": field_keys,
            "filter_string": filter_string,
            "top_row_count": top_row_count,
            "use_cache": use_cache,
        })
        return self.rows


@pytest.mark.asyncio
async def test_resolve_master_data_ids_by_number_and_name():
    client = FakeClient([
        [1001, "C001", "华东客户"],
        [1002, "C002", "华南客户"],
    ])

    ids, err = await tools._resolve_master_data_ids(
        client,
        "BD_Customer",
        "FCUSTID",
        "FNumber",
        "FName",
        "C001",
        "华南客户",
        "客户",
    )

    assert err is None
    assert ids == "1001,1002"
    assert client.calls[0]["form_id"] == "BD_Customer"
    assert client.calls[0]["use_cache"] is False


@pytest.mark.asyncio
async def test_resolve_master_data_ids_propagates_business_failure():
    client = FakeClient({
        "Result": {
            "ResponseStatus": {
                "IsSuccess": False,
                "Errors": [{"Message": "基础资料查询失败"}],
            }
        }
    })

    ids, err = await tools._resolve_master_data_ids(
        client,
        "BD_Customer",
        "FCUSTID",
        "FNumber",
        "FName",
        "C001",
        "",
        "客户",
    )

    assert ids == ""
    assert "客户查询失败" in err
    assert "基础资料查询失败" in err


@pytest.mark.asyncio
async def test_resolve_master_data_ids_rejects_non_list_result():
    client = FakeClient({"unexpected": "shape"})

    ids, err = await tools._resolve_master_data_ids(
        client,
        "BD_Customer",
        "FCUSTID",
        "FNumber",
        "FName",
        "C001",
        "",
        "客户",
    )

    assert ids == ""
    assert "返回格式不是列表" in err


@pytest.mark.asyncio
async def test_resolve_master_data_ids_rejects_ambiguous_name():
    client = FakeClient([
        [1001, "C001", "华东客户"],
        [1002, "C002", "华东客户"],
    ])

    ids, err = await tools._resolve_master_data_ids(
        client,
        "BD_Customer",
        "FCUSTID",
        "FNumber",
        "FName",
        "",
        "华东客户",
        "客户",
    )

    assert ids == ""
    assert "名称不唯一" in err


class FailingGroupClient:
    async def query_group_info(self, form_id, group_field_key="", group_pk_ids="", ids=""):
        return {
            "Result": {
                "ResponseStatus": {
                    "IsSuccess": False,
                    "Errors": [{"Message": "分组服务异常"}],
                }
            }
        }


class QueryableGroupClient:
    def __init__(self):
        self.calls = []

    async def query_group_info(self, form_id, group_field_key="", group_pk_ids="", ids=""):
        self.calls.append({
            "form_id": form_id,
            "group_field_key": group_field_key,
            "group_pk_ids": group_pk_ids,
            "ids": ids,
        })
        if group_pk_ids:
            return {
                "Result": {
                    "NeedReturnData": (
                        '{"Rows":[{"GroupPkId":101,"FNumber":"UAT-GROUP-01",'
                        '"FName":"UAT华东客户"}]}'
                    ),
                    "ResponseStatus": {"IsSuccess": True, "Errors": []},
                }
            }
        return {
            "Result": {
                "NeedReturnData": (
                    '{"Rows":[{"GroupPkId":101,"FNumber":"UAT-GROUP-01",'
                    '"FName":"UAT华东客户"}]}'
                ),
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
            }
        }


@pytest.mark.asyncio
async def test_query_group_by_business_key_resolves_group_number(monkeypatch):
    tmp = tempfile.mktemp(suffix=".db")
    try:
        pm = PermissionManager(db_path=tmp)
        pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")
        client = QueryableGroupClient()

        async def fake_perm_mgr():
            return pm

        async def fake_client():
            return client

        monkeypatch.setattr(tools, "_identity", lambda: ("wecom", "user1"))
        monkeypatch.setattr(tools, "_get_perm_mgr", fake_perm_mgr)
        monkeypatch.setattr(tools, "_get_client", fake_client)

        response = await tools.kingdee_query_group_by_business_key(
            group_number="UAT-GROUP-01",
            form_id="BD_Customer",
            org_id="01",
        )

        text = response.content[0].text
        assert "基础资料分组信息" in text
        assert "UAT-GROUP-01" in text
        assert client.calls[-1]["group_pk_ids"] == "101"
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@pytest.mark.asyncio
async def test_create_group_under_parent_propagates_group_query_failure(monkeypatch):
    tmp = tempfile.mktemp(suffix=".db")
    try:
        pm = PermissionManager(db_path=tmp)
        pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="admin")

        async def fake_perm_mgr():
            return pm

        async def fake_client():
            return FailingGroupClient()

        monkeypatch.setattr(tools, "_identity", lambda: ("wecom", "user1"))
        monkeypatch.setattr(tools, "_get_perm_mgr", fake_perm_mgr)
        monkeypatch.setattr(tools, "_get_client", fake_client)

        response = await tools.kingdee_create_group_under_parent(
            name="华东客户",
            number="HD01",
            parent_name="国内客户",
            form_id="BD_Customer",
            org_id="01",
        )

        text = response.content[0].text
        assert "父分组查询 BD_Customer失败" in text
        assert "分组服务异常" in text
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class FailingSwitchClient:
    async def switch_org(self, org_number):
        raise RuntimeError("接口不可用")


@pytest.mark.asyncio
async def test_switch_org_rolls_back_default_org_on_client_exception(monkeypatch):
    tmp = tempfile.mktemp(suffix=".db")
    try:
        pm = PermissionManager(db_path=tmp)
        pm.set_permission("wecom:user1", "01", "张三", ["sales"], role="viewer")
        pm.set_permission("wecom:user1", "02", "张三", ["sales"], role="viewer")
        context_key = make_org_context_key("wecom", "user1", "agent-a")
        pm.set_default_org(context_key, "kingdee", "01")

        async def fake_perm_mgr():
            return pm

        async def fake_client():
            return FailingSwitchClient()

        monkeypatch.setattr(tools, "_identity", lambda: ("wecom", "user1"))
        monkeypatch.setattr(tools, "_agent_id", lambda: "agent-a")
        monkeypatch.setattr(tools, "_get_perm_mgr", fake_perm_mgr)
        monkeypatch.setattr(tools, "_get_client", fake_client)

        response = await tools.kingdee_switch_org("02")

        assert "默认组织未变更" in response.content[0].text
        assert pm.get_default_org(context_key, "kingdee") == "01"
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

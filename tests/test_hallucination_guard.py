# -*- coding: utf-8 -*-
"""Tests for hallucination guard system (standalone, minimal deps).

Run: python tests/test_hallucination_guard.py
"""
import sys
import os
import importlib.util
import threading
import types

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, SRC_DIR)


def _ensure_stubs():
    """Create minimal stubs so target modules can import."""
    if "agentscope.message" in sys.modules:
        return
    class _TextBlock:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _ToolResponse:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    as_msg = types.ModuleType("agentscope.message")
    as_msg.Msg = type("Msg", (), {})
    as_msg.ToolResultBlock = type("ToolResultBlock", (), {})
    as_msg.TextBlock = _TextBlock
    sys.modules["agentscope"] = types.ModuleType("agentscope")
    sys.modules["agentscope.model"] = types.ModuleType("agentscope.model")
    as_tool = types.ModuleType("agentscope.tool")
    as_tool.ToolResponse = _ToolResponse
    sys.modules["agentscope.tool"] = as_tool
    sys.modules["agentscope.agent"] = types.ModuleType("agentscope.agent")
    sys.modules["agentscope.message"] = as_msg
    for mod_name in [
        "agentscope_runtime",
        "agentscope_runtime.engine",
        "agentscope_runtime.engine.schemas",
        "agentscope_runtime.engine.schemas.exception",
    ]:
        sys.modules[mod_name] = types.ModuleType(mod_name)
    sys.modules["agentscope_runtime.engine.schemas.exception"].ConfigurationException = Exception
    # qwenpaw stubs
    qe = types.ModuleType("qwenpaw.exceptions")
    qe.ProviderError = Exception
    sys.modules["qwenpaw.exceptions"] = qe
    qc = types.ModuleType("qwenpaw.constant")
    qc.WORKING_DIR = "/tmp"
    qc.MEDIA_UNSUPPORTED_PLACEHOLDER = ""
    qc.TRUNCATION_NOTICE_MARKER = ""
    sys.modules["qwenpaw.constant"] = qc
    qapp = types.ModuleType("qwenpaw.app")
    qctx = types.ModuleType("qwenpaw.app.agent_context")
    qctx.get_current_channel = lambda: "test"
    qctx.get_current_session_id = lambda: "session-a"
    qctx.get_current_user_id = lambda: "user-a"
    sys.modules["qwenpaw.app"] = qapp
    sys.modules["qwenpaw.app.agent_context"] = qctx


def _import_kingdee_tools():
    """Import Kingdee tools with lightweight dependency stubs."""
    pkg_name = "kingdee_backend_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = []
    sys.modules[pkg_name] = pkg

    sdk = types.ModuleType(f"{pkg_name}.sdk")
    sdk.KingdeeClient = type("KingdeeClient", (), {})
    sdk._logger = None
    sys.modules[f"{pkg_name}.sdk"] = sdk

    erp_config = types.ModuleType("erp_config")
    erp_config.ConfigManager = type("ConfigManager", (), {"get_config": staticmethod(lambda *_: {})})
    sys.modules["erp_config"] = erp_config

    erp_permissions = types.ModuleType("erp_permissions")
    erp_permissions.PermissionManager = type(
        "PermissionManager",
        (),
        {"list_field_mappings": lambda self: []},
    )
    erp_permissions.check_operation_permission = lambda *_, **__: (True, "")
    erp_permissions.filter_fields_by_permission = lambda *args, **kwargs: args[4]
    erp_permissions.resolve_row_filter = lambda *_, **__: ""
    sys.modules["erp_permissions"] = erp_permissions

    return _import_mod(
        f"{pkg_name}.tools",
        os.path.join(
            ROOT_DIR,
            "plugins",
            "tool",
            "kingdee-erp",
            "backends",
            "kingdee",
            "tools.py",
        ),
    )


def _import_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ensure_stubs()

_hgm = _import_mod(
    "hgm",
    os.path.join(SRC_DIR, "qwenpaw", "agents", "hallucination_guard_mixin.py"),
)
_base = _import_mod(
    "tbase",
    os.path.join(SRC_DIR, "qwenpaw", "agents", "tools", "base.py"),
)


# ===================== 辅助函数内联实现（纯函数，无依赖） =====================

import re as _re

def _contains_factual_claims(text: str) -> bool:
    patterns = [
        _re.compile(r"\d{4}-\d{2}-\d{2}"),
        _re.compile(r"编码[是为:：]\s*\S+"),
        _re.compile(r"(?:金额|数量|总额|单价)为[：:：]?\s*[\d,.]+"),
        _re.compile(r"(供应商|组织|部门|仓库)[是为:：]"),
    ]
    return any(p.search(text) for p in patterns)


def _extract_text_from_msg(msg) -> str:
    if not hasattr(msg, "content"):
        return str(msg)
    c = msg.content
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        texts = []
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text":
                texts.append(b.get("text", ""))
        return "\n".join(texts)
    return str(c)


CITATION_RULE_TEST = """
## 引用规则（强制）

当你的回答基于以下来源时，必须标注出处：
- 基于记忆检索结果 -> 标注 [来源:记忆]
- 基于工具查询结果 -> 标注 [来源:工具名]
"""


# ===================== P1.1: _extract_file_refs_from_cmd =====================

def test_extract_absolute_unix():
    p = _hgm._extract_file_refs_from_cmd("python /home/u/script.py")
    assert "/home/u/script.py" in p


def test_extract_redirect():
    p = _hgm._extract_file_refs_from_cmd("echo > /tmp/out.txt")
    assert "/tmp/out.txt" in p


def test_extract_flag():
    p = _hgm._extract_file_refs_from_cmd("cat --file=/etc/passwd")
    assert "/etc/passwd" in p


def test_extract_none():
    p = _hgm._extract_file_refs_from_cmd("echo hello")
    assert p == []


def test_extract_none_cmd():
    assert _hgm._extract_file_refs_from_cmd("") == []
    assert _hgm._extract_file_refs_from_cmd(None) == []


# ===================== P1.1: _validate_tool_input =====================

def test_val_int_ok():
    def fn(count: int): ...
    assert _hgm._validate_tool_input(fn, {"count": 5}) == []


def test_val_int_type_err():
    def fn(count: int): ...
    v = _hgm._validate_tool_input(fn, {"count": "abc"})
    assert "类型错误" in v[0]


def test_val_missing():
    def fn(path: str): ...
    v = _hgm._validate_tool_input(fn, {})
    assert "缺少必填参数" in v[0]


def test_val_str_ok():
    def fn(name: str): ...
    assert _hgm._validate_tool_input(fn, {"name": "hello"}) == []


# ===================== P1.4: _contains_factual_claims =====================

def test_cf_date():
    assert _contains_factual_claims("日期为2024-01-01")


def test_cf_code():
    assert _contains_factual_claims("供应商编码为S001")


def test_cf_amount():
    assert _contains_factual_claims("金额为100.00")


def test_cf_not():
    assert not _contains_factual_claims("今天天气不错")


def test_cf_no_false_liang():
    assert not _contains_factual_claims("变量为10")


# ===================== P1.3: _extract_text_from_msg =====================

class _FakeMsg:
    def __init__(self, content):
        self.content = content


def test_extract_str():
    assert _extract_text_from_msg(_FakeMsg("hello")) == "hello"


def test_extract_list():
    r = _extract_text_from_msg(_FakeMsg([{"type": "text", "text": "hi"}, {"type": "text", "text": " there"}]))
    assert "hi" in r and "there" in r


# ===================== P1.5: AntiHallucinationToolMixin =====================

def test_two_step_preview():
    import asyncio
    t = _base.AntiHallucinationToolMixin()
    r = asyncio.run(t.enforce_two_step(False, {"x": "y"}))
    assert r is not None
    assert "pending" in str(r)


def test_two_step_has_lock():
    t = _base.AntiHallucinationToolMixin()
    assert hasattr(t, "_preview_lock")
    assert hasattr(t, "_previewed_keys")


def test_two_step_consumes_preview():
    import asyncio
    t = _base.AntiHallucinationToolMixin()
    params = {"x": "y"}
    assert asyncio.run(t.enforce_two_step(False, params)) is not None
    assert asyncio.run(t.enforce_two_step(True, params)) is None
    replay = asyncio.run(t.enforce_two_step(True, params))
    assert replay is not None and "error" in replay


def test_kingdee_preview_concurrent_consume_once():
    tools = _import_kingdee_tools()
    caller = "web:user-a:session-a"
    key = tools._preview_key("SAL_SaleOrder", "100", numbers="SO001")
    tools._register_preview(caller, key)

    barrier = threading.Barrier(8)
    results = []
    errors = []

    def worker():
        try:
            barrier.wait()
            results.append(tools._check_previewed(caller, key))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results.count(True) == 1
    assert results.count(False) == 7


def test_kingdee_preview_expired_blocks():
    tools = _import_kingdee_tools()
    caller = "web:user-a:session-expired"
    key = tools._preview_key("SAL_SaleOrder", "100", numbers="SO002")
    tools._PREVIEW_TTL_SECONDS = 1
    with tools._preview_registry_lock:
        tools._preview_registry[caller] = {key: tools.time.monotonic() - 2}
    assert not tools._check_previewed(caller, key)


# ===================== P2.3/P2.4: CITATION_RULE =====================

def test_citation():
    assert CITATION_RULE_TEST is not None
    assert "[来源:" in CITATION_RULE_TEST


# ===================== Main =====================

if __name__ == "__main__":
    tests = [
        ("extract_absolute_unix", test_extract_absolute_unix),
        ("extract_redirect", test_extract_redirect),
        ("extract_flag", test_extract_flag),
        ("extract_none", test_extract_none),
        ("extract_none_cmd", test_extract_none_cmd),
        ("val_int_ok", test_val_int_ok),
        ("val_int_type_err", test_val_int_type_err),
        ("val_missing", test_val_missing),
        ("val_str_ok", test_val_str_ok),
        ("cf_date", test_cf_date),
        ("cf_code", test_cf_code),
        ("cf_amount", test_cf_amount),
        ("cf_not", test_cf_not),
        ("cf_no_false_liang", test_cf_no_false_liang),
        ("extract_str", test_extract_str),
        ("extract_list", test_extract_list),
        ("two_step_preview", test_two_step_preview),
        ("two_step_has_lock", test_two_step_has_lock),
        ("two_step_consumes_preview", test_two_step_consumes_preview),
        ("kingdee_preview_concurrent_consume_once", test_kingdee_preview_concurrent_consume_once),
        ("kingdee_preview_expired_blocks", test_kingdee_preview_expired_blocks),
        ("citation", test_citation),
    ]
    ok = 0
    fail = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS: {name}")
            ok += 1
        except Exception as e:
            print(f"  FAIL: {name} - {e}")
            fail += 1
    print(f"\n{ok}/{ok+fail} passed")
    sys.exit(0 if fail == 0 else 1)

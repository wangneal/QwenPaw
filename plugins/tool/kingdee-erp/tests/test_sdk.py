# -*- coding: utf-8 -*-
"""Tests for Kingdee SDK (migrated from qwenpaw-kingdee/tests/test_sdk.py)."""

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure plugin root is on sys.path for absolute imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backends.kingdee.sdk import KingdeeClient, QueryCache


class TestQueryCache:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        cache = QueryCache(ttl=60)
        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self):
        cache = QueryCache(ttl=60)
        assert await cache.get("nonexistent") is None

    def test_make_key_deterministic(self):
        key1 = QueryCache.make_key("SAL_SaleOrder", "FDate,FQty", "FDate>='2026-01-01'")
        key2 = QueryCache.make_key("SAL_SaleOrder", "FDate,FQty", "FDate>='2026-01-01'")
        assert key1 == key2

    def test_make_key_different_inputs(self):
        key1 = QueryCache.make_key("SAL_SaleOrder", "FDate", "")
        key2 = QueryCache.make_key("BD_Material", "FDate", "")
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_clear(self):
        cache = QueryCache(ttl=60)
        await cache.set("key1", "value1")
        await cache.clear()
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_clear_by_form_id(self):
        cache = QueryCache(ttl=60)
        await cache.set("k1", "v1", form_id="SAL_SaleOrder")
        await cache.set("k2", "v2", form_id="SAL_SaleOrder")
        await cache.set("k3", "v3", form_id="PUR_PurchaseOrder")

        await cache.clear_by_form_id("SAL_SaleOrder")

        assert await cache.get("k1") is None
        assert await cache.get("k2") is None
        assert await cache.get("k3") == "v3"  # 不同 form_id 不受影响


class TestKingdeeClient:
    def _make_client(self):
        return KingdeeClient(
            server_url="http://192.168.1.100/k3cloud/",
            acct_id="test_acct",
            user_name="test_user",
            app_id="test_app",
            app_secret="test_secret",
        )

    def test_init_trailing_slash(self):
        client = KingdeeClient(
            server_url="http://192.168.1.100/k3cloud/",
            acct_id="a", user_name="u", app_id="aid", app_secret="s",
        )
        assert client.server_url == "http://192.168.1.100/k3cloud"  # trailing slash stripped

    def test_init_attributes(self):
        client = self._make_client()
        assert client.acct_id == "test_acct"
        assert client.lcid == 2052
        assert client._sdk is None

    @patch("backends.kingdee.sdk.HAS_OFFICIAL_SDK", False)
    @pytest.mark.asyncio
    async def test_ensure_no_sdk(self):
        client = self._make_client()
        with pytest.raises(RuntimeError, match="not installed"):
            await client._ensure()

    @patch("backends.kingdee.sdk.HAS_OFFICIAL_SDK", True)
    @pytest.mark.asyncio
    async def test_ensure_with_sdk(self):
        client = self._make_client()
        mock_sdk = MagicMock()
        with patch("backends.kingdee.sdk.K3CloudApiSdk", return_value=mock_sdk):
            await client._ensure()
            assert client._sdk is not None
            mock_sdk.InitConfig.assert_called_once()

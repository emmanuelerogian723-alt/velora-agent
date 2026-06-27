"""
Velora — Unit Tests for CROO Client
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from velora.croo.client import CROOClient


@pytest.fixture
def mock_sdk_client():
    mock = AsyncMock()
    return mock


@pytest.fixture
def croo(mock_sdk_client):
    client = CROOClient()
    client._client = mock_sdk_client
    return client, mock_sdk_client


@pytest.mark.asyncio
async def test_accept_negotiation_success(croo):
    client, sdk = croo
    sdk.accept_negotiation.return_value = MagicMock(order_id="order-abc")
    result = await client.accept_negotiation("neg-123")
    assert result is True
    sdk.accept_negotiation.assert_called_once_with("neg-123")


@pytest.mark.asyncio
async def test_accept_negotiation_retries_on_failure(croo):
    from croo import APIError
    client, sdk = croo
    sdk.accept_negotiation.side_effect = [
        Exception("timeout"),
        Exception("timeout"),
        MagicMock(order_id="order-abc"),
    ]
    with patch("velora.core.config.settings.DELIVERY_RETRY_ATTEMPTS", 3):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.accept_negotiation("neg-456")
    assert result is True


@pytest.mark.asyncio
async def test_deliver_order_success(croo):
    client, sdk = croo
    sdk.deliver_order.return_value = MagicMock()
    result = await client.deliver_order("order-001", "Here is your result.")
    assert result is True


@pytest.mark.asyncio
async def test_deliver_order_retries_then_fails(croo):
    client, sdk = croo
    sdk.deliver_order.side_effect = Exception("network error")
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client.deliver_order("order-fail", "content")
    assert result is False


@pytest.mark.asyncio
async def test_get_order_not_found(croo):
    from croo import APIError
    client, sdk = croo
    with patch("velora.croo.client.is_not_found", return_value=True):
        sdk.get_order.side_effect = APIError(code=404, reason="not_found", message="Order not found")
        result = await client.get_order("order-missing")
    assert result is None


@pytest.mark.asyncio
async def test_list_active_orders_empty(croo):
    client, sdk = croo
    sdk.list_orders.return_value = []
    result = await client.list_active_orders()
    assert result == []


@pytest.mark.asyncio
async def test_list_pending_negotiations(croo):
    client, sdk = croo
    mock_neg = MagicMock()
    mock_neg.id = "neg-001"
    sdk.list_negotiations.return_value = [mock_neg]
    result = await client.list_pending_negotiations()
    assert len(result) == 1

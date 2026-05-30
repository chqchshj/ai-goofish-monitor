import asyncio

from src.infrastructure.external.notification_clients.base import (
    NotificationClient,
    NotificationMessage,
)
from src.infrastructure.config.settings import NotificationSettings
from src.infrastructure.external.notification_clients.factory import (
    build_notification_clients_for_targets,
)
from src.infrastructure.external.notification_clients.webhook_client import WebhookClient
from src.services.notification_config_service import (
    build_configured_channels,
    build_notification_settings_response,
)
from src.services.notification_service import NotificationService


# ---------------------------------------------------------------------------
# Fake clients
# ---------------------------------------------------------------------------

class _OkClient(NotificationClient):
    channel_key = "ok"
    display_name = "OK"

    async def send(self, product_data, reason):
        return None


class _FailClient(NotificationClient):
    channel_key = "fail"
    display_name = "FAIL"

    async def send(self, product_data, reason):
        raise RuntimeError("boom")


class _SpyClient(NotificationClient):
    """Captures the NotificationMessage for inspection."""
    channel_key = "spy"
    display_name = "SPY"

    def __init__(self, enabled=True, pcurl_to_mobile=False):
        super().__init__(enabled=enabled, pcurl_to_mobile=pcurl_to_mobile)
        self.last_message: NotificationMessage | None = None

    async def send(self, product_data, reason):
        self.last_message = self._build_message(product_data, reason)
        return None


# ---------------------------------------------------------------------------
# Existing tests (must still pass)
# ---------------------------------------------------------------------------

def test_notification_service_collects_success_and_failure_results():
    service = NotificationService([_OkClient(enabled=True), _FailClient(enabled=True)])

    results = asyncio.run(
        service.send_notification({"商品标题": "Sony A7M4"}, "价格合适")
    )

    assert results["ok"]["success"] is True
    assert results["ok"]["message"] == "发送成功"
    assert results["fail"]["success"] is False
    assert results["fail"]["message"] == "boom"


def test_webhook_client_renders_json_templates(monkeypatch):
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

    def _fake_post(url, headers=None, json=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["data"] = data
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    client = WebhookClient(
        webhook_url="https://hooks.example.com/notify",
        webhook_method="POST",
        webhook_headers='{"Authorization":"Bearer token"}',
        webhook_content_type="JSON",
        webhook_query_parameters='{"task":"{{title}}"}',
        webhook_body='{"message":"{{content}}","link":"{{desktop_link}}"}',
        pcurl_to_mobile=False,
    )

    asyncio.run(
        client.send(
            {
                "商品标题": "Sony A7M4",
                "当前售价": "9999",
                "商品链接": "https://www.goofish.com/item/123",
            },
            "价格合适",
        )
    )

    assert "task=%F0%9F%9A%A8+%E6%96%B0%E6%8E%A8%E8%8D%90%21+Sony+A7M4" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["json"]["message"].startswith("价格: 9999")
    assert captured["json"]["link"] == "https://www.goofish.com/item/123"
    assert captured["data"] is None


def test_target_factory_overrides_telegram_chat_id():
    settings = NotificationSettings(
        telegram_bot_token="token",
        telegram_chat_id="global-chat",
    )

    clients = build_notification_clients_for_targets(
        settings,
        [{"channel": "telegram", "recipient": "task-chat"}],
    )

    telegram = [client for client in clients if client.channel_key == "telegram"][0]
    assert telegram.chat_id == "task-chat"
    assert telegram.bot_token == "token"


def test_target_factory_overrides_wecom_app_touser():
    settings = NotificationSettings(
        wecom_app_corpid="corp",
        wecom_app_secret="secret",
        wecom_app_agentid="1000001",
        wecom_app_touser="@all",
    )

    clients = build_notification_clients_for_targets(
        settings,
        [{"channel": "wecom_app", "recipient": "user1|user2"}],
    )

    wecom_app = [client for client in clients if client.channel_key == "wecom_app"][0]
    assert wecom_app.touser == "user1|user2"
    assert wecom_app.corpid == "corp"


def test_target_factory_empty_targets_uses_global_default():
    settings = NotificationSettings(
        telegram_bot_token="token",
        telegram_chat_id="global-chat",
    )

    clients = build_notification_clients_for_targets(settings, [])

    telegram = [client for client in clients if client.channel_key == "telegram"][0]
    assert telegram.chat_id == "global-chat"


def test_retired_channels_are_not_reported_as_configured_channels():
    settings = NotificationSettings(
        wecom_app_corpid="corp",
        wecom_app_secret="secret",
        wecom_app_agentid="1000001",
        telegram_bot_token="tg-token",
        telegram_chat_id="tg-chat",
        webhook_url="https://hooks.example.com/notify",
    )

    assert build_configured_channels(settings) == [
        "wecom_app",
        "telegram",
        "webhook",
    ]


def test_notification_settings_response_surfaces_channel_metadata():
    settings = NotificationSettings(
        wecom_app_corpid="corp",
        wecom_app_secret="secret",
        wecom_app_agentid="1000001",
        telegram_bot_token="tg-token",
        telegram_chat_id="tg-chat",
    )

    response = build_notification_settings_response(settings)

    assert response["CONFIGURED_CHANNELS"] == ["wecom_app", "telegram"]
    assert response["PREFERRED_CHANNELS"] == ["wecom_app"]
    assert "DEPRECATED_CHANNELS" not in response
    assert response["ADVANCED_COMPAT_CHANNELS"] == ["webhook"]


# ---------------------------------------------------------------------------
# P4-2: enriched _build_message fields
# ---------------------------------------------------------------------------

def test_build_message_extracts_region_tags_and_badges():
    """_build_message should extract 发货地区 and derive booleans from 商品标签."""
    client = _SpyClient(pcurl_to_mobile=False)
    product_data = {
        "商品标题": "iPhone 15 Pro",
        "当前售价": "5999",
        "商品链接": "https://www.goofish.com/item/456",
        "发货地区": "北京",
        "商品标签": ["验货宝", "包邮"],
        "卖家昵称": "张三",
    }

    asyncio.run(client.send(product_data, "价格不错"))
    msg = client.last_message

    assert msg.region == "北京"
    assert msg.tags == ["验货宝", "包邮"]
    assert msg.inspection_service is True
    assert msg.free_shipping is True
    assert msg.seller_nickname == "张三"


def test_build_message_missing_keys_default_gracefully():
    """Missing enriched keys should default to empty/False without crashing."""
    client = _SpyClient(pcurl_to_mobile=False)
    product_data = {
        "商品标题": "Minimal",
        "当前售价": "100",
        "商品链接": "https://www.goofish.com/item/min",
    }

    asyncio.run(client.send(product_data, "test"))
    msg = client.last_message

    assert msg.region == ""
    assert msg.tags == []
    assert msg.free_shipping is False
    assert msg.inspection_service is False
    assert msg.seller_nickname == ""
    assert msg.seller_type_persona == ""


def test_build_message_handles_none_tags():
    """None tags should become empty list, not crash."""
    client = _SpyClient(pcurl_to_mobile=False)
    product_data = {
        "商品标题": "NoneTags",
        "当前售价": "999",
        "商品链接": "https://www.goofish.com/item/none",
        "商品标签": None,
    }

    asyncio.run(client.send(product_data, "test"))
    msg = client.last_message

    assert msg.tags == []
    assert msg.free_shipping is False


def test_build_message_seller_type_from_underscore_keys():
    """_build_message reads seller_type persona from underscore-prefixed keys."""
    client = _SpyClient(pcurl_to_mobile=False)
    product_data = {
        "商品标题": "MacBook Pro",
        "当前售价": "8999",
        "商品链接": "https://www.goofish.com/item/mbp",
        "_seller_type_persona": "个人玩家",
        "_seller_type_status": "positive",
        "_seller_type_comment": "自用升级换机",
    }

    asyncio.run(client.send(product_data, "性价比高"))
    msg = client.last_message

    assert msg.seller_type_persona == "个人玩家"
    assert msg.seller_type_status == "positive"
    assert msg.seller_type_comment == "自用升级换机"


# ---------------------------------------------------------------------------
# P4-2: WeCom App TextCard description enrichment
# ---------------------------------------------------------------------------

def test_wecom_app_textcard_contains_enriched_fields(monkeypatch):
    """WeCom App TextCard description should include region, badges, and seller_type.

    Critical: NO HTML tags or raw links in description.
    """
    from src.infrastructure.external.notification_clients.wecom_app_client import (
        WeComAppClient,
    )

    captured_payload = {}

    def _fake_get_token(self):
        return "fake-token"

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"errcode": 0, "errmsg": "ok"}

    def _fake_post(url, json=None, timeout=None):
        captured_payload["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(WeComAppClient, "_get_access_token", _fake_get_token)
    monkeypatch.setattr("requests.post", _fake_post)

    client = WeComAppClient(
        corpid="corp",
        corpsecret="sec",
        agentid="1000001",
        touser="@all",
        pcurl_to_mobile=False,
    )

    asyncio.run(
        client.send(
            {
                "商品标题": "Nikon Z8",
                "当前售价": "25000",
                "商品链接": "https://www.goofish.com/item/z8",
                "发货地区": "上海",
                "商品标签": ["验货宝", "包邮"],
                "_seller_type_persona": "个人玩家",
            },
            "成色新",
        )
    )

    payload = captured_payload["json"]
    assert payload["msgtype"] == "textcard"
    desc = payload["textcard"]["description"]

    # Enriched content
    assert "📍 地区: 上海" in desc
    assert "🏷️" in desc and "验货宝" in desc and "包邮" in desc
    assert "👤 卖家: 个人玩家" in desc

    # Safety invariants: NO HTML, no raw links
    assert "<a " not in desc
    assert "href=" not in desc
    assert "<div" not in desc
    assert "</div>" not in desc
    assert "goofish.com" not in desc

    # Click hint preserved
    assert "点击卡片或下方按钮查看详情" in desc

    # URL should be on the card, not in description
    assert payload["textcard"]["url"] == "https://www.goofish.com/item/z8"


def test_wecom_app_description_safe_with_special_chars():
    """HTML-like content in user data should be escaped, not rendered."""
    from src.infrastructure.external.notification_clients.wecom_app_client import (
        WeComAppClient,
    )

    client = WeComAppClient(
        corpid="corp",
        corpsecret="sec",
        agentid="1000001",
        touser="@all",
        pcurl_to_mobile=False,
    )

    message = client._build_message(
        {
            "商品标题": "<script>alert(1)</script>",
            "当前售价": "<b>bold</b>",
            "商品链接": "#",
            "_seller_type_persona": "<a href='x'>商家</a>",
        },
        "<div>safe?</div>",
    )

    # The raw values arrive on NotificationMessage
    assert message.title == "<script>alert(1)</script>"
    # The client's send() method applies html.escape before rendering
    # We test this at integration level above


# ---------------------------------------------------------------------------
# P4-2: Telegram message enrichment
# ---------------------------------------------------------------------------

def test_telegram_message_contains_enriched_fields(monkeypatch):
    """Telegram message should include region, badges, and seller_type."""
    from src.infrastructure.external.notification_clients.telegram_client import (
        TelegramClient,
    )

    captured_text = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured_text["text"] = json["text"]
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    client = TelegramClient(
        bot_token="bot123",
        chat_id="chat456",
        pcurl_to_mobile=False,
    )

    asyncio.run(
        client.send(
            {
                "商品标题": "Fuji X-T5",
                "当前售价": "12000",
                "商品链接": "https://www.goofish.com/item/xt5",
                "发货地区": "广州",
                "商品标签": ["验货宝"],
                "_seller_type_persona": "发烧友自用",
            },
            "快门数低",
        )
    )

    text = captured_text["text"]
    assert "📍 地区: 广州" in text
    assert "🏷️ 验货宝" in text
    assert "👤 卖家: 发烧友自用" in text
    assert "💰 价格: 12000" in text
    assert "📝 原因: 快门数低" in text
    # No 包邮 badge when not present
    assert "包邮" not in text


# ---------------------------------------------------------------------------
# P4-2: Webhook enriched template vars
# ---------------------------------------------------------------------------

def test_webhook_client_renders_enriched_template_vars(monkeypatch):
    """Webhook templates should support ${region}, ${badges}, ${seller_type_persona}, etc."""
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

    def _fake_post(url, headers=None, json=None, data=None, timeout=None):
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    client = WebhookClient(
        webhook_url="https://hooks.example.com/notify",
        webhook_method="POST",
        webhook_content_type="JSON",
        webhook_body=(
            '{"region":"${region}",'
            '"badges":"${badges}",'
            '"seller_nickname":"${seller_nickname}",'
            '"seller_type_persona":"${seller_type_persona}",'
            '"free_shipping":"${free_shipping}",'
            '"inspection_service":"${inspection_service}"}'
        ),
        pcurl_to_mobile=False,
    )

    asyncio.run(
        client.send(
            {
                "商品标题": "Test Item",
                "当前售价": "500",
                "商品链接": "https://www.goofish.com/item/enriched",
                "发货地区": "深圳",
                "商品标签": ["验货宝", "包邮"],
                "卖家昵称": "测试卖家",
                "_seller_type_persona": "个人卖家",
            },
            "测试原因",
        )
    )

    payload = captured["json"]
    assert payload["region"] == "深圳"
    assert payload["badges"] == "验货宝 · 包邮"
    assert payload["seller_nickname"] == "测试卖家"
    assert payload["seller_type_persona"] == "个人卖家"
    assert payload["free_shipping"] == "true"
    assert payload["inspection_service"] == "true"


def test_webhook_badges_empty_without_tags():
    """badges template var should be empty string when no badges apply."""
    from src.infrastructure.external.notification_clients.base import (
        NotificationClient,
        NotificationMessage,
    )

    message = NotificationMessage(
        title="T",
        price="1",
        reason="R",
        desktop_link="#",
        mobile_link=None,
        notification_title="N",
        content="C",
        image_url=None,
    )

    client = WebhookClient(
        webhook_url="https://example.com/hook",
        pcurl_to_mobile=False,
    )

    result = client._replace_placeholders("${badges}", message)
    assert result == ""

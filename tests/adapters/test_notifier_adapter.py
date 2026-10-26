"""Unit tests for Notifier adapters."""

from unittest.mock import MagicMock, patch
import pytest
from trading_agent.adapters.notifier.console_adapter import ConsoleNotifierAdapter
from trading_agent.adapters.notifier.telegram_adapter import TelegramNotifierAdapter


def test_console_notifier(capsys):
    """Verify ConsoleNotifier prints formatted message to stdout."""
    notifier = ConsoleNotifierAdapter()
    result = notifier.send_notification("Test Alert 123")
    assert result is True

    captured = capsys.readouterr()
    assert "📢 [NOTIFICATION]" in captured.out
    assert "Test Alert 123" in captured.out


def test_telegram_unconfigured_fallback():
    """Verify Telegram notifier gracefully delegates to fallback when unconfigured."""
    mock_fallback = MagicMock()
    mock_fallback.send_notification.return_value = True

    notifier = TelegramNotifierAdapter(
        bot_token="",
        chat_id="",
        fallback_notifier=mock_fallback,
    )
    assert not notifier.is_configured

    res = notifier.send_notification("Unconfigured test")
    assert res is True
    mock_fallback.send_notification.assert_called_once_with("Unconfigured test")


@patch("requests.post")
def test_telegram_configured_success(mock_post):
    """Verify Telegram sends POST request when configured."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    notifier = TelegramNotifierAdapter(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        chat_id="987654321",
    )
    assert notifier.is_configured

    res = notifier.send_notification("Trade Alert: Buy RELIANCE")
    assert res is True
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11" in args[0]
    assert kwargs["json"]["chat_id"] == "987654321"
    assert kwargs["json"]["text"] == "Trade Alert: Buy RELIANCE"


@patch("requests.post")
def test_telegram_failure_fallback_to_console(mock_post):
    """Verify Telegram falls back to fallback notifier when network/API fails."""
    mock_post.side_effect = Exception("Network timeout")
    mock_fallback = MagicMock()
    mock_fallback.send_notification.return_value = True

    notifier = TelegramNotifierAdapter(
        bot_token="fake_token",
        chat_id="fake_chat",
        fallback_notifier=mock_fallback,
    )

    res = notifier.send_notification("Critical Alert")
    assert res is False  # Telegram send failed
    # But message was delivered to fallback
    mock_fallback.send_notification.assert_called_once_with("Critical Alert")

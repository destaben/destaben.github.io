from unittest.mock import MagicMock, patch

from signal_relay.telegram import TelegramNotifier


def test_sends_message_to_configured_telegram_chat():
    response = MagicMock()
    response.status = 200
    response.__enter__.return_value = response
    with patch("signal_relay.telegram.urlopen", return_value=response) as urlopen:
        TelegramNotifier("test-token", "12345").send_message("Hello from LXMF")

    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.telegram.org/bottest-token/sendMessage"
    assert request.data == b'{"chat_id": "12345", "text": "New Reticulum message\\n\\nHello from LXMF"}'
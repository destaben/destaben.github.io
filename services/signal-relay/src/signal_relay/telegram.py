from __future__ import annotations

import json
from urllib.request import Request, urlopen


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send_message(self, content: str) -> None:
        payload = json.dumps(
            {"chat_id": self._chat_id, "text": f"New LXMF message\n\n{content}"}
        ).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"Telegram returned HTTP {response.status}")
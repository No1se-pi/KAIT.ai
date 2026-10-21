from __future__ import annotations

import os
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from dataclasses import dataclass
from typing import Any

from app.logger import get_logger

logger = get_logger(__name__)
MAX_TEXT_LIMIT = 4000


@dataclass(frozen=True, slots=True)
class MaxIncoming:
    event_id: str
    update_type: str
    user_id: str
    chat_id: str
    text: str = ""
    action: str | None = None


def parse_max_update(payload: dict[str, Any]) -> MaxIncoming | None:
    update_type = str(payload.get("update_type") or "")
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    callback = payload.get("callback") if isinstance(payload.get("callback"), dict) else {}
    sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
    recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
    user = payload.get("user") if isinstance(payload.get("user"), dict) else sender

    if update_type == "bot_started":
        user_id = str(user.get("user_id") or "")
        chat_id = str(payload.get("chat_id") or user_id)
        return MaxIncoming(
            event_id=f"bot_started:{user_id}:{payload.get('timestamp', '')}",
            update_type=update_type,
            user_id=user_id,
            chat_id=chat_id,
            action="main_menu",
        ) if user_id and chat_id else None

    if update_type == "message_created":
        body = message.get("body") if isinstance(message.get("body"), dict) else {}
        user_id = str(sender.get("user_id") or payload.get("user_id") or "")
        chat_id = str(recipient.get("chat_id") or payload.get("chat_id") or user_id)
        text = str(body.get("text") or "").strip()
        message_id = str(body.get("mid") or message.get("message_id") or payload.get("timestamp") or "")
        if user_id and chat_id and text:
            return MaxIncoming(message_id, update_type, user_id, chat_id, text=text)
        return None

    if update_type == "message_callback":
        callback_message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
        callback_recipient = (
            callback_message.get("recipient")
            if isinstance(callback_message.get("recipient"), dict)
            else recipient
        )
        callback_user = callback.get("user") if isinstance(callback.get("user"), dict) else user
        user_id = str(callback_user.get("user_id") or payload.get("user_id") or "")
        chat_id = str(payload.get("chat_id") or callback_recipient.get("chat_id") or user_id)
        action = str(callback.get("payload") or "").strip()
        callback_id = str(callback.get("callback_id") or payload.get("timestamp") or "")
        if user_id and chat_id and action:
            return MaxIncoming(callback_id, update_type, user_id, chat_id, action=action)
    return None


class MaxBotClient:
    def __init__(self) -> None:
        self.token = os.getenv("MAX_BOT_TOKEN", "").strip()
        self.base_url = os.getenv("MAX_API_BASE_URL", "https://platform-api2.max.ru").rstrip("/")
        self.timeout = float(os.getenv("MAX_API_TIMEOUT_SECONDS", "8"))

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def send_answer(self, *, chat_id: str, text: str, buttons: list[dict[str, str]]) -> None:
        if not self.configured:
            raise RuntimeError("MAX_BOT_TOKEN is not configured")
        chunks = self._split_text(text)
        for index, chunk in enumerate(chunks):
            attachments = self._keyboard(buttons) if index == len(chunks) - 1 else []
            query = urlencode({"chat_id": chat_id, "disable_link_preview": "true"})
            body = json.dumps(
                {"text": chunk, "attachments": attachments or None},
                ensure_ascii=False,
            ).encode("utf-8")
            request = Request(
                f"{self.base_url}/messages?{query}",
                data=body,
                method="POST",
                headers={
                    "Authorization": self.token,
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"MAX API returned HTTP {response.status}")

    @staticmethod
    def _keyboard(buttons: list[dict[str, str]]) -> list[dict[str, Any]]:
        rows: list[list[dict[str, str]]] = []
        for button in buttons[:10]:
            item = {
                "type": "callback",
                "text": str(button.get("label") or "")[:64],
                "payload": str(button.get("action") or "")[:128],
            }
            if item["text"] and item["payload"]:
                rows.append([item])
        if not rows:
            return []
        return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]

    @staticmethod
    def _split_text(text: str) -> list[str]:
        value = text.strip()
        if len(value) <= MAX_TEXT_LIMIT:
            return [value]
        chunks: list[str] = []
        while value:
            cut = min(MAX_TEXT_LIMIT, len(value))
            if cut < len(value):
                cut = max(value.rfind("\n", 0, cut), value.rfind(" ", 0, cut), 1)
            chunks.append(value[:cut].strip())
            value = value[cut:].strip()
        return chunks

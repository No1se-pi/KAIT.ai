import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.chat_models import ChatSession
from app.logger import get_logger

logger = get_logger(__name__)


DEFAULT_ROUTE_STATE: dict[str, Any] = {
    "current_route": "kait",
    "route_step": "main_menu",
}


class SessionService:
    def get_or_create_session(
        self,
        db: Session,
        user_id: str,
        session_id: str | None = None,
        title: str = "Новый диалог",
    ) -> ChatSession:
        if session_id:
            existing_session = db.scalar(
                select(ChatSession).where(
                    ChatSession.session_id == session_id,
                    ChatSession.user_id == user_id,
                )
            )
            if existing_session:
                return existing_session

        new_session = ChatSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            metadata_json=DEFAULT_ROUTE_STATE.copy(),
        )
        db.add(new_session)
        # The caller commits the complete turn (session + messages) once.
        db.flush()

        logger.info(f"Создана новая сессия: {new_session.session_id}")
        return new_session

    def get_route_state(self, session: ChatSession) -> dict[str, Any]:
        raw = session.metadata_json or {}
        if not isinstance(raw, dict):
            raw = {}
        state = DEFAULT_ROUTE_STATE.copy()
        state.update(raw)
        return state

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.chat_models import ChatMessage
from app.logger import get_logger
from app.services.session_service import SessionService

logger = get_logger(__name__)

COLLEGE_NAME = "Колледж автоматизации и информационных технологий № 20"
SHORT_NAME = "КАИТ №20"
ADMISSION_URL = "https://priem.kait20.ru/"
SPECIALTIES_URL = "https://priem.kait20.ru/specialities"
OFFICIAL_URL = "https://kait20.mskobr.ru/"
PHONE = "+7 (499) 164-86-95"
EMAIL = "priem@kait20.ru"

MAIN_MENU = [
    "Специальности КАИТ",
    "Подобрать направление",
    "Поступление 2026",
    "Адреса и контакты",
    "Задать свой вопрос",
]
END_SESSION_BUTTON = "Завершить сессию"


def action_for_label(label: str, *, route: str | None = None, step: str | None = None) -> str:
    del route, step
    value = normalize(label)
    actions = {
        "специальности каит": "kait_specialties",
        "все специальности": "kait_specialties",
        "подобрать направление": "kait_match",
        "поступление 2026": "kait_admission",
        "адреса и контакты": "kait_contacts",
        "задать свой вопрос": "kait_question",
        "главное меню": "main_menu",
        "завершить сессию": "end_session",
    }
    return actions.get(value, re.sub(r"\W+", "_", value).strip("_") or "noop")

SPECIALTY_HINTS: dict[str, tuple[str, ...]] = {
    "Обеспечение информационной безопасности автоматизированных систем": (
        "кибер", "безопас", "защит", "хак", "пентест",
    ),
    "Интеграция решений с применением технологий искусственного интеллекта (Специалист по работе с ИИ)": (
        "искусствен", "нейро", "машинн", "данн", "ии", "ai",
    ),
    "Техника и искусство фотографии": ("фото", "камер", "съем", "съём", "контент"),
    "Компьютерные системы и комплексы": ("компьютер", "желез", "ремонт", "техподдерж"),
    "Разработка электронных устройств и систем": ("электрон", "плат", "микроконтрол", "схем"),
    "Сетевое и системное администрирование": ("сет", "сервер", "админ", "devops", "инфраструктур"),
    "Графический дизайнер": ("дизайн", "рис", "визуал", "график", "бренд"),
    "Веб-разработка": ("веб", "сайт", "frontend", "backend", "html", "javascript"),
    "Эксплуатация беспилотных авиационных систем": ("бпла", "дрон", "беспилот", "авиа"),
    "Техническая эксплуатация и сопровождение информационных систем": (
        "сопровожд", "информационн систем", "поддержк", "эксплуатац",
    ),
    "Разработка и управление программным обеспечением (Программист)": (
        "программ", "разработ", "код", "python", "приложен",
    ),
    "Интеллектуальные интегрированные системы": (
        "умн", "iot", "автоматизац", "робот", "интегрирован",
    ),
}


def normalize(text: str | None) -> str:
    value = (text or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9№+.-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True, slots=True)
class Specialty:
    name: str
    professions: tuple[str, ...]
    url: str


class KaitCatalog:
    """Small immutable in-memory catalog used by the latency-critical path."""

    def __init__(self, data_path: str | None = None) -> None:
        path = Path(data_path or get_settings().data_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        college = next(
            (item for item in raw if "автоматизации и информационных технологий № 20" in str(item.get("name", "")).lower()),
            None,
        )
        if not college:
            raise RuntimeError(f"КАИТ №20 не найден в {path}")

        self.name = str(college["name"])
        self.addresses = tuple(str(item) for item in college.get("addresses", []))
        self.contacts = tuple(str(item) for item in college.get("contacts", []))
        self.specialties = tuple(
            Specialty(
                name=str(item.get("name", "")).strip(),
                professions=tuple(str(value) for value in item.get("professions", []) if str(value).strip()),
                url=str(item.get("atlas_url") or SPECIALTIES_URL),
            )
            for item in college.get("specialties", [])
            if str(item.get("name", "")).strip()
        )

    def match_specialties(self, query: str, limit: int = 3) -> list[Specialty]:
        q = normalize(query)
        scored: list[tuple[int, Specialty]] = []
        for specialty in self.specialties:
            name = normalize(specialty.name)
            score = 10 if name and name in q else 0
            score += sum(3 for hint in SPECIALTY_HINTS.get(specialty.name, ()) if hint in q)
            score += sum(2 for profession in specialty.professions if normalize(profession) in q)
            if score:
                scored.append((score, specialty))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [item for _, item in scored[:limit]]

    def specialty_by_number(self, number: int) -> Specialty | None:
        if 1 <= number <= len(self.specialties):
            return self.specialties[number - 1]
        return None


class KaitAssistantService:
    """Fast single-college assistant shared by API, Telegram and MAX."""

    def __init__(self, session_service: SessionService | None = None, catalog: KaitCatalog | None = None) -> None:
        self.session_service = session_service or SessionService()
        self.catalog = catalog or KaitCatalog()

    def ask(
        self,
        db: Session,
        user_id: str,
        message: str,
        session_id: str | None = None,
        *,
        route: str | None = None,
        action: str | None = None,
        user_type: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        del route, user_type, top_k
        started = time.perf_counter()
        session = self.session_service.get_or_create_session(db, user_id, session_id, title="КАИТ №20")
        query = (message or "").strip()
        action_code = normalize(action).replace(" ", "_")
        answer, mode, suggestions, topic = self._answer(query, action_code)

        state = self.session_service.get_route_state(session)
        state.update({"current_route": "kait", "route_step": topic, "last_answer": answer})
        session.metadata_json = state
        if query:
            db.add(ChatMessage(session_db_id=session.id, role="user", content=query))
        db.add(ChatMessage(session_db_id=session.id, role="assistant", content=answer))
        db.add(session)
        db.commit()

        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info("KAIT fast answer: mode=%s topic=%s latency_ms=%.1f", mode, topic, elapsed_ms)
        return {
            "session_id": session.session_id,
            "answer": answer,
            "dialog_mode": mode,
            "route": "kait",
            "step": topic,
            "suggestions": suggestions,
            "suggestion_labels": suggestions,
            "suggestion_buttons": self._suggestion_buttons(suggestions),
            "latency_ms": elapsed_ms,
        }

    def _answer(self, query: str, action: str) -> tuple[str, str, list[str], str]:
        q = normalize(query)
        combined = f"{q} {action}".strip()

        specialty_number = self._extract_specialty_number(combined)
        if specialty_number:
            specialty = self.catalog.specialty_by_number(specialty_number)
            if specialty:
                return self._specialty_detail(specialty)

        if not combined or action in {"start", "main_menu", "kait_menu"} or q in {"привет", "здравствуйте", "начать"}:
            return (
                "Привет! Я KAIT.ai — помощник абитуриента КАИТ №20. "
                "Быстро расскажу о специальностях, поступлении и учебных площадках колледжа.",
                "menu",
                MAIN_MENU,
                "main_menu",
            )

        if action == "kait_specialties" or any(marker in q for marker in ("специальност", "направлен", "что есть", "чему учат")):
            matches = self.catalog.match_specialties(q)
            if len(matches) == 1:
                return self._specialty_detail(matches[0])
            return self._specialties_answer()

        if action == "kait_match" or any(marker in q for marker in ("подобрать", "что выбрать", "кем стать", "интерес", "люблю", "нравится")):
            matches = self.catalog.match_specialties(q)
            if matches:
                names = "\n".join(f"{index}. {item.name}" for index, item in enumerate(matches, 1))
                return (
                    f"По твоему запросу лучше всего подходят:\n\n{names}\n\n"
                    "Выбери программу — покажу детали. Это подбор только среди программ КАИТ №20.",
                    "recommend",
                    [item.name for item in matches] + ["Главное меню"],
                    "recommendation",
                )
            return (
                "Напиши, что тебе нравится: программировать, работать с компьютерами и сетями, "
                "защищать данные, создавать дизайн и фото, собирать электронику или работать с БПЛА.",
                "clarify",
                ["ИТ и программирование", "Дизайн и фото", "Электроника и БПЛА", "Главное меню"],
                "awaiting_interests",
            )

        direct_matches = self.catalog.match_specialties(q)
        if direct_matches:
            return self._specialty_detail(direct_matches[0])

        if action == "kait_contacts" or any(marker in q for marker in ("контакт", "телефон", "почт", "адрес", "где находится", "как добраться")):
            addresses = "\n".join(f"• {item}" for item in self.catalog.addresses)
            return (
                f"Приёмная комиссия КАИТ №20:\n☎ {PHONE}\n✉ {EMAIL}\n🌐 {ADMISSION_URL}\n\n"
                f"Учебные площадки:\n{addresses}",
                "contacts",
                ["Специальности КАИТ", "Поступление 2026", "Главное меню"],
                "contacts",
            )

        if action == "kait_admission" or any(marker in q for marker in ("поступ", "прием", "приём", "документ", "огэ", "экзамен", "заявлен", "конкурс", "бюджет", "платн")):
            return self._admission_answer(q)

        if any(marker in q for marker in ("общежит", "отсроч", "стипенд", "льгот", "овз", "инвалид")):
            return (
                "Этот вопрос зависит от действующих правил и ситуации абитуриента. Чтобы не дать устаревший ответ, "
                f"проверь раздел приёма {ADMISSION_URL} или уточни в комиссии: {PHONE}, {EMAIL}.",
                "verified_redirect",
                ["Поступление 2026", "Адреса и контакты", "Главное меню"],
                "admission_detail",
            )

        return (
            "Я отвечаю только про КАИТ №20. Уточни вопрос — например, назови интересующую специальность, "
            "спроси о поступлении или нужной учебной площадке.",
            "clarify",
            MAIN_MENU,
            "clarify",
        )

    def _specialties_answer(self) -> tuple[str, str, list[str], str]:
        rows = [f"{index}. {item.name}" for index, item in enumerate(self.catalog.specialties, 1)]
        return (
            "В КАИТ №20 на странице приёма 2026 опубликованы 12 программ:\n\n"
            + "\n".join(rows)
            + f"\n\nАктуальные условия по каждой программе: {SPECIALTIES_URL}\nНапиши номер — расскажу подробнее.",
            "specialties",
            ["Подобрать направление", "Поступление 2026", "Главное меню"],
            "specialties",
        )

    def _specialty_detail(self, specialty: Specialty) -> tuple[str, str, list[str], str]:
        professions = (
            "\n".join(f"• {item}" for item in specialty.professions)
            if specialty.professions
            else "Профили и квалификации уточняются в карточке программы."
        )
        return (
            f"{specialty.name}\n\nКем можно работать:\n{professions}\n\n"
            f"Карточка программы и актуальные условия набора: {SPECIALTIES_URL}",
            "specialty_detail",
            ["Все специальности", "Подобрать направление", "Поступление 2026", "Главное меню"],
            "specialty_detail",
        )

    def _admission_answer(self, query: str) -> tuple[str, str, list[str], str]:
        if "бюдж" in query or "платн" in query or "стоим" in query:
            text = (
                "В КАИТ №20 есть бюджетные программы, а для части направлений — также внебюджет. "
                "Форма финансирования зависит от специальности и базы образования. "
                f"Сверь выбранную программу здесь: {SPECIALTIES_URL}."
            )
        elif "экзам" in query or "огэ" in query or "гиа" in query:
            text = (
                "На странице приёма КАИТ №20 указано, что поступление после 9 класса учитывает результаты "
                "двух основных экзаменов ГИА — русского языка и математики. Для творческих программ могут быть "
                f"дополнительные испытания; проверь карточку программы: {SPECIALTIES_URL}."
            )
        else:
            text = (
                "Приёмная кампания КАИТ №20 — 2026:\n"
                f"• программы и условия: {SPECIALTIES_URL}\n"
                f"• анкета и новости приёма: {ADMISSION_URL}\n"
                f"• телефон: {PHONE}\n"
                f"• почта: {EMAIL}\n\n"
                "Сроки, документы и число мест лучше сверять на странице приёма: эти данные могут обновляться."
            )
        return text, "admission", ["Специальности КАИТ", "Адреса и контакты", "Главное меню"], "admission"

    @staticmethod
    def _extract_specialty_number(value: str) -> int | None:
        match = re.search(r"(?:specialty[: _]?|специальность_?|номер\s*)?(\d{1,2})$", value)
        return int(match.group(1)) if match else None

    def _suggestion_buttons(self, labels: list[str]) -> list[dict[str, str]]:
        actions = {
            "Специальности КАИТ": "kait_specialties",
            "Все специальности": "kait_specialties",
            "Подобрать направление": "kait_match",
            "Поступление 2026": "kait_admission",
            "Адреса и контакты": "kait_contacts",
            "Задать свой вопрос": "kait_question",
            "Главное меню": "main_menu",
        }
        specialty_numbers = {item.name: index for index, item in enumerate(self.catalog.specialties, 1)}
        return [
            {
                "label": label,
                "action": actions.get(label) or f"specialty:{specialty_numbers[label]}",
            }
            for label in labels
            if label in actions or label in specialty_numbers
        ]

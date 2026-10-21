import time
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.chat_models  # noqa: F401
from app.db.repository import Base
from app.services.kait_assistant import KaitAssistantService, KaitCatalog


class KaitAssistantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.session_factory = sessionmaker(bind=cls.engine)
        cls.service = KaitAssistantService(catalog=KaitCatalog("data/colleges.json"))

    def ask(self, message: str = "", action: str | None = None):
        with self.session_factory() as db:
            return self.service.ask(db, "test-user", message, action=action)

    def test_catalog_contains_only_kait_programs(self) -> None:
        self.assertEqual(len(self.service.catalog.specialties), 12)
        self.assertTrue(all(item.name for item in self.service.catalog.specialties))

    def test_specialties_are_answered_without_rag_or_llm(self) -> None:
        started = time.perf_counter()
        result = self.ask("Какие специальности есть?")
        elapsed = time.perf_counter() - started
        self.assertEqual(result["dialog_mode"], "specialties")
        self.assertIn("Веб-разработка", result["answer"])
        self.assertLess(elapsed, 0.25)

    def test_interest_matching_is_kait_only(self) -> None:
        result = self.ask("Люблю серверы, сети и настраивать инфраструктуру")
        self.assertEqual(result["dialog_mode"], "recommend")
        self.assertIn("Сетевое и системное администрирование", result["answer"])
        self.assertNotIn("других колледж", result["answer"].lower())

    def test_admission_answer_uses_official_source(self) -> None:
        result = self.ask("Как поступить в 2026 году?")
        self.assertEqual(result["dialog_mode"], "admission")
        self.assertIn("https://priem.kait20.ru/", result["answer"])

    def test_known_action_returns_contacts(self) -> None:
        result = self.ask(action="kait_contacts")
        self.assertEqual(result["dialog_mode"], "contacts")
        self.assertIn("priem@kait20.ru", result["answer"])

    def test_session_cannot_be_reused_by_another_user(self) -> None:
        first = self.ask("Привет")
        with self.session_factory() as db:
            second = self.service.ask(
                db,
                "another-user",
                "Привет",
                session_id=first["session_id"],
            )
        self.assertNotEqual(first["session_id"], second["session_id"])


if __name__ == "__main__":
    unittest.main()

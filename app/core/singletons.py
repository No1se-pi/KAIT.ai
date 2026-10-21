from functools import lru_cache

from app.services.kait_assistant import KaitAssistantService


@lru_cache
def get_scenario_service() -> KaitAssistantService:
    return KaitAssistantService()

from sqlalchemy.orm import DeclarativeBase

from app.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


def create_tables(engine) -> None:
    logger.info("Создание таблиц сессий в БД...")
    Base.metadata.create_all(bind=engine)
    logger.info("Таблицы успешно созданы")

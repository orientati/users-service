from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def import_models():
    from app.models.user import User  # noqa: E402 F401
    from app.models.outbox import OutboxMessage  # noqa: E402 F401

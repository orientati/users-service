from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.broker import AsyncBrokerSingleton
from app.services.http_client import OrientatiException

logger = get_logger(__name__)

RABBIT_DELETE_TYPE = "DELETE"
RABBIT_UPDATE_TYPE = "UPDATE"
RABBIT_CREATE_TYPE = "CREATE"


class UserCreateErrorType(Enum):
    INVALID_EMAIL = "invalid_email"
    EMAIL_TAKEN = "email_taken"
    INVALID_PASSWORD = "invalid_password"


class UserCreateError(OrientatiException):
    def __init__(self, message: str, error_type: str = "default_error"):
        super().__init__("Bad Request", 400, {
            "message": message,
            "type": error_type
        }, "/users/create")


def list_users(db: Session, limit: int = 50, offset: int = 0) -> Iterable[User]:
    try:
        stmt = select(User).limit(limit).offset(offset)
        return db.execute(stmt).scalars().all()
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/list",
        )


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


async def create_user(db: Session, payload: UserCreate) -> User:
    try:
        existing_user = db.query(User).filter_by(email=payload.email).first()
        if existing_user:
            raise UserCreateError(
                message="Email already in use",
                error_type=UserCreateErrorType.EMAIL_TAKEN.value,
            )

        if not payload.email or "@" not in payload.email:
            raise UserCreateError(
                message="Invalid email format",
                error_type=UserCreateErrorType.INVALID_EMAIL.value,
            )

        user = User(**payload.model_dump())
        db.add(user)
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_CREATE_TYPE)
        await send_verification_email(user)
        return user
    except UserCreateError as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/create",
        )


async def update_user(db: Session, user_id: int, payload: UserUpdate) -> User | None:
    try:
        user = db.get(User, user_id)
        if not user:
            raise OrientatiException(
                status_code=404,
                message="Not Found",
                details={"message": "User not found"},
                url=f"users/{user_id}"
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_UPDATE_TYPE)
        return user
    except OrientatiException as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}",
        )


async def change_user_password(db: Session, user_id: int, old_password: str, new_password: str) -> bool:
    try:
        user = db.get(User, user_id)
        if not user or user.hashed_password != old_password:
            return False
        user.hashed_password = new_password
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_UPDATE_TYPE)
        return True
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}/change_password",
        )


async def delete_user(db: Session, user_id: int) -> bool:
    try:
        user = db.get(User, user_id)
        if not user:
            return False
        db.delete(user)
        db.commit()
        await update_services(user, RABBIT_DELETE_TYPE)
        return True
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}/delete",
        )


async def update_services(user: User, operation: str):
    try:
        broker_instance = AsyncBrokerSingleton()
        connected = await broker_instance.connect()
        if connected:
            message = {
                "id": user.id,
                "email": user.email,
                "email_verified": user.email_verified,
                "name": user.name,
                "surname": user.surname,
                "hashed_password": user.hashed_password,
                "created_at": str(user.created_at),
                "updated_at": str(user.updated_at)
            } if operation != RABBIT_DELETE_TYPE else {"id": user.id}
            await broker_instance.publish_message("users", operation, message)
        else:
            logger.warning("Could not connect to broker.")
    except Exception as e:
        logger.error(f"Error updating services for user {user.id}. Operation: {operation}: {e}")
        raise e


async def send_verification_email(user: User):
    try:
        broker_instance = AsyncBrokerSingleton()
        connected = await broker_instance.connect()
        if connected:
            token = secrets.token_urlsafe(32)
            email_request = {
                "to": user.email,
                "subject": "Verifica il tuo Account Orientati",
                "template_name": "verify_email_v1",
                "context": {
                    "username": f"{user.surname} {user.name}",
                    "link": f"https://{settings.SERVER_URL}/api/v1/users/verify_email?token={token}"
                }
            }

            db = next(get_db())
            db_user = db.query(User).filter(User.id == user.id).first()
            if not db_user:
                raise OrientatiException(
                     status_code=404,
                     message="Not Found",
                     details={"message": "User not found during verification email generation"},
                     url=f"users/{user.id}/send_verification_email"
                 )
            db_user.email_verified = False  # TODO: considerare se controllare se è già verificato
            db_user.verify_email_token = token
            db_user.verify_email_token_expiration = datetime.now() + timedelta(minutes=30)
            db.commit()
            await update_services(db_user, RABBIT_UPDATE_TYPE)
            await broker_instance.publish_message("email", "email_notification", email_request,
                                                  routing_key="send_email")
        else:
            logger.warning("Could not connect to broker.")
    except Exception as e:
        logger.error(f"Error sending verification email for user {user.id}: {e}")
        raise e


async def request_email_verification(user_id: int, db: Session):
    try:
        user = get_user(db, user_id)
        if not user:
            raise OrientatiException(
                status_code=404,
                message="Not Found",
                details={"message": "User not found"},
                url=f"users/{user_id}/request_email_verification"
            )
        await send_verification_email(user)
    except OrientatiException as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}/request_email_verification",
        )


async def verify_email(token: str):
    """
    Verifica l'email dell'utente tramite il token passato
    :param token:
    :return: stato verifica
    """
    try:
        db = next(get_db())
        user = db.query(User).filter(User.verify_email_token == token).first()
        if not user:
            raise OrientatiException(
                status_code=404,
                message="Not Found",
                details={"message": "Invalid verification token"},
                url="users/verify_email"
            )

        if user.verify_email_token_expiration < datetime.now(timezone.utc):
            raise OrientatiException(
                status_code=400,
                message="Bad Request",
                details={"message": "Verification token has expired"},
                url="users/verify_email"
            )
        user.email_verified = True
        user.verify_email_token = None
        user.verify_email_token_expiration = None
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_UPDATE_TYPE)
        return True
    except OrientatiException as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/verify_email",
        )

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
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


async def list_users(db: AsyncSession, limit: int = 50, offset: int = 0) -> Sequence[User]:
    try:
        stmt = select(User).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/list",
        )


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    try:
        stmt = select(User).filter_by(email=payload.email)
        result = await db.execute(stmt)
        existing_user = result.scalars().first()
        
        if existing_user:
            if not existing_user.email_verified:
                await send_verification_email(existing_user, db)
            return existing_user

        user = User(**payload.model_dump())
        db.add(user)
        await update_services(user, RABBIT_CREATE_TYPE, db)
        await send_verification_email(user, db)
        await db.commit()
        await db.refresh(user)
        return user
    except UserCreateError as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/create",
        )


async def update_user(db: AsyncSession, user_id: int, payload: UserUpdate) -> User | None:
    try:
        user = await db.get(User, user_id)
        if not user:
            raise OrientatiException(
                status_code=404,
                message="Not Found",
                details={"message": "User not found"},
                url=f"users/{user_id}"
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await update_services(user, RABBIT_UPDATE_TYPE, db)
        await db.commit()
        await db.refresh(user)
        return user
    except OrientatiException as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}",
        )


async def change_user_password(db: AsyncSession, user_id: int, old_password: str, new_password: str) -> bool:
    try:
        user = await db.get(User, user_id)
        if not user or user.hashed_password != old_password:
            return False
        user.hashed_password = new_password
        await update_services(user, RABBIT_UPDATE_TYPE, db)
        await db.commit()
        await db.refresh(user)
        return True
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}/change_password",
        )


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    try:
        user = await db.get(User, user_id)
        if not user:
            return False
        await update_services(user, RABBIT_DELETE_TYPE, db)
        await db.delete(user)
        await db.commit()
        return True
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}/delete",
        )


async def update_services(user: User, operation: str, db: AsyncSession):
    """Write message to outbox for eventual delivery to other services.
    
    Args:
        user: User object
        operation: Operation type (CREATE, UPDATE, DELETE)
        db: Database session - MUST be the same session as the user operation for atomicity
    """
    try:
        from app.models.outbox import OutboxMessage
        import json
        
        message_payload = {
            "id": user.id,
            "email": user.email,
            "email_verified": user.email_verified,
            "name": user.name,
            "surname": user.surname,
            "hashed_password": user.hashed_password,
            "created_at": str(user.created_at),
            "updated_at": str(user.updated_at)
        } if operation != RABBIT_DELETE_TYPE else {"id": user.id}
        
        outbox_message = OutboxMessage(
            exchange_name="users",
            message_type=operation,
            routing_key="",
            payload=json.dumps(message_payload)
        )
        
        db.add(outbox_message)
        # Note: commit will be done by caller as part of the same transaction
        
        logger.info(f"Added outbox message for user {user.id}, operation: {operation}")
        
    except Exception as e:
        logger.error(f"Error adding outbox message for user {user.id}. Operation: {operation}: {e}")
        raise e



async def send_verification_email(user: User, db: AsyncSession):
    """Send verification email by writing to outbox for transactional delivery.
    
    Args:
        user: User object
        db: Database session - MUST be the same session as the user operation for atomicity
    """
    try:
        from app.models.outbox import OutboxMessage
        import json
        
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

        stmt = select(User).where(User.id == user.id)
        result = await db.execute(stmt)
        db_user = result.scalars().first()
        
        if not db_user:
            raise OrientatiException(
                 status_code=404,
                 message="Not Found",
                 details={"message": "User not found during verification email generation"},
                 url=f"users/{user.id}/send_verification_email"
             )
        
        # Update user with verification token
        db_user.email_verified = False
        db_user.verify_email_token = token
        db_user.verify_email_token_expiration = datetime.now(timezone.utc) + timedelta(minutes=30)
        
        # Write to outbox for eventual delivery
        outbox_message = OutboxMessage(
            exchange_name="email",
            message_type="email_notification",
            routing_key="send_email",
            payload=json.dumps(email_request)
        )
        db.add(outbox_message)
        
        # Note: commit will be done by caller as part of the same transaction
        logger.info(f"Added verification email to outbox for user {user.id}")
        
    except Exception as e:
        logger.error(f"Error adding verification email to outbox for user {user.id}: {e}")
        raise e


async def verify_email(token: str, db: AsyncSession):
    """
    Verifica l'email dell'utente tramite il token passato
    :param token:
    :param db:
    :return: stato verifica
    """
    try:
        stmt = select(User).where(User.verify_email_token == token)
        result = await db.execute(stmt)
        user = result.scalars().first()
        
        if not user:
            raise OrientatiException(
                status_code=404,
                message="Not Found",
                details={"message": "Invalid verification token"},
                url="users/verify_email"
            )

        # Ensure datetime is timezone aware if needed, or consistent with stored time
        # Here we assume token expiration check logic matches original intent
        if user.verify_email_token_expiration and user.verify_email_token_expiration < datetime.now(timezone.utc):
            raise OrientatiException(
                status_code=400,
                message="Bad Request",
                details={"message": "Verification token has expired"},
                url="users/verify_email"
            )
        user.email_verified = True
        user.verify_email_token = None
        user.verify_email_token_expiration = None
        await update_services(user, RABBIT_UPDATE_TYPE, db)
        await db.commit()
        await db.refresh(user)
        return True
    except OrientatiException as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/verify_email",
        )

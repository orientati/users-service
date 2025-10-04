from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.http_client import HttpClientException
from app.services.broker import AsyncBrokerSingleton
from app.core.logging import get_logger

logger = get_logger(__name__)

RABBIT_DELETE_TYPE = "DELETE"
RABBIT_UPDATE_TYPE = "UPDATE"
RABBIT_CREATE_TYPE = "CREATE"

def list_users(db: Session, limit: int = 50, offset: int = 0) -> Iterable[User]:
    try:
        stmt = select(User).limit(limit).offset(offset)
        return db.execute(stmt).scalars().all()
    except Exception as e:
        raise e


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


async def create_user(db: Session, payload: UserCreate) -> User:
    try:
        existing_user = db.query(User).filter_by(email=payload.email).first()
        if existing_user:
            raise HttpClientException(message="Bad Request", server_message="Email already in use", status_code=400, url="users/")

        if not payload.email or "@" not in payload.email:
            raise HttpClientException(message="Bad Request", server_message="Invalid email", status_code=400, url="users/")

        if not payload.username or len(payload.username) < 3:
            raise HttpClientException(message="Bad Request", server_message="Username too short", status_code=400, url="users/")

        user = User(**payload.model_dump())
        db.add(user)
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_CREATE_TYPE)
        return user
    except HttpClientException as e:
        raise e
    except Exception as e:
        raise e


async def update_user(db: Session, user_id: int, payload: UserUpdate) -> User | None:
    try:
        user = db.get(User, user_id)
        if not user:
            raise HttpClientException(message="Not Found", server_message="User not found", status_code=404, url=f"users/{user_id}")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_UPDATE_TYPE)
        return user
    except HttpClientException as e:
        raise e
    except Exception as e:
        raise e



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
        raise e


async def delete_user(db: Session, user_id: int) -> bool:
    try:
        user = db.get(User, user_id)
        if not user:
            return False
        db.delete(user)
        db.commit()

        # Notifica altri servizi della cancellazione dell'utente
        await update_services(user_id, RABBIT_DELETE_TYPE)

        return True
    except Exception as e:
        raise e

async def update_services(user: User, operation: str):
    try:
        broker_instance = AsyncBrokerSingleton()
        connected = await broker_instance.connect()
        if connected:
            message = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
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
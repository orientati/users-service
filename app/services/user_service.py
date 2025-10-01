from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.http_client import HttpClientException

def list_users(db: Session, limit: int = 50, offset: int = 0) -> Iterable[User]:
    try:
        stmt = select(User).limit(limit).offset(offset)
        return db.execute(stmt).scalars().all()
    except Exception as e:
        raise e


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, payload: UserCreate) -> User:
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
        return user
    except HttpClientException as e:
        raise e
    except Exception as e:
        raise e


def update_user(db: Session, user_id: int, payload: UserUpdate) -> User | None:
    try:
        user = db.get(User, user_id)
        if not user:
            raise HttpClientException(message="Not Found", server_message="User not found", status_code=404, url=f"users/{user_id}")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        return user
    except HttpClientException as e:
        raise e
    except Exception as e:
        raise e

def upsert_user_from_event(db: Session, event_body: str) -> None:
    """
    Esempio di handler per evento broker.
    Atteso un JSON tipo:
      {"type":"user_created","user":{"id":123,"username":"x","email":"y","full_name":"..."}}
    oppure:
      {"type":"user_updated","user":{"id":123,...}}
    """
    data = json.loads(event_body)
    user_data = data.get("user") or {}
    if "id" not in user_data:
        return

    user = db.get(User, user_data["id"])
    if user is None:
        # create with explicit id to allinearsi al servizio autoritativo
        user = User(
            id=user_data["id"],
            username=user_data.get("username", ""),
            email=user_data.get("email", ""),
            name=user_data.get("name", ""),
            surname=user_data.get("surname", "")
        )
        db.add(user)
    else:
        user.username = user_data.get("username", user.username)
        user.email = user_data.get("email", user.email)
        user.name = user_data.get("name", user.name)
        user.surname = user_data.get("surname", user.surname)

    db.commit()


def change_user_password(db: Session, user_id: int, old_password: str, new_password: str) -> bool:
    try:
        user = db.get(User, user_id)
        if not user or user.hashed_password != old_password:
            return False
        user.hashed_password = new_password
        db.commit()
        return True
    except Exception as e:
        raise e


def delete_user(db: Session, user_id: int) -> bool:
    try:
        user = db.get(User, user_id)
        if not user:
            return False
        db.delete(user)
        db.commit()
        return True
    except Exception as e:
        raise e
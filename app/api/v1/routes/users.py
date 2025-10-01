from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.user import UserOut, UserCreate, UserUpdate, ChangePasswordRequest
from app.services.user_service import list_users, get_user, create_user, update_user, change_user_password, delete_user

router = APIRouter()


@router.get("/", response_model=List[UserOut])
def api_list_users(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return list_users(db, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserOut)
def api_get_user(user_id: int, db: Session = Depends(get_db)):
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def api_create_user(payload: UserCreate, db: Session = Depends(get_db)):
    return create_user(db, payload)


@router.patch("/{user_id}", response_model=UserOut)
def api_update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    user = update_user(db, user_id, payload)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def api_change_password(
        payload: ChangePasswordRequest,
        db: Session = Depends(get_db)
):
    success = change_user_password(db, payload.user_id, payload.old_password, payload.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password errata o utente non trovato")


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_user(user_id: int, db: Session = Depends(get_db)):
    success = delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.user import UserOut, UserCreate, UserUpdate, ChangePasswordRequest
from app.services.user_service import list_users, get_user, create_user, update_user, change_user_password, delete_user
from app.services.http_client import HttpClientException
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=List[UserOut])
def api_list_users(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    try:
        return list_users(db, limit=limit, offset=offset)
    except HttpClientException as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"message": e.message, "stack": e.server_message, "url": e.url})
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(status_code=500, detail={"message": "Internal Server Error", "stack": "Swiggity Swoggity, U won't find my log", "url": "users/"})


@router.get("/{user_id}", response_model=UserOut)
def api_get_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = get_user(db, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Not Found", "stack": "User not found", "url": f"users/{user_id}"})
        return user
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail={"message": "Internal Server Error", "stack": "Swiggity Swoggity, U won't find my log", "url": f"users/{user_id}"})

@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def api_create_user(payload: UserCreate, db: Session = Depends(get_db)):
    try:
        return create_user(db, payload)
    except HttpClientException as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"message": e.message, "stack": e.server_message, "url": e.url})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{user_id}", response_model=UserOut)
def api_update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    try:
        user = update_user(db, user_id, payload)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
    except HttpClientException as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"message": e.message, "stack": e.server_message, "url": e.url})
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        raise HTTPException(status_code=500, detail={"message": "Internal Server Error", "stack": "Swiggity Swoggity, U won't find my log", "url": f"users/{user_id}"})


@router.post("/change_password", status_code=status.HTTP_204_NO_CONTENT)
def api_change_password(
        payload: ChangePasswordRequest,
        db: Session = Depends(get_db)
):
    try:
        success = change_user_password(db, payload.user_id, payload.old_password, payload.new_password)
        if not success:
            raise HttpClientException(status_code=400, message="Bad Request", server_message="Old password is incorrect", url=f"users/change-password")
    except HttpClientException as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"message": e.message, "stack": e.server_message, "url": e.url})
    except Exception as e:
        logger.error(f"Error changing password for user {payload.user_id}: {e}")
        raise HTTPException(status_code=500, detail={"message": "Internal Server Error", "stack": "Swiggity Swoggity, U won't find my log", "url": f"users/{payload.user_id}/change-password"})

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_user(user_id: int, db: Session = Depends(get_db)):
    try:
        success = delete_user(db, user_id)
        if not success:
            raise HttpClientException(status_code=404, message="Not Found", server_message="User not found", url=f"users/{user_id}")
    except HttpClientException as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"message": e.message, "stack": e.server_message, "url": e.url})
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail={"message": "Internal Server Error", "stack": "Swiggity Swoggity, U won't find my log", "url": f"users/{user_id}"})
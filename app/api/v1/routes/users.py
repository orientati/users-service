from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status, Body
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.logging import get_logger
from app.schemas.user import UserOut, UserCreate, UserUpdate, ChangePasswordRequest
from app.services.http_client import OrientatiException
from app.services.user_service import list_users, get_user, create_user, update_user, change_user_password, delete_user, \
    verify_email

logger = get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=List[UserOut])
async def api_list_users(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    try:
        return await list_users(db, limit=limit, offset=offset)
    except OrientatiException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "message": e.message,
                "details": e.details,
                "url": e.url
            }
        )


@router.get("/{user_id}", response_model=UserOut)
async def api_get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    try:
        user = await get_user(db, user_id)
        if not user:
            raise OrientatiException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Not Found",
                details={"message": "User not found"},
                url=f"users/{user_id}"
            )
        return user
    except OrientatiException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "message": e.message,
                "details": e.details,
                "url": e.url
            }
        )


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def api_create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        await create_user(db, payload)
        return {"message": "Registration successful. Please check your email to verify your account."}
    except OrientatiException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "message": e.message,
                "details": e.details,
                "url": e.url
            }
        )


@router.patch("/{user_id}", response_model=UserOut)
async def api_update_user(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    try:
        user = await update_user(db, user_id, payload)
        if not user:
            raise OrientatiException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Not Found",
                details={"message": "User not found"},
                url=f"users/{user_id}"
            )
        return user
    except OrientatiException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "message": e.message,
                "details": e.details,
                "url": e.url
            }
        )


@router.post("/change_password", status_code=status.HTTP_204_NO_CONTENT)
async def api_change_password(
        payload: ChangePasswordRequest,
        db: AsyncSession = Depends(get_db)
):
    try:
        success = await change_user_password(db, payload.user_id, payload.old_password, payload.new_password)
        if not success:
            raise OrientatiException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Bad Request",
                details={"message": "Password change failed"},
                url="users/change_password"
            )
    except OrientatiException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "message": e.message,
                "details": e.details,
                "url": e.url
            }
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    try:
        success = await delete_user(db, user_id)
        if not success:
            raise OrientatiException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Not Found",
                details={"message": "User not found"},
                url=f"users/{user_id}"
            )
    except OrientatiException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "message": e.message,
                "details": e.details,
                "url": e.url
            }
        )


@router.post("/verify_email", status_code=status.HTTP_204_NO_CONTENT)
async def api_verify_email(token: str = Body(..., embed=True), db: AsyncSession = Depends(get_db)):
    try:
        await verify_email(token, db)
    except OrientatiException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "message": e.message,
                "details": e.details,
                "url": e.url
            }
        )

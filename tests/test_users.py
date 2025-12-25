import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate
from app.schemas.user import UserUpdate
from app.services.user_service import create_user, get_user, list_users
from app.services.user_service import update_user
from app.services.http_client import OrientatiException


@pytest.mark.asyncio
async def test_create_user_success(db_session):
    payload = UserCreate(
        hashed_password="admin",
        email="admin@gaga.com",
        name="Admin",
        surname="User"
    )
    user = await create_user(db_session, payload)
    assert user.id is not None
    assert user.email == "admin@gaga.com"
    assert user.name == "Admin"

    fetched = await get_user(db_session, user.id)
    assert fetched.email == "admin@gaga.com"


@pytest.mark.asyncio
async def test_create_user_multiple(db_session):
    # Creazione di più utenti
    users_data = [
        {"hashed_password": "pass1", "email": "user1@gaga.com", "name": "U1", "surname": "S1"},
        {"hashed_password": "pass2", "email": "user2@gaga.com", "name": "U2", "surname": "S2"},
        {"hashed_password": "pass3", "email": "user3@gaga.com", "name": "U3", "surname": "S3"},
    ]
    for data in users_data:
        payload = UserCreate(**data)
        await create_user(db_session, payload)

    users = await list_users(db_session)
    assert len(users) == 3
    assert users[0].email == "user1@gaga.com"
    assert users[2].email == "user3@gaga.com"


def test_create_user_invalid_email(db_session):
    with pytest.raises(ValidationError):
        UserCreate(
            hashed_password="pass",
            email="not-an-email",
            name="Bad",
            surname="User"
        )


def test_create_user_missing_field(db_session):
    # Pydantic dovrebbe sollevare errore se manca un campo obbligatorio
    with pytest.raises(ValidationError):
        UserCreate(
            hashed_password="pass",
            email="inc@gaga.com",
            name="Incomplete"
            # manca 'surname'
        )


@pytest.mark.asyncio
async def test_create_user_duplicate_email(db_session):
    payload = UserCreate(
        hashed_password="pass",
        email="dup@gaga.com",
        name="Dup",
        surname="One"
    )
    await create_user(db_session, payload)

    payload2 = UserCreate(
        hashed_password="pass",
        email="dup@gaga.com",
        name="Dup",
        surname="Two"
    )
    # The service now silently handles duplicates (returns existing user or similar) logic
    # It should NOT raise UserCreateError
    
    user = await create_user(db_session, payload2)
    assert user is not None
    assert user.email == "dup@gaga.com"
    # Ensure name wasn't updated (since we don't update on duplicate create, just maybe resend email)
    assert user.name == "Dup" 



@pytest.mark.asyncio
async def test_update_user_success(db_session):
    # Create user first
    payload = UserCreate(
        hashed_password="admin",
        email="gaga@gaga.com",
        name="gaga",
        surname="gagoso"
    )
    user = await create_user(db_session, payload)

    # Update user
    # Update user - email should NOT be updateable via this payload anymore
    # The schema doesn't have email, so usually pydantic ignores it or errors if we pass it depending on config.
    # Assuming standard behavior, we pass valid fields.
    update_payload = UserUpdate(
        name="superadmin"
    )
    # If we tried to pass email="...", it would be ignored or error. Let's stick to valid usage.
    
    updated = await update_user(db_session, user.id, update_payload)

    assert updated.email == "gaga@gaga.com" # Should remain unchanged
    assert updated.name == "superadmin"
    assert updated.surname == "gagoso"  # unchanged


@pytest.mark.asyncio
async def test_update_user_not_found(db_session):
    update_payload = UserUpdate(name="ghost")
    with pytest.raises(OrientatiException) as exc_info:
        await update_user(db_session, 9999, update_payload)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_users_pagination(db_session):
    # Create multiple users
    # We must ensure emails are unique
    for i in range(5):
        payload = UserCreate(
            hashed_password="pass",
            email=f"user{i}@gaga.com",
            name=f"Name{i}",
            surname=f"Surname{i}"
        )
        await create_user(db_session, payload)

    users = await list_users(db_session, limit=3, offset=0)
    assert len(users) == 3
    assert users[0].email == "user0@gaga.com"

    users_page2 = await list_users(db_session, limit=3, offset=3)
    assert len(users_page2) == 2  # restanti


@pytest.mark.asyncio
async def test_change_password_success(db_session):
    # Crea un utente
    payload = UserCreate(
        hashed_password="oldpass",
        email="pwuser@gaga.com",
        name="Pw",
        surname="User"
    )
    user = await create_user(db_session, payload)

    # Cambia la password
    from app.schemas.user import ChangePasswordRequest
    from app.services.user_service import change_user_password

    req = ChangePasswordRequest(
        user_id=user.id,
        old_password="oldpass",
        new_password="newpass"
    )
    result = await change_user_password(db_session, req.user_id, req.old_password, req.new_password)
    assert result is True


@pytest.mark.asyncio
async def test_change_password_wrong_old_password(db_session):
    payload = UserCreate(
        hashed_password="oldpass2",
        email="pwuser2@gaga.com",
        name="Pw2",
        surname="User2"
    )
    user = await create_user(db_session, payload)

    from app.schemas.user import ChangePasswordRequest
    from app.services.user_service import change_user_password

    req = ChangePasswordRequest(
        user_id=user.id,
        old_password="wrongpass",
        new_password="newpass"
    )
    result = await change_user_password(db_session, req.user_id, req.old_password, req.new_password)
    assert result is False


@pytest.mark.asyncio
async def test_change_password_user_not_found(db_session):
    from app.schemas.user import ChangePasswordRequest
    from app.services.user_service import change_user_password

    req = ChangePasswordRequest(
        user_id=99999,
        old_password="irrelevant",
        new_password="irrelevant"
    )
    result = await change_user_password(db_session, req.user_id, req.old_password, req.new_password)
    assert result is False


@pytest.mark.asyncio
async def test_delete_user_success(db_session):
    # Crea un utente da eliminare
    payload = UserCreate(
        hashed_password="pass",
        email="todelete@gaga.com",
        name="To",
        surname="Delete"
    )
    user = await create_user(db_session, payload)

    from app.services.user_service import delete_user, get_user
    result = await delete_user(db_session, user.id)
    assert result is True
    assert await get_user(db_session, user.id) is None


@pytest.mark.asyncio
async def test_delete_user_not_found(db_session):
    from app.services.user_service import delete_user
    result = await delete_user(db_session, 99999)
    assert result is False

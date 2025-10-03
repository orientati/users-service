import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate
from app.schemas.user import UserUpdate
from app.services.user_service import create_user, get_user, list_users
from app.services.user_service import update_user
from app.services.http_client import HttpClientException


def test_create_user_success(db_session):
    payload = UserCreate(
        username="admin",
        hashed_password="admin",
        email="admin@gaga.com",
        name="Admin",
        surname="User"
    )
    user = create_user(db_session, payload)
    assert user.id is not None
    assert user.username == "admin"
    assert user.email == "admin@gaga.com"

    fetched = get_user(db_session, user.id)
    assert fetched.username == "admin"


def test_create_user_multiple(db_session):
    # Creazione di più utenti
    users_data = [
        {"username": "user1", "hashed_password": "pass1", "email": "user1@gaga.com", "name": "U1", "surname": "S1"},
        {"username": "user2", "hashed_password": "pass2", "email": "user2@gaga.com", "name": "U2", "surname": "S2"},
        {"username": "user3", "hashed_password": "pass3", "email": "user3@gaga.com", "name": "U3", "surname": "S3"},
    ]
    for data in users_data:
        payload = UserCreate(**data)
        create_user(db_session, payload)

    users = list_users(db_session)
    assert len(users) == 3
    assert users[0].username == "user1"
    assert users[2].email == "user3@gaga.com"


def test_create_user_invalid_email(db_session):
    with pytest.raises(ValidationError):
        UserCreate(
            username="baduser",
            hashed_password="pass",
            email="not-an-email",
            name="Bad",
            surname="User"
        )


def test_create_user_missing_field(db_session):
    # Pydantic dovrebbe sollevare errore se manca un campo obbligatorio
    with pytest.raises(ValidationError):
        UserCreate(
            username="incomplete",
            hashed_password="pass",
            email="inc@gaga.com",
            name="Incomplete"
            # manca 'surname'
        )


@pytest.mark.skip(reason="Se il DB ha vincolo UNIQUE su username, questo test verifica il fallimento")
def test_create_user_duplicate_username(db_session):
    payload = UserCreate(
        username="duplicate",
        hashed_password="pass",
        email="dup1@gaga.com",
        name="Dup",
        surname="One"
    )
    create_user(db_session, payload)

    payload2 = UserCreate(
        username="duplicate",
        hashed_password="pass",
        email="dup2@gaga.com",
        name="Dup",
        surname="Two"
    )
    # qui dovrebbe fallire commit DB per violazione UNIQUE
    with pytest.raises(Exception):
        create_user(db_session, payload2)


def test_update_user_success(db_session):
    # Create user first
    payload = UserCreate(
        username="admin",
        hashed_password="admin",
        email="gaga@gaga.com",
        name="gaga",
        surname="gagoso"
    )
    user = create_user(db_session, payload)

    # Update user
    update_payload = UserUpdate(
        username="superadmin",
        email="super@gaga.com"
    )
    updated = update_user(db_session, user.id, update_payload)

    assert updated.username == "superadmin"
    assert updated.email == "super@gaga.com"
    assert updated.name == "gaga"  # unchanged
    assert updated.surname == "gagoso"  # unchanged



def test_update_user_not_found(db_session):
    update_payload = UserUpdate(username="ghost")
    with pytest.raises(HttpClientException) as exc_info:
        update_user(db_session, 9999, update_payload)
    assert exc_info.value.status_code == 404

def test_list_users_pagination(db_session):
    # Create multiple users
    for i in range(5):
        payload = UserCreate(
            username=f"user{i}",
            hashed_password="pass",
            email=f"user{i}@gaga.com",
            name=f"Name{i}",
            surname=f"Surname{i}"
        )
        create_user(db_session, payload)

    users = list_users(db_session, limit=3, offset=0)
    assert len(users) == 3
    assert users[0].username == "user0"

    users_page2 = list_users(db_session, limit=3, offset=3)
    assert len(users_page2) == 2  # restanti


def test_change_password_success(db_session):
    # Crea un utente
    payload = UserCreate(
        username="pwuser",
        hashed_password="oldpass",
        email="pwuser@gaga.com",
        name="Pw",
        surname="User"
    )
    user = create_user(db_session, payload)

    # Cambia la password
    from app.schemas.user import ChangePasswordRequest
    from app.services.user_service import change_user_password

    req = ChangePasswordRequest(
        user_id=user.id,
        old_password="oldpass",
        new_password="newpass"
    )
    result = change_user_password(db_session, req.user_id, req.old_password, req.new_password)
    assert result is True


def test_change_password_wrong_old_password(db_session):
    payload = UserCreate(
        username="pwuser2",
        hashed_password="oldpass2",
        email="pwuser2@gaga.com",
        name="Pw2",
        surname="User2"
    )
    user = create_user(db_session, payload)

    from app.schemas.user import ChangePasswordRequest
    from app.services.user_service import change_user_password

    req = ChangePasswordRequest(
        user_id=user.id,
        old_password="wrongpass",
        new_password="newpass"
    )
    result = change_user_password(db_session, req.user_id, req.old_password, req.new_password)
    assert result is False


def test_change_password_user_not_found(db_session):
    from app.schemas.user import ChangePasswordRequest
    from app.services.user_service import change_user_password

    req = ChangePasswordRequest(
        user_id=99999,
        old_password="irrelevant",
        new_password="irrelevant"
    )
    result = change_user_password(db_session, req.user_id, req.old_password, req.new_password)
    assert result is False


def test_delete_user_success(db_session):
    # Crea un utente da eliminare
    payload = UserCreate(
        username="todelete",
        hashed_password="pass",
        email="todelete@gaga.com",
        name="To",
        surname="Delete"
    )
    user = create_user(db_session, payload)

    from app.services.user_service import delete_user, get_user
    result = delete_user(db_session, user.id)
    assert result is True
    assert get_user(db_session, user.id) is None


def test_delete_user_not_found(db_session):
    from app.services.user_service import delete_user
    result = delete_user(db_session, 99999)
    assert result is False

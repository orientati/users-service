"""Tests for the transactional outbox pattern implementation."""
from __future__ import annotations

import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.outbox import OutboxMessage
from app.services.user_service import create_user, update_user, delete_user
from app.schemas.user import UserCreate, UserUpdate


@pytest.mark.asyncio
async def test_create_user_writes_to_outbox(db_session: AsyncSession):
    """Test that creating a user writes both user and outbox message atomically."""
    # Create user
    payload = UserCreate(
        email="test@example.com",
        name="Test",
        surname="User",
        hashed_password="hashedpass123"
    )
    
    user = await create_user(db_session, payload)
    
    # Verify user was created
    assert user.id is not None
    assert user.email == "test@example.com"
    
    # Verify outbox message was created
    stmt = select(OutboxMessage)
    result = await db_session.execute(stmt)
    outbox_messages = result.scalars().all()
    
    # Should have 2 messages: one for user creation, one for verification email
    assert len(outbox_messages) == 2
    
    # Check user creation message
    user_msg = [m for m in outbox_messages if m.message_type == "CREATE"][0]
    assert user_msg.exchange_name == "users"
    assert user_msg.message_type == "CREATE"
    
    payload_data = json.loads(user_msg.payload)
    assert payload_data["id"] == user.id
    assert payload_data["email"] == user.email
    
    # Check email message
    email_msg = [m for m in outbox_messages if m.message_type == "email_notification"][0]
    assert email_msg.exchange_name == "email"
    assert email_msg.routing_key == "send_email"


@pytest.mark.asyncio
async def test_update_user_writes_to_outbox(db_session: AsyncSession):
    """Test that updating a user writes to outbox."""
    # First create a user
    payload = UserCreate(
        email="update@example.com",
        name="Update",
        surname="Test",
        hashed_password="hashedpass123"
    )
    user = await create_user(db_session, payload)
    user_id = user.id
    
    # Clear outbox
    stmt = select(OutboxMessage)
    result = await db_session.execute(stmt)
    for msg in result.scalars().all():
        await db_session.delete(msg)
    await db_session.commit()
    
    # Update user
    update_payload = UserUpdate(name="UpdatedName")
    updated_user = await update_user(db_session, user_id, update_payload)
    
    assert updated_user.name == "UpdatedName"
    
    # Verify outbox message
    stmt = select(OutboxMessage).where(OutboxMessage.message_type == "UPDATE")
    result = await db_session.execute(stmt)
    outbox_message = result.scalars().first()
    
    assert outbox_message is not None
    assert outbox_message.exchange_name == "users"
    
    payload_data = json.loads(outbox_message.payload)
    assert payload_data["name"] == "UpdatedName"


@pytest.mark.asyncio
async def test_delete_user_writes_to_outbox(db_session: AsyncSession):
    """Test that deleting a user writes to outbox."""
    # Create user
    payload = UserCreate(
        email="delete@example.com",
        name="Delete",
        surname="Test",
        hashed_password="hashedpass123"
    )
    user = await create_user(db_session, payload)
    user_id = user.id
    
    # Clear outbox
    stmt = select(OutboxMessage)
    result = await db_session.execute(stmt)
    for msg in result.scalars().all():
        await db_session.delete(msg)
    await db_session.commit()
    
    # Delete user
    success = await delete_user(db_session, user_id)
    assert success is True
    
    # Verify user is deleted
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    assert result.scalars().first() is None
    
    # Verify outbox message
    stmt = select(OutboxMessage).where(OutboxMessage.message_type == "DELETE")
    result = await db_session.execute(stmt)
    outbox_message = result.scalars().first()
    
    assert outbox_message is not None
    assert outbox_message.exchange_name == "users"
    
    payload_data = json.loads(outbox_message.payload)
    assert payload_data["id"] == user_id


@pytest.mark.asyncio
async def test_outbox_message_model(db_session: AsyncSession):
    """Test that OutboxMessage model works correctly."""
    outbox_msg = OutboxMessage(
        exchange_name="test_exchange",
        message_type="TEST_TYPE",
        routing_key="test.routing",
        payload=json.dumps({"test": "data"})
    )
    
    db_session.add(outbox_msg)
    await db_session.commit()
    await db_session.refresh(outbox_msg)
    
    assert outbox_msg.id is not None
    assert outbox_msg.attempts == 0
    assert outbox_msg.last_error is None
    assert outbox_msg.created_at is not None
    
    # Test updating attempts
    outbox_msg.attempts += 1
    outbox_msg.last_error = "Test error"
    await db_session.commit()
    await db_session.refresh(outbox_msg)
    
    assert outbox_msg.attempts == 1
    assert outbox_msg.last_error == "Test error"


@pytest.mark.asyncio
async def test_existing_user_resend_email_writes_to_outbox(db_session: AsyncSession):
    """Test that resending verification email to existing user writes to outbox."""
    # Create unverified user
    payload = UserCreate(
        email="existing@example.com",
        name="Existing",
        surname="User",
        hashed_password="hashedpass123"
    )
    user = await create_user(db_session, payload)
    
    # Clear outbox
    stmt = select(OutboxMessage)
    result = await db_session.execute(stmt)
    for msg in result.scalars().all():
        await db_session.delete(msg)
    await db_session.commit()
    
    # Try to "create" the same user again (should trigger resend)
    same_user = await create_user(db_session, payload)
    
    assert same_user.id == user.id
    
    # Should have new email message in outbox
    stmt = select(OutboxMessage).where(OutboxMessage.message_type == "email_notification")
    result = await db_session.execute(stmt)
    outbox_message = result.scalars().first()
    
    assert outbox_message is not None
    assert outbox_message.exchange_name == "email"

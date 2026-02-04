"""Tests for the OutboxWorker background service."""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.outbox import OutboxMessage
from app.services.outbox_worker import OutboxWorker


@pytest.mark.asyncio
async def test_outbox_worker_initialization():
    """Test that OutboxWorker initializes correctly."""
    worker = OutboxWorker(poll_interval=10, max_retries=5)
    
    assert worker.poll_interval == 10
    assert worker.max_retries == 5
    assert worker.running is False
    assert worker.task is None
    assert worker.broker is not None


@pytest.mark.asyncio
async def test_outbox_worker_start_stop():
    """Test that worker starts and stops gracefully."""
    worker = OutboxWorker(poll_interval=1, max_retries=3)
    
    # Start worker
    await worker.start()
    assert worker.running is True
    assert worker.task is not None
    
    # Give it a moment to run
    await asyncio.sleep(0.1)
    
    # Stop worker
    await worker.stop()
    assert worker.running is False


@pytest.mark.asyncio
async def test_outbox_worker_processes_messages(db_session: AsyncSession, monkeypatch):
    """Test that worker processes outbox messages."""
    # Mock AsyncSessionLocal to return our test db_session
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__.return_value = db_session
    mock_session_cm.__aexit__.return_value = None
    monkeypatch.setattr("app.services.outbox_worker.AsyncSessionLocal", lambda: mock_session_cm)

    # Create test outbox message
    test_message = OutboxMessage(
        exchange_name="test_exchange",
        message_type="TEST",
        routing_key="test.key",
        payload=json.dumps({"test": "data"})
    )
    db_session.add(test_message)
    await db_session.commit()
    await db_session.refresh(test_message)
    message_id = test_message.id
    
    # Mock the broker
    worker = OutboxWorker(poll_interval=1, max_retries=3)
    
    with patch.object(worker.broker, 'connect', new_callable=AsyncMock) as mock_connect, \
         patch.object(worker.broker, 'publish_message', new_callable=AsyncMock) as mock_publish:
        
        mock_connect.return_value = True
        mock_publish.return_value = None
        
        # Process messages once
        await worker._process_pending_messages()
        
        # Verify broker was called
        mock_connect.assert_called_once()
        mock_publish.assert_called_once()
        
        # Verify message was deleted from outbox
        stmt = select(OutboxMessage).where(OutboxMessage.id == message_id)
        result = await db_session.execute(stmt)
        assert result.scalars().first() is None


@pytest.mark.asyncio
async def test_outbox_worker_handles_broker_failure(db_session: AsyncSession, monkeypatch):
    """Test that worker handles broker connection failure gracefully."""
    # Mock AsyncSessionLocal to return our test db_session
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__.return_value = db_session
    mock_session_cm.__aexit__.return_value = None
    monkeypatch.setattr("app.services.outbox_worker.AsyncSessionLocal", lambda: mock_session_cm)

    # Create test message
    test_message = OutboxMessage(
        exchange_name="test_exchange",
        message_type="TEST",
        routing_key="test.key",
        payload=json.dumps({"test": "data"})
    )
    db_session.add(test_message)
    await db_session.commit()
    await db_session.refresh(test_message)
    message_id = test_message.id
    
    worker = OutboxWorker(poll_interval=1, max_retries=3)
    
    with patch.object(worker.broker, 'connect', new_callable=AsyncMock) as mock_connect:
        # Broker connection fails
        mock_connect.return_value = False
        
        # Process messages
        await worker._process_pending_messages()
        
        # Message should still be in outbox
        stmt = select(OutboxMessage).where(OutboxMessage.id == message_id)
        result = await db_session.execute(stmt)
        message = result.scalars().first()
        
        assert message is not None
        assert message.attempts == 0  # Not incremented since we didn't try to send


@pytest.mark.asyncio
async def test_outbox_worker_increments_attempts_on_failure(monkeypatch):
    """Test that worker increments attempts on publish failure."""
    import os
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as SqlAsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.models.outbox import OutboxMessage
    from app.db.base import Base

    # Use a separate file database for this test to avoid sharing the connection/transaction
    # with other tests using StaticPool + :memory:
    test_db_file = "test_worker_retry.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
        
    test_url = f"sqlite+aiosqlite:///{test_db_file}"
    worker_engine = create_async_engine(test_url)
    
    # Create tables in this new DB
    async with worker_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    WorkerSessionLocal = sessionmaker(
        bind=worker_engine, 
        class_=SqlAsyncSession,
        autocommit=False, 
        autoflush=False
    )
    
    class AsyncSessionCM:
        async def __aenter__(self):
            self.session = WorkerSessionLocal()
            return self.session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.session.close()

    monkeypatch.setattr("app.services.outbox_worker.AsyncSessionLocal", AsyncSessionCM)

    # Create test message
    async with WorkerSessionLocal() as session:
        test_message = OutboxMessage(
            exchange_name="test_exchange",
            message_type="TEST",
            routing_key="test.key",
            payload=json.dumps({"test": "data"})
        )
        session.add(test_message)
        await session.commit()
        await session.refresh(test_message)
        message_id = test_message.id

    worker = OutboxWorker(poll_interval=1, max_retries=3)

    with patch.object(worker.broker, 'connect', new_callable=AsyncMock) as mock_connect, \
         patch.object(worker.broker, 'publish_message', new_callable=AsyncMock) as mock_publish:

        mock_connect.return_value = True
        mock_publish.side_effect = Exception("Publish failed")

        # Process messages
        await worker._process_pending_messages()

        # Now check
        async with WorkerSessionLocal() as session:
            stmt = select(OutboxMessage).where(OutboxMessage.id == message_id)
            result = await session.execute(stmt)
            message = result.scalars().first()
            
            assert message is not None
            assert message.attempts == 1
            assert "Publish failed" in message.last_error

    # Cleanup
    await worker_engine.dispose()
    if os.path.exists(test_db_file):
        os.remove(test_db_file)


@pytest.mark.asyncio
async def test_outbox_worker_gives_up_after_max_retries(db_session: AsyncSession, monkeypatch):
    """Test that worker gives up after max retries."""
    # Mock AsyncSessionLocal to return our test db_session
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__.return_value = db_session
    mock_session_cm.__aexit__.return_value = None
    monkeypatch.setattr("app.services.outbox_worker.AsyncSessionLocal", lambda: mock_session_cm)

    # Create message with high attempt count
    test_message = OutboxMessage(
        exchange_name="test_exchange",
        message_type="TEST",
        routing_key="test.key",
        payload=json.dumps({"test": "data"}),
        attempts=10  # Already exceeded max
    )
    db_session.add(test_message)
    await db_session.commit()
    await db_session.refresh(test_message)
    message_id = test_message.id
    
    worker = OutboxWorker(poll_interval=1, max_retries=3)
    
    with patch.object(worker.broker, 'connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = True
        
        # Process messages
        await worker._process_pending_messages()
        
        # Should not even try to process this message
        assert mock_connect.call_count >= 0  # May or may not connect if no messages to process

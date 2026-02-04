from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.outbox import OutboxMessage
from app.services.broker import AsyncBrokerSingleton

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class OutboxWorker:
    """Background worker that processes outbox messages and sends them to RabbitMQ."""
    
    def __init__(self, poll_interval: int = 5, max_retries: int = 10):
        """
        Initialize outbox worker.
        
        Args:
            poll_interval: Seconds to wait between polling the outbox table
            max_retries: Maximum attempts before giving up on a message
        """
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.running = False
        self.task = None
        self.broker = AsyncBrokerSingleton()

    async def start(self):
        """Start the outbox worker background task."""
        if self.running:
            logger.warning("Outbox worker already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._process_loop())
        logger.info(f"Outbox worker started (poll interval: {self.poll_interval}s)")

    async def stop(self):
        """Stop the outbox worker gracefully."""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Outbox worker stopped")

    async def _process_loop(self):
        """Main processing loop that polls and sends messages."""
        while self.running:
            try:
                await self._process_pending_messages()
            except Exception as e:
                logger.error(f"Error in outbox worker loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.poll_interval)

    async def _process_pending_messages(self):
        """Process all pending outbox messages."""
        async with async_session_maker() as session:
            # Get pending messages ordered by creation time
            stmt = select(OutboxMessage).where(
                OutboxMessage.attempts < self.max_retries
            ).order_by(OutboxMessage.created_at)
            
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            if not messages:
                return
            
            logger.info(f"Processing {len(messages)} pending outbox messages")
            
            # Try to connect to broker
            connected = await self.broker.connect(retries=3, delay=2)
            if not connected:
                logger.warning("Cannot connect to RabbitMQ, will retry later")
                return
            
            for message in messages:
                try:
                    await self._send_message(session, message)
                except Exception as e:
                    logger.error(f"Failed to send outbox message {message.id}: {e}", exc_info=True)
                    await self._mark_failed(session, message, str(e))

    async def _send_message(self, session: AsyncSession, message: OutboxMessage):
        """Send a single outbox message to RabbitMQ."""
        try:
            # Parse JSON payload
            payload = json.loads(message.payload)
            
            # Send to RabbitMQ
            await self.broker.publish_message(
                exchange_name=message.exchange_name,
                msg_type=message.message_type,
                data=payload,
                routing_key=message.routing_key
            )
            
            # Delete message from outbox on success
            await session.delete(message)
            await session.commit()
            
            logger.info(
                f"Successfully sent and deleted outbox message {message.id} "
                f"(exchange: {message.exchange_name}, type: {message.message_type})"
            )
            
        except Exception as e:
            await session.rollback()
            raise e

    async def _mark_failed(self, session: AsyncSession, message: OutboxMessage, error: str):
        """Mark a message as failed and increment retry counter."""
        try:
            message.attempts += 1
            message.last_error = error[:1000]  # Truncate error to avoid overflow
            
            if message.attempts >= self.max_retries:
                logger.error(
                    f"Outbox message {message.id} exceeded max retries ({self.max_retries}), "
                    f"giving up. Last error: {error}"
                )
            
            await session.commit()
        except Exception as e:
            logger.error(f"Failed to mark message {message.id} as failed: {e}", exc_info=True)
            await session.rollback()

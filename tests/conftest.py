import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.user import User

# Database in-memory per test
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(
    bind=engine, 
    class_=AsyncSession,
    autocommit=False, 
    autoflush=False
)

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="session")
async def db_engine():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def db_session(db_engine):
    """Session di test isolata per ogni test"""
    connection = await db_engine.connect()
    transaction = await connection.begin()
    
    session = TestingSessionLocal(bind=connection)
    yield session
    
    await session.close()
    await transaction.rollback()
    await connection.close()

@pytest.fixture(autouse=True)
def mock_broker(monkeypatch):
    """Mock broker integration to avoid real connection attempts"""
    
    mock_instance = MagicMock()
    # connect returns True
    mock_instance.connect = AsyncMock(return_value=True)
    mock_instance.publish_message = AsyncMock()
    mock_instance.subscribe = AsyncMock()
    
    # Mock the class to return our instance
    mock_cls = MagicMock(return_value=mock_instance)
    
    monkeypatch.setattr("app.services.broker.AsyncBrokerSingleton", mock_cls)
    # Also patch where it might be imported
    monkeypatch.setattr("app.services.user_service.AsyncBrokerSingleton", mock_cls)


@pytest.fixture
async def client(db_session):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.api.deps import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    # Create client with ASGITransport for direct app testing
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    
    app.dependency_overrides.clear()


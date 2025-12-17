import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, clear_mappers

from app.db.base import Base
from app.models.user import User

# Database in-memory per test
TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(engine):
    """Session di test isolata per ogni test"""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def mock_broker(monkeypatch):
    """Mock broker integration to avoid real connection attempts"""
    from unittest.mock import AsyncMock, MagicMock
    
    mock_instance = MagicMock()
    # connect returns True
    mock_instance.connect = AsyncMock(return_value=True)
    mock_instance.publish_message = AsyncMock()
    mock_instance.subscribe = AsyncMock()
    
    # Mock the class to return our instance
    mock_cls = MagicMock(return_value=mock_instance)
    
    monkeypatch.setattr("app.services.broker.AsyncBrokerSingleton", mock_cls)
    monkeypatch.setattr("app.services.user_service.AsyncBrokerSingleton", mock_cls)


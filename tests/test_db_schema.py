import pytest
from sqlalchemy import inspect

from tests.conftest import apply_migrations, engine


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # Applica le migration prima dei test
    apply_migrations()
    yield

def test_users_table_exists():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("Tabelle presenti:", tables)  # utile per debug
    assert "users" in tables, "La tabella 'users' non esiste nel DB di test"

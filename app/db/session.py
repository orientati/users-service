from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Engine e Session (SQLAlchemy 2.x, modalità sincrona)
engine = create_engine(settings.DATABASE_URL,
   pool_size=1000,  # connessioni permanenti
   max_overflow=2000,  # connessioni extra temporanee
   pool_timeout=5,  # secondi prima di dare errore se pool pieno
   pool_recycle=1800,  # ricrea connessioni vecchie ogni 30 minuti
   pool_pre_ping=True,  # verifica connessione prima di riutilizzarla
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

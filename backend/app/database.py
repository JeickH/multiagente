import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

if POSTGRES_PASSWORD:
    SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
else:
    SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# hide_parameters: una traza de error de SQLAlchemy no debe arrastrar los
# valores del INSERT/UPDATE a los logs (ej. `llm_config` con el secreto Shopify
# cifrado, o el guion completo de un bot). Regla de seguridad #1.
#
# Tamaño del pool por env (#635, modo convención): con los defaults de
# SQLAlchemy (5 + 10) una ráfaga de 20 demos agotó las conexiones. RDS
# db.t3.micro admite ~80 conexiones; el backend corre como una sola task.
def _env_pool(nombre: str, defecto: int) -> int:
    try:
        return max(1, min(int(os.getenv(nombre, "") or defecto), 60))
    except ValueError:
        return defecto


engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    hide_parameters=True,
    pool_size=_env_pool("DB_POOL_SIZE", 5),
    max_overflow=_env_pool("DB_MAX_OVERFLOW", 10),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

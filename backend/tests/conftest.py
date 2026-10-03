import os

# Settings require DATABASE_URL. Tests never connect, so a dummy value is enough.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)

import os

# Fail-fast Settings (app/config/settings.py) requires these to be set before app.main
# is imported. Set safe local-test defaults here so `pytest` works out of the box
# without needing a real .env.local — real integration tests still point at the
# docker-compose Postgres/Redis via these same variable names.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://sijil:sijil@localhost:5432/sijil_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OBJECT_STORAGE_BUCKET", "sijil-test")

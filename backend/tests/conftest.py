import os

# Fail-fast Settings (app/config/settings.py) requires these to be set before app.main
# is imported. Set safe local-test defaults here so `pytest` works out of the box
# without needing a real .env.local — real integration tests still point at the
# docker-compose Postgres/Redis/MinIO via these same variable names. CI overrides
# DATABASE_URL/REDIS_URL/JWT_SECRET/OBJECT_STORAGE_BUCKET via its own env: block, which
# wins over setdefault here.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://sijil:sijil@localhost:5432/sijil_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OBJECT_STORAGE_BUCKET", "sijil-test")
os.environ.setdefault("OBJECT_STORAGE_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("OBJECT_STORAGE_ACCESS_KEY", "minioadmin")
os.environ.setdefault("OBJECT_STORAGE_SECRET_KEY", "minioadmin")
# The real Redis-backed rate limiter (app/middleware/rate_limit.py) is shared across
# every test in the run, all hitting /api/v1/auth/* from the same test-client address —
# the production default (10/minute) would start rejecting registrations partway
# through any real test suite. Effectively unlimited here; production behavior is
# unaffected since this is only a setdefault.
os.environ.setdefault("AUTH_RATE_LIMIT_PER_MINUTE", "100000")

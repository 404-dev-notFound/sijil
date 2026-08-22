from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config.settings import get_settings

settings = get_settings()

# Redis-backed (not in-memory) so the limit is shared across multiple API worker
# processes — an in-memory limiter would let each process grant its own quota,
# silently multiplying the effective rate limit (API SPEC Section 15).
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)

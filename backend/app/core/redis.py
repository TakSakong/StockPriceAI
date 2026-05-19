import redis.asyncio as redis

from app.core.config import settings

# DB 0 (Main Backend & Token Blacklist)
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)  # type: ignore[no-untyped-call]

# DB 1 (ML / Stock cache shared with yfinance ML service)
ml_redis_url = settings.REDIS_URL
if ml_redis_url.endswith("/0"):
    ml_redis_url = ml_redis_url[:-2] + "/1"
elif ml_redis_url.endswith("/0/"):
    ml_redis_url = ml_redis_url[:-3] + "/1"

ml_redis_client = redis.from_url(ml_redis_url, decode_responses=True)  # type: ignore[no-untyped-call]


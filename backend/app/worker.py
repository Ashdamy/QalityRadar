from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("qalitiradar", broker=settings.redis_url, backend=settings.redis_url)

# No tasks defined yet -- Week 2 adds those.

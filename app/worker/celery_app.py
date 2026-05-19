from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['app.worker.tasks']  # Auto-découverte des tâches
)

# Configuration des routes de tâches
# celery_app.conf.task_routes = {
#     "app.worker.tasks.*": {"queue": "main-queue"}
# }

# Configuration des files d'attente
celery_app.conf.task_queues = {
    "main-queue": {
        "exchange": "main-queue",
        "routing_key": "main-queue",
    },
    "low-queue": {
        "exchange": "low-queue",
        "routing_key": "low-queue",
    }
}

# Configuration des tâches périodiques
celery_app.conf.beat_schedule = {
    "delete-expired-images": {
        "task": "app.worker.tasks.delete_expired_images",
        "schedule": 86400.0,  # Une fois par jour
    },
}

# Configuration générale
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True
)
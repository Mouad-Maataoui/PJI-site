"""
Métriques Prometheus pour le monitoring de l'application
"""

from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.multiprocess import MultiProcessCollector
from prometheus_client.registry import REGISTRY
import time
import logging
from typing import Dict, Any
from functools import wraps

logger = logging.getLogger(__name__)

# =============================================================================
# MÉTRIQUES MÉTIER (Business Metrics)
# =============================================================================

# Compteurs pour les paiements
payment_intents_total = Counter(
    'payment_intents_total',
    'Nombre total de PaymentIntents créés',
    ['status']  # success, failed, pending
)

payments_completed_total = Counter(
    'payments_completed_total', 
    'Nombre total de paiements complétés'
)

revenue_total = Counter(
    'revenue_euros_total',
    'Revenus totaux en euros'
)

points_purchased_total = Counter(
    'points_purchased_total',
    'Points totaux achetés'
)

points_spent_total = Counter(
    'points_spent_total',
    'Points totaux dépensés'
)

# Compteurs pour le traitement d'images
images_processed_total = Counter(
    'images_processed_total',
    'Nombre total d\'images traitées',
    ['status', 'model']  # completed, failed + nom du modèle IA
)

image_processing_duration = Histogram(
    'image_processing_duration_seconds',
    'Temps de traitement des images en secondes',
    ['model', 'status'],
    buckets=[1, 5, 10, 30, 60, 120, 300]  # Buckets en secondes
)

# Métriques utilisateurs
users_total = Gauge(
    'users_total',
    'Nombre total d\'utilisateurs'
)

active_users_24h = Gauge(
    'active_users_24h',
    'Utilisateurs actifs dans les dernières 24h'
)

# =============================================================================
# MÉTRIQUES TECHNIQUES (Technical Metrics)
# =============================================================================

# Requêtes HTTP
http_requests_total = Counter(
    'http_requests_total',
    'Nombre total de requêtes HTTP',
    ['method', 'endpoint', 'status_code']
)

http_request_duration = Histogram(
    'http_request_duration_seconds',
    'Durée des requêtes HTTP en secondes',
    ['method', 'endpoint'],
    buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)

# Base de données
db_connections_active = Gauge(
    'db_connections_active',
    'Connexions actives à la base de données'
)

db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Durée des requêtes de base de données',
    ['operation'],  # select, insert, update, delete
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2]
)

# Celery/Redis
celery_tasks_total = Counter(
    'celery_tasks_total',
    'Nombre total de tâches Celery',
    ['task_name', 'status']  # pending, success, failure, retry
)

redis_connections_total = Gauge(
    'redis_connections_total',
    'Connexions Redis actives'
)

# Stockage
storage_uploads_total = Counter(
    'storage_uploads_total',
    'Fichiers uploadés vers le stockage cloud',
    ['storage_type', 'status']  # aws_s3, cloudflare_r2 + success/failed
)

storage_size_bytes = Gauge(
    'storage_size_bytes',
    'Taille totale du stockage en bytes',
    ['storage_type']
)

# =============================================================================
# MÉTRIQUES SYSTÈME
# =============================================================================

# Info sur l'application
app_info = Info(
    'app_info',
    'Informations sur l\'application'
)

# Santé de l'application
app_health = Gauge(
    'app_health',
    'État de santé de l\'application (1=sain, 0=problème)'
)

# =============================================================================
# DÉCORATEURS POUR L'INSTRUMENTATION AUTOMATIQUE
# =============================================================================

def monitor_endpoint(endpoint_name: str = None):
    """Décorateur pour monitorer automatiquement les endpoints"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            method = "POST"  # Vous pouvez l'extraire de la requête
            endpoint = endpoint_name or func.__name__
            
            try:
                result = await func(*args, **kwargs)
                status_code = "200"
                http_requests_total.labels(
                    method=method, 
                    endpoint=endpoint, 
                    status_code=status_code
                ).inc()
                
                return result
                
            except Exception as e:
                status_code = "500"
                http_requests_total.labels(
                    method=method, 
                    endpoint=endpoint, 
                    status_code=status_code
                ).inc()
                raise
                
            finally:
                duration = time.time() - start_time
                http_request_duration.labels(
                    method=method, 
                    endpoint=endpoint
                ).observe(duration)
                
        return wrapper
    return decorator

def monitor_db_operation(operation: str):
    """Décorateur pour monitorer les opérations de base de données"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                db_query_duration.labels(operation=operation).observe(duration)
                
        return wrapper
    return decorator

# =============================================================================
# FONCTIONS D'AIDE POUR L'INSTRUMENTATION
# =============================================================================

class MetricsCollector:
    """Classe utilitaire pour collecter des métriques facilement"""
    
    @staticmethod
    def record_payment_intent(status: str):
        """Enregistre la création d'un PaymentIntent"""
        payment_intents_total.labels(status=status).inc()
    
    @staticmethod
    def record_payment_completed(amount_euros: float, points: int):
        """Enregistre un paiement complété"""
        payments_completed_total.inc()
        revenue_total.inc(amount_euros)
        points_purchased_total.inc(points)
    
    @staticmethod
    def record_points_spent(points: int):
        """Enregistre des points dépensés"""
        points_spent_total.inc(points)
    
    @staticmethod
    def record_image_processing_start(model_name: str):
        """Démarre le chronométrage du traitement d'image"""
        return time.time()
    
    @staticmethod
    def record_image_processing_end(start_time: float, model_name: str, status: str):
        """Termine le chronométrage du traitement d'image"""
        duration = time.time() - start_time
        images_processed_total.labels(status=status, model=model_name).inc()
        image_processing_duration.labels(model=model_name, status=status).observe(duration)
    
    @staticmethod
    def record_celery_task(task_name: str, status: str):
        """Enregistre l'exécution d'une tâche Celery"""
        celery_tasks_total.labels(task_name=task_name, status=status).inc()
    
    @staticmethod
    def record_storage_upload(storage_type: str, status: str, size_bytes: int = 0):
        """Enregistre un upload vers le stockage"""
        storage_uploads_total.labels(storage_type=storage_type, status=status).inc()
        if status == "success" and size_bytes > 0:
            storage_size_bytes.labels(storage_type=storage_type).inc(size_bytes)
    
    @staticmethod
    def update_user_counts(total_users: int, active_24h: int):
        """Met à jour les compteurs d'utilisateurs"""
        users_total.set(total_users)
        active_users_24h.set(active_24h)
    
    @staticmethod
    def set_app_health(healthy: bool):
        """Met à jour l'état de santé de l'application"""
        app_health.set(1 if healthy else 0)

# Instance globale
metrics = MetricsCollector()

# =============================================================================
# ENDPOINT POUR EXPOSER LES MÉTRIQUES
# =============================================================================

def get_metrics():
    """Retourne les métriques au format Prometheus"""
    return generate_latest(REGISTRY)

# =============================================================================
# INITIALISATION
# =============================================================================

def init_metrics():
    """Initialise les métriques avec les informations de l'application"""
    from app.core.config import settings
    
    app_info.info({
        'version': '1.0.0',
        'environment': 'development',  # À adapter selon votre config
        'project_name': settings.PROJECT_NAME
    })
    
    # Marquer l'application comme saine au démarrage
    app_health.set(1)
    
    logger.info("📊 Métriques Prometheus initialisées")
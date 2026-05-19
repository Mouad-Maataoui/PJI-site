from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.api.routes import api_router
from app.api.routes import websockets
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.security_headers_middleware import SecurityHeadersMiddleware
from app.middleware.jwt_error_handler_middleware import JWTErrorHandlerMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware

configure_logging()

# Configuration du logger
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Middleware pour la gestion des erreurs JWT (doit être le premier pour intercepter les exceptions)
app.add_middleware(JWTErrorHandlerMiddleware)

# Middleware pour la limitation de débit
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

# Middleware pour la journalisation des requêtes
app.add_middleware(RequestLoggingMiddleware)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware pour les en-têtes de sécurité
app.add_middleware(SecurityHeadersMiddleware)
    

# Événement de démarrage pour vérifier les connexions
@app.on_event("startup")
async def startup_event():
    # Vérifier la connexion à la base de données
    try:
        from app.db.session import engine
        from sqlalchemy import text
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Base de données connectée avec succès")
    except Exception as e:
        logger.error(f"Échec de la connexion à la base de données: {str(e)}")

    # Vérifier la connexion à Redis
    try:
        import redis
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            socket_timeout=5
        )
        if redis_client.ping():
            logger.info("Connexion Redis établie avec succès")
        else:
            logger.error("Échec de la connexion Redis: La commande PING a échoué")
    except Exception as e:
        logger.error(f"Échec de la connexion Redis: {str(e)}")
    
    # Vérifier l'initialisation de Celery
    try:
        from app.worker.celery_app import celery_app
        logger.info("Application Celery initialisée avec succès")
        
        # Vérifier si des workers Celery sont en ligne (optionnel)
        try:
            i = celery_app.control.inspect()
            if i.ping():
                logger.info("Workers Celery connectés")
            else:
                logger.warning("Aucun worker Celery actif détecté")
        except Exception as e:
            logger.warning(f"Impossible de vérifier les workers Celery: {str(e)}")
            
    except Exception as e:
        logger.error(f"Erreur d'initialisation de Celery: {str(e)}")

# Événement d'arrêt
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Arrêt de l'application...")

# Inclusion des routes API
app.include_router(api_router, prefix=settings.API_V1_STR)

app.include_router(websockets.router, prefix=settings.API_V1_STR, tags=["websockets"])


@app.get("/")
def root():
    return {"message": "Bienvenue sur l'API de traitement d'images"}

@app.get(f"{settings.API_V1_STR}/health")
def health_check():
    # Vérifier la santé des services essentiels
    services_status = {
        "api": "ok"
    }
    
    # Vérifier Redis
    try:
        import redis
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            socket_timeout=2
        )
        redis_client.ping()
        services_status["redis"] = "ok"
    except Exception:
        services_status["redis"] = "error"
    
    # Vérifier la base de données
    try:
        from app.db.session import engine
        from sqlalchemy import text
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        services_status["database"] = "ok"
    except Exception:
        services_status["database"] = "error"
    
    return {
        "status": "ok" if all(status == "ok" for status in services_status.values()) else "degraded",
        "services": services_status
    }
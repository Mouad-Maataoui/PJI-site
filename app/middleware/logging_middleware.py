import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Récupérer l'adresse IP du client
        client_ip = request.client.host if request.client else "unknown"
        
        # Journaliser la requête entrante
        logger.info(
            f"Requête entrante: {request.method} {request.url} - Client: {client_ip}"
        )
        
        # Traiter la requête
        response = await call_next(request)
        
        # Calculer le temps de traitement
        process_time = time.time() - start_time
        
        # Journaliser la réponse
        logger.info(
            f"Réponse: {response.status_code} - Temps: {process_time:.4f}s"
        )
        
        return response
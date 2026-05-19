import time
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests=100, window_seconds=60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # IP -> [timestamp1, timestamp2, ...]
    
    async def dispatch(self, request: Request, call_next):
        # Récupérer l'adresse IP du client
        client_ip = request.client.host if request.client else "unknown"
        
        # Obtenir l'heure actuelle
        current_time = time.time()
        
        # Initialiser la liste des requêtes pour cette IP si elle n'existe pas
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        # Supprimer les requêtes trop anciennes
        self.requests[client_ip] = [
            timestamp for timestamp in self.requests[client_ip]
            if current_time - timestamp < self.window_seconds
        ]
        
        # Vérifier si le nombre de requêtes dépasse la limite
        if len(self.requests[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Trop de requêtes, veuillez réessayer plus tard"},
            )
        
        # Ajouter la requête actuelle
        self.requests[client_ip].append(current_time)
        
        # Traiter la requête
        return await call_next(request)
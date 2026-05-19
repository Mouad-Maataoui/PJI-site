import pytest
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit_middleware import RateLimitMiddleware

# Application de test simple
app = FastAPI()

# Créer une instance du middleware que nous pourrons réinitialiser
rate_limit_middleware = RateLimitMiddleware(app, max_requests=3, window_seconds=10)

# Ajouter le middleware à l'application
app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=10)

@app.get("/test")
@pytest.mark.ignore_test
def endpoint():
    return {"message": "This is a test"}

client = TestClient(app)

def test_rate_limit_middleware():
    """Test que le middleware limite le nombre de requêtes"""
    # Faire 3 requêtes qui devraient réussir
    for _ in range(3):
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"message": "This is a test"}
    
    # La 4ème requête devrait être limitée
    response = client.get("/test")
    assert response.status_code == 429
    assert "trop de requêtes" in response.json()["detail"].lower()
    
    # Attendre que la fenêtre de temps expire pour ne pas affecter d'autres tests
    time.sleep(0.1)  # Une petite pause suffit pour les tests
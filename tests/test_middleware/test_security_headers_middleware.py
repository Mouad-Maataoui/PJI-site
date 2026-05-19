import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security_headers_middleware import SecurityHeadersMiddleware

# Application de test simple
app = FastAPI()

# Ajouter le middleware à l'application
app.add_middleware(SecurityHeadersMiddleware)

@app.get("/test")
@pytest.mark.ignore_test
def endpoint():
    return {"message": "This is a test"}

client = TestClient(app)

def test_security_headers_middleware():
    """Test que le middleware ajoute les en-têtes de sécurité"""
    response = client.get("/test")
    
    # Vérifier que la réponse contient les en-têtes de sécurité
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    
    # Vérifier que la réponse est correcte
    assert response.status_code == 200
    assert response.json() == {"message": "This is a test"}
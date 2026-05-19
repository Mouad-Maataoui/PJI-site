import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch
from jose import ExpiredSignatureError, JWTError

from app.middleware.jwt_error_handler_middleware import JWTErrorHandlerMiddleware
from app.core.security import oauth2_scheme

# Application de test simple
app = FastAPI()

# Ajouter le middleware à l'application
app.add_middleware(JWTErrorHandlerMiddleware)

# Endpoint qui simule une erreur de token expiré
@app.get("/expired-token")
def expired_token_endpoint(token: str = Depends(oauth2_scheme)):
    # Simuler une erreur de token expiré
    raise ExpiredSignatureError()

# Endpoint qui simule une erreur de token invalide
@app.get("/invalid-token")
def invalid_token_endpoint(token: str = Depends(oauth2_scheme)):
    # Simuler une erreur de token invalide
    raise JWTError()

client = TestClient(app)

def test_expired_token_handler():
    """Test que le middleware gère correctement les tokens expirés"""
    with patch("app.core.security.oauth2_scheme", side_effect=ExpiredSignatureError()):
        response = client.get("/expired-token", headers={"Authorization": "Bearer invalid_token"})
        
        # Vérifier que la réponse a le bon code d'état
        assert response.status_code == 401
        
        # Vérifier que la réponse contient le bon message d'erreur
        assert response.json() == {"detail": "Token expiré, veuillez vous reconnecter"}
        
        # Vérifier que l'en-tête WWW-Authenticate est présent
        assert response.headers["WWW-Authenticate"] == "Bearer"

def test_invalid_token_handler():
    """Test que le middleware gère correctement les tokens invalides"""
    with patch("app.core.security.oauth2_scheme", side_effect=JWTError()):
        response = client.get("/invalid-token", headers={"Authorization": "Bearer invalid_token"})
        
        # Vérifier que la réponse a le bon code d'état
        assert response.status_code == 401
        
        # Vérifier que la réponse contient le bon message d'erreur
        assert response.json() == {"detail": "Token invalide"}
        
        # Vérifier que l'en-tête WWW-Authenticate est présent
        assert response.headers["WWW-Authenticate"] == "Bearer"
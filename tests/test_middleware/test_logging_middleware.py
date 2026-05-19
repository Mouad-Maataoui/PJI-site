import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.middleware.logging_middleware import RequestLoggingMiddleware

# Application de test simple
app = FastAPI()

# Ajouter le middleware à l'application
app.add_middleware(RequestLoggingMiddleware)

@app.get("/test")
@pytest.mark.ignore_test
def endpoint():
    return {"message": "This is a test"}

client = TestClient(app)

def test_logging_middleware():
    """Test que le middleware de journalisation enregistre les requêtes"""
    with patch("app.middleware.logging_middleware.logger") as mock_logger:
        # Faire une requête
        response = client.get("/test")
        
        # Vérifier que la requête a été enregistrée
        mock_logger.info.assert_called()
        
        # Vérifier que le log contient les informations attendues
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("Requête entrante: GET" in msg for msg in log_calls)
        assert any(f"Réponse: {response.status_code}" in msg for msg in log_calls)
        
        # Vérifier que la réponse est correcte
        assert response.status_code == 200
        assert response.json() == {"message": "This is a test"}
# tests/test_api/test_image_routes.py
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from io import BytesIO

# Import des dépendances
from app.api.routes.images import router
from app.models.image_task import ProcessingStatus

# Créer une application FastAPI de test
app = FastAPI()
app.include_router(router, prefix="/api/images")

@pytest.fixture(scope="function")
def test_client(db_session, temp_image_dir):
    """Fixture pour créer un client de test"""
    # Patcher les dépendances
    with patch("app.api.routes.images.get_db", return_value=db_session), \
         patch("app.api.routes.images.get_current_user", return_value=MagicMock(id=1)):
        
        client = TestClient(app)
        yield client

def test_upload_image(test_client, test_image, mock_celery):
    """Test d'upload d'image"""
    # Mocker le service de traitement d'images
    with patch("app.api.routes.images.ImageProcessingService") as mock_service_class:
        # Configuration des mocks
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.compress_image.return_value = (b"compressed_data", "jpeg")
        mock_service.save_image.side_effect = [
            "/path/to/original/image.jpg",
            "/path/to/compressed/image.jpg"
        ]
        mock_service.run_processing_threads.return_value = "test-celery-task-id"
        
        # Upload d'une image
        response = test_client.post(
            "/api/images/upload",
            files={
                "file": ("test.jpg", BytesIO(test_image), "image/jpeg")
            },
            data={
                "options": json.dumps({"test": "value"})
            }
        )
        
        # Vérifier la réponse
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert data["celery_task_id"] == "test-celery-task-id"
        
        # Vérifier que les méthodes ont été appelées
        mock_service.compress_image.assert_called_once()
        assert mock_service.save_image.call_count == 2
        mock_service.run_processing_threads.assert_called_once()

def test_upload_image_invalid_format(test_client):
    """Test d'upload d'image avec format invalide"""
    response = test_client.post(
        "/api/images/upload",
        files={
            "file": ("test.txt", BytesIO(b"text_content"), "text/plain")
        }
    )
    
    # Vérifier la réponse
    assert response.status_code == 400
    assert "Format non supporté" in response.json()["detail"]

def test_get_user_tasks(test_client, test_image_task):
    """Test de récupération des tâches d'un utilisateur"""
    response = test_client.get("/api/images/tasks")
    
    # Vérifier la réponse
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == test_image_task.id
    assert data[0]["original_filename"] == test_image_task.original_filename
    assert data[0]["status"] == test_image_task.status

def test_get_task_details(test_client, test_image_task):
    """Test de récupération des détails d'une tâche"""
    response = test_client.get(f"/api/images/tasks/{test_image_task.id}")
    
    # Vérifier la réponse
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_image_task.id
    assert data["original_filename"] == test_image_task.original_filename
    assert data["status"] == test_image_task.status

def test_get_task_details_not_found(test_client):
    """Test de récupération d'une tâche inexistante"""
    response = test_client.get("/api/images/tasks/999")
    
    # Vérifier la réponse
    assert response.status_code == 404
    assert "Tâche non trouvée" in response.json()["detail"]

def test_download_processed_image(test_client, test_image_task, temp_image_dir):
    """Test de téléchargement d'une image traitée"""
    # Setup
    processed_path = os.path.join(temp_image_dir, "test_processed.jpg")
    with open(processed_path, "wb") as f:
        f.write(b"test_processed_content")
    
    # Mettre à jour la tâche
    from app.db.repositories.image_repository import ImageRepository
    repo = ImageRepository(test_client.app.dependency_overrides[router.routes[0].endpoint.__closure__[1].cell_contents]["db"])
    repo.update_processed_path(test_image_task.id, processed_path)
    repo.update_status(test_image_task.id, ProcessingStatus.COMPLETED.value)
    
    # Télécharger l'image
    response = test_client.get(f"/api/images/download/{test_image_task.id}")
    
    # Vérifier la réponse
    assert response.status_code == 200
    assert response.content == b"test_processed_content"
    assert "image/" in response.headers["content-type"]

def test_download_processed_image_not_completed(test_client, test_image_task):
    """Test de téléchargement d'une image non traitée"""
    response = test_client.get(f"/api/images/download/{test_image_task.id}")
    
    # Vérifier la réponse
    assert response.status_code == 400
    assert "L'image n'est pas disponible" in response.json()["detail"]

def test_retry_processing(test_client, test_image_task, temp_image_dir, mock_celery):
    """Test de relancement d'un traitement échoué"""
    # Setup
    original_path = test_image_task.original_file_path
    compressed_path = test_image_task.compressed_file_path
    
    # Mettre à jour la tâche comme échouée
    from app.db.repositories.image_repository import ImageRepository
    repo = ImageRepository(test_client.app.dependency_overrides[router.routes[0].endpoint.__closure__[1].cell_contents]["db"])
    repo.update_status(test_image_task.id, ProcessingStatus.FAILED.value, "Test error")
    
    # Mocker le service de traitement d'images
    with patch("app.api.routes.images.ImageProcessingService") as mock_service_class:
        # Configuration des mocks
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.run_processing_threads.return_value = "test-celery-task-id"
        
        # Relancer le traitement
        response = test_client.post(f"/api/images/retry/{test_image_task.id}")
        
        # Vérifier la réponse
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == test_image_task.id
        assert data["status"] == "pending"
        assert data["celery_task_id"] == "test-celery-task-id"
        
        # Vérifier que les méthodes ont été appelées
        mock_service.run_processing_threads.assert_called_once_with(
            task_id=test_image_task.id,
            original_path=original_path,
            compressed_path=compressed_path,
            options=None
        )

def test_retry_processing_not_failed(test_client, test_image_task):
    """Test de relancement d'un traitement non échoué"""
    response = test_client.post(f"/api/images/retry/{test_image_task.id}")
    
    # Vérifier la réponse
    assert response.status_code == 400
    assert "Seules les tâches en échec peuvent être relancées" in response.json()["detail"]
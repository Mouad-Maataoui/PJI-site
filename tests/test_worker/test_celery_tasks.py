# tests/test_worker/test_celery_tasks.py
import os
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta

from app.worker.tasks import process_image_task, delete_expired_images
from app.models.image_task import ProcessingStatus

@pytest.mark.asyncio
async def test_process_image_task_success(db_session, temp_image_dir, mock_thread_manager):
    """Test de traitement d'image avec succès"""
    # Setup
    task_id = 1
    original_path = os.path.join(temp_image_dir, "test_original.jpg")
    compressed_path = os.path.join(temp_image_dir, "test_compressed.jpg")
    processed_path = os.path.join(temp_image_dir, "test_processed.jpg")
    
    # Créer des fichiers factices
    with open(original_path, "wb") as f:
        f.write(b"test_original_content")
    
    with open(compressed_path, "wb") as f:
        f.write(b"test_compressed_content")
    
    with open(processed_path, "wb") as f:
        f.write(b"test_processed_content")
    
    # Configurer les résultats des threads
    thread_results = {
        "save_success": True,
        "process_success": True,
        "processed_path": processed_path,
        "compressed_processed_path": compressed_path
    }
    
    thread_results_phase2 = {
        "delivery_success": True,
        "upload_success": True
    }
    
    # Mocker le comportement du gestionnaire de threads
    def start_thread_side_effect(name, func, *args, **kwargs):
        if name == "save_thread":
            func(compressed_path)
        elif name == "process_thread":
            func(original_path)
        elif name == "client_delivery_thread":
            func(processed_path)
        elif name == "s3_upload_thread":
            func(compressed_path)
    
    mock_thread_manager.start_thread.side_effect = start_thread_side_effect
    mock_thread_manager.wait_all.side_effect = [thread_results, thread_results_phase2]
    
    # Mocker les dépendances
    with patch("app.worker.tasks.SessionLocal", return_value=db_session), \
         patch("app.worker.tasks.ThreadManager", return_value=mock_thread_manager), \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove:
        
        # Exécuter la tâche
        result = process_image_task(task_id, original_path, compressed_path, {"test": "value"})
        
        # Vérifier le résultat
        assert result["status"] == "success"
        assert "message" in result
        assert result["task_id"] == task_id
        
        # Vérifier que les threads ont été démarrés
        assert mock_thread_manager.start_thread.call_count == 4
        
        # Vérifier que les fichiers temporaires ont été supprimés
        assert mock_remove.call_count == 2
        mock_remove.assert_has_calls([
            call(original_path),
            call(processed_path)
        ], any_order=True)

def test_process_image_task_success(db_session, temp_image_dir, mock_thread_manager):
    """Test de traitement d'image avec erreur de traitement"""
    # Setup
    task_id = 1
    original_path = os.path.join(temp_image_dir, "test_original.jpg")
    compressed_path = os.path.join(temp_image_dir, "test_compressed.jpg")
    
    # Créer des fichiers factices
    with open(original_path, "wb") as f:
        f.write(b"test_original_content")
    
    with open(compressed_path, "wb") as f:
        f.write(b"test_compressed_content")
    
    # Configurer une erreur de traitement
    thread_results = {
        "save_success": True,
        "process_success": False,
        "process_error": "Test processing error"
    }
    
# Mocker le comportement du gestionnaire de threads
def start_thread_side_effect(name, func, *args, **kwargs):
    # Au lieu d'appeler la fonction réelle qui contient asyncio.run(),
    # simule simplement le comportement attendu
    if name == "save_thread":
        func(compressed_path)
    elif name == "process_thread":
        # Ne pas exécuter la fonction qui contient asyncio.run()
        # Utilisez directement les résultats simulés
        pass  # La fonction n'est pas appelée, mais les résultats sont définis dans thread_results
    elif name == "client_delivery_thread":
        func(processed_path)
    elif name == "s3_upload_thread":
        func(compressed_path)

def test_delete_expired_images(db_session, temp_image_dir):
    """Test de suppression des images expirées"""
    # Setup
    now = datetime.utcnow()
    
    # Créer des fichiers factices
    expired_original = os.path.join(temp_image_dir, "expired_original.jpg")
    expired_compressed = os.path.join(temp_image_dir, "expired_compressed.jpg")
    expired_processed = os.path.join(temp_image_dir, "expired_processed.jpg")
    
    with open(expired_original, "wb") as f:
        f.write(b"expired_original_content")
    
    with open(expired_compressed, "wb") as f:
        f.write(b"expired_compressed_content")
    
    with open(expired_processed, "wb") as f:
        f.write(b"expired_processed_content")
    
    # Créer une tâche expirée
    from app.models.image_task import ImageTask
    expired_task = ImageTask(
        id=2,
        user_id=1,
        original_filename="expired.jpg",
        original_file_path=expired_original,
        compressed_file_path=expired_compressed,
        processed_file_path=expired_processed,
        status=ProcessingStatus.COMPLETED.value,
        expire_at=now - timedelta(days=1)
    )
    
    db_session.add(expired_task)
    db_session.commit()
    
    # Mocker les dépendances
    with patch("app.worker.tasks.SessionLocal", return_value=db_session), \
         patch("datetime.datetime") as mock_datetime:
        
        # Configurer le mock de datetime
        mock_datetime.utcnow.return_value = now
        
        # Exécuter la tâche
        result = delete_expired_images()
        
        # Vérifier le résultat
        assert result["status"] == "success"
        assert result["deleted_count"] == 1
        
        # Vérifier que les fichiers ont été supprimés
        assert not os.path.exists(expired_original)
        assert not os.path.exists(expired_compressed)
        assert not os.path.exists(expired_processed)
        
        # Vérifier que la tâche a été supprimée de la base de données
        from app.db.repositories.image_repository import ImageRepository
        repo = ImageRepository(db_session)
        assert repo.get_task(2) is None
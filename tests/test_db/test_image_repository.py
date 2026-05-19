import pytest
from datetime import datetime, timedelta

from app.db.repositories.image_repository import ImageRepository
from app.models.image_task import ProcessingStatus, ImageTask

def test_create_task(db_session, temp_image_dir):
    """Test de création d'une tâche d'image"""
    repo = ImageRepository(db_session)
    
    # Chemins de test
    original_path = f"{temp_image_dir}/test_original.jpg"
    compressed_path = f"{temp_image_dir}/test_compressed.jpg"
    
    # Créer une tâche
    task_id = repo.create_task(
        user_id=1,
        original_filename="test.jpg",
        original_file_path=original_path,
        compressed_file_path=compressed_path
    )
    
    # Vérifier que la tâche a été créée
    assert task_id is not None
    assert task_id > 0
    
    # Récupérer la tâche
    task = repo.get_task(task_id)
    
    # Vérifier les propriétés
    assert task.user_id == 1
    assert task.original_filename == "test.jpg"
    assert task.original_file_path == original_path
    assert task.compressed_file_path == compressed_path
    assert task.status == ProcessingStatus.PENDING.value
    assert task.expire_at is not None

def test_get_task(db_session, test_image_task):
    """Test de récupération d'une tâche par ID"""
    repo = ImageRepository(db_session)
    
    # Récupérer la tâche
    task = repo.get_task(test_image_task.id)
    
    # Vérifier que la tâche a été récupérée
    assert task is not None
    assert task.id == test_image_task.id
    assert task.user_id == test_image_task.user_id
    assert task.original_filename == test_image_task.original_filename

def test_get_user_tasks(db_session, test_image_task):
    """Test de récupération des tâches d'un utilisateur"""
    repo = ImageRepository(db_session)
    
    # Récupérer les tâches de l'utilisateur
    tasks = repo.get_user_tasks(test_image_task.user_id)
    
    # Vérifier que la tâche est dans la liste
    assert len(tasks) == 1
    assert tasks[0].id == test_image_task.id

def test_update_status(db_session, test_image_task):
    """Test de mise à jour du statut d'une tâche"""
    repo = ImageRepository(db_session)
    
    # Statut initial
    assert test_image_task.status == ProcessingStatus.PENDING.value
    
    # Mettre à jour le statut
    updated_task = repo.update_status(
        task_id=test_image_task.id,
        status=ProcessingStatus.PROCESSING.value,
        error_message="Test error"
    )
    
    # Vérifier que le statut a été mis à jour
    assert updated_task.status == ProcessingStatus.PROCESSING.value
    assert updated_task.error_message == "Test error"
    
    # Vérifier que la mise à jour est persistante
    task = repo.get_task(test_image_task.id)
    assert task.status == ProcessingStatus.PROCESSING.value
    assert task.error_message == "Test error"

def test_update_processed_path(db_session, test_image_task, temp_image_dir):
    """Test de mise à jour du chemin de l'image traitée"""
    repo = ImageRepository(db_session)
    
    # Chemin de test
    processed_path = f"{temp_image_dir}/test_processed.jpg"
    
    # Mettre à jour le chemin
    updated_task = repo.update_processed_path(
        task_id=test_image_task.id,
        processed_file_path=processed_path
    )
    
    # Vérifier que le chemin a été mis à jour
    assert updated_task.processed_file_path == processed_path
    
    # Vérifier que la mise à jour est persistante
    task = repo.get_task(test_image_task.id)
    assert task.processed_file_path == processed_path

def test_update_s3_path(db_session, test_image_task):
    """Test de mise à jour du chemin S3"""
    repo = ImageRepository(db_session)
    
    # URL S3 de test
    s3_path = "https://example-bucket.s3.amazonaws.com/test.jpg"
    
    # Mettre à jour le chemin S3
    updated_task = repo.update_s3_path(
        task_id=test_image_task.id,
        s3_path=s3_path
    )
    
    # Vérifier que le chemin S3 a été mis à jour
    assert updated_task.s3_path == s3_path
    
    # Vérifier que la mise à jour est persistante
    task = repo.get_task(test_image_task.id)
    assert task.s3_path == s3_path

def test_get_expired_images(db_session):
    """Test de récupération des images expirées"""
    repo = ImageRepository(db_session)
    
    # Créer des tâches avec différentes dates d'expiration
    now = datetime.utcnow()
    
    # Tâche expirée
    expired_task = ImageTask(
        user_id=1,
        original_filename="expired.jpg",
        original_file_path="/test/expired.jpg",
        status=ProcessingStatus.COMPLETED.value,
        expire_at=now - timedelta(days=1)
    )
    
    # Tâche active
    active_task = ImageTask(
        user_id=1,
        original_filename="active.jpg",
        original_file_path="/test/active.jpg",
        status=ProcessingStatus.COMPLETED.value,
        expire_at=now + timedelta(days=1)
    )
    
    db_session.add(expired_task)
    db_session.add(active_task)
    db_session.commit()
    
    # Récupérer les images expirées
    expired_images = repo.get_expired_images(now)
    
    # Vérifier que seule la tâche expirée est retournée
    assert len(expired_images) == 1
    assert expired_images[0].original_filename == "expired.jpg"

def test_delete_task(db_session, test_image_task):
    """Test de suppression d'une tâche"""
    repo = ImageRepository(db_session)
    
    # Supprimer la tâche
    result = repo.delete_task(test_image_task.id)
    
    # Vérifier que la suppression a réussi
    assert result is True
    
    # Vérifier que la tâche a été supprimée
    task = repo.get_task(test_image_task.id)
    assert task is None
# tests/conftest.py
import os
import pytest
import shutil
import tempfile
from PIL import Image
import io
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Import des modèles et dépendances
from app.db.base import Base
from app.models.user import User
from app.models.image_task import ImageTask, ProcessingStatus
from app.core.config import settings
from app.worker.thread_manager import ThreadManager

# Créer une base de données SQLite en mémoire pour les tests
@pytest.fixture(scope="function")
def db_session():
    """Fixture pour créer une session de base de données temporaire pour les tests"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    
    # Ajouter des données de test
    test_user = User(
        id=1,
        email="test@example.com",
        hashed_password="hashed_password",
        username="Test_User"
    )
    session.add(test_user)
    session.commit()
    
    yield session
    
    # Nettoyage
    session.close()
    Base.metadata.drop_all(engine)

# Créer un répertoire temporaire pour simuler le stockage d'images
@pytest.fixture(scope="function")
def temp_image_dir():
    """Fixture pour créer un répertoire temporaire pour les tests d'images"""
    test_dir = tempfile.mkdtemp()
    
    # Créer les sous-répertoires nécessaires
    os.makedirs(os.path.join(test_dir, "uploads", "original"), exist_ok=True)
    os.makedirs(os.path.join(test_dir, "uploads", "compressed"), exist_ok=True)
    os.makedirs(os.path.join(test_dir, "processed"), exist_ok=True)
    os.makedirs(os.path.join(test_dir, "compressed"), exist_ok=True)
    
    # Patcher le paramètre IMAGE_STORAGE_PATH pour les tests
    original_storage_path = settings.IMAGE_STORAGE_PATH
    settings.IMAGE_STORAGE_PATH = test_dir
    
    yield test_dir
    
    # Restaurer la configuration d'origine
    settings.IMAGE_STORAGE_PATH = original_storage_path
    
    # Nettoyer le répertoire temporaire
    shutil.rmtree(test_dir)

# Créer une image de test
@pytest.fixture(scope="function")
def test_image():
    """Fixture pour créer une image de test"""
    image = Image.new('RGB', (100, 100), color='red')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    buffer.seek(0)
    
    return buffer.getvalue()

# Créer une instance de test ImageTask
@pytest.fixture(scope="function")
def test_image_task(db_session, temp_image_dir):
    """Fixture pour créer une tâche d'image de test"""
    # Créer des chemins de test
    original_path = os.path.join(temp_image_dir, "uploads", "original", "test_original.jpg")
    compressed_path = os.path.join(temp_image_dir, "uploads", "compressed", "test_compressed.jpg")
    
    # Créer des fichiers factices
    with open(original_path, "wb") as f:
        f.write(b"test_original_content")
    
    with open(compressed_path, "wb") as f:
        f.write(b"test_compressed_content")
    
    # Créer une tâche d'image
    task = ImageTask(
        id=1,
        user_id=1,
        original_filename="test.jpg",
        original_file_path=original_path,
        compressed_file_path=compressed_path,
        status=ProcessingStatus.PENDING.value,
        expire_at=datetime.utcnow() + timedelta(days=7)
    )
    
    db_session.add(task)
    db_session.commit()
    
    return task

# Mock pour Celery
@pytest.fixture(scope="function")
def mock_celery():
    """Fixture pour mocker Celery"""
    with patch("app.worker.tasks.celery_app") as mock_celery:
        mock_task = MagicMock()
        mock_task.id = "test-celery-task-id"
        mock_celery.send_task.return_value = mock_task
        mock_celery.AsyncResult.return_value = mock_task
        yield mock_celery

# Mock pour Thread Manager
@pytest.fixture(scope="function")
def mock_thread_manager():
    """Fixture pour mocker ThreadManager"""
    with patch("app.worker.thread_manager.ThreadManager") as mock_tm:
        instance = MagicMock()
        mock_tm.return_value = instance
        instance.wait_all.return_value = {}
        yield instance
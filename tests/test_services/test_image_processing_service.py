# tests/test_services/test_image_processing_service.py
import os
import pytest
import io
from PIL import Image
from unittest.mock import patch, MagicMock

from app.services.image_processing_service import ImageProcessingService

@pytest.mark.asyncio
async def test_compress_image(test_image):
    """Test de compression d'image"""
    service = ImageProcessingService()
    
    # Compresser l'image
    compressed_bytes, format = await service.compress_image(test_image)
    
    # Vérifier que l'image compressée est plus petite que l'originale
    assert len(compressed_bytes) < len(test_image)
    assert format.lower() in ["jpeg", "jpg"]
    
    # Vérifier que l'image compressée est valide
    Image.open(io.BytesIO(compressed_bytes))

@pytest.mark.asyncio
async def test_compress_and_save_image(temp_image_dir):
    """Test de compression et sauvegarde d'une image existante"""
    service = ImageProcessingService()
    
    # Créer une image de test
    image = Image.new('RGB', (100, 100), color='red')
    test_path = os.path.join(temp_image_dir, "test_image.jpg")
    image.save(test_path)
    
    # Compresser et sauvegarder l'image
    output_path = await service.compress_and_save_image(test_path, "test_compressed.jpg")
    
    # Vérifier que le fichier de sortie existe
    assert os.path.exists(output_path)
    
    # Vérifier que le fichier de sortie est plus petit que l'original
    assert os.path.getsize(output_path) < os.path.getsize(test_path)

@pytest.mark.asyncio
async def test_process_mock(temp_image_dir):
    """Test du traitement mock d'une image"""
    service = ImageProcessingService()
    
    # Créer une image de test
    image = Image.new('RGB', (100, 100), color='red')
    test_path = os.path.join(temp_image_dir, "test_image.jpg")
    image.save(test_path)
    
    # Traiter l'image
    processed_path = await service.process_mock(test_path)
    
    # Vérifier que le fichier de sortie existe
    assert os.path.exists(processed_path)
    
    # Vérifier que le chemin de sortie est différent de l'original
    assert processed_path != test_path
    
    # Vérifier que les images sont différentes en les ouvrant
    original_img = Image.open(test_path)
    processed_img = Image.open(processed_path)
    
    # Vérifier au moins un pixel pour s'assurer que l'image a été modifiée
    # (Comparer les valeurs de pixels au centre de l'image)
    width, height = original_img.size
    center_x, center_y = width // 2, height // 2
    
    # Obtenir la couleur du pixel central
    original_pixel = original_img.getpixel((center_x, center_y))
    processed_pixel = processed_img.getpixel((center_x, center_y))
    
    # L'image a été modifiée si les pixels sont différents
    assert original_pixel != processed_pixel
    
@pytest.mark.asyncio
async def test_decompress_for_download(temp_image_dir):
    """Test de décompression d'une image pour téléchargement"""
    service = ImageProcessingService()
    
    # Créer un fichier de test
    test_content = b"test_compressed_content"
    test_path = os.path.join(temp_image_dir, "test_compressed.jpg")
    with open(test_path, "wb") as f:
        f.write(test_content)
    
    # Décompresser l'image
    decompressed_bytes = await service.decompress_for_download(test_path)
    
    # Vérifier que le contenu est le même
    assert decompressed_bytes == test_content

def test_run_processing_threads(db_session, temp_image_dir, mock_celery):
    """Test du lancement des threads de traitement"""
    # Setup
    service = ImageProcessingService(db_session)
    original_path = os.path.join(temp_image_dir, "test_original.jpg")
    compressed_path = os.path.join(temp_image_dir, "test_compressed.jpg")
    
    # Créer des fichiers factices
    with open(original_path, "wb") as f:
        f.write(b"test_original_content")
    
    with open(compressed_path, "wb") as f:
        f.write(b"test_compressed_content")
    
    # Mocker la tâche Celery
    with patch("app.worker.tasks.process_image_task") as mock_task:
        mock_async_result = MagicMock()
        mock_async_result.id = "test-celery-task-id"
        mock_task.delay.return_value = mock_async_result
        
        # Exécuter le test
        task_id = service.run_processing_threads(
            task_id=1,
            original_path=original_path,
            compressed_path=compressed_path,
            options={"test": "value"}
        )
        
        # Vérifier que la tâche Celery a été appelée avec les bons paramètres
        mock_task.delay.assert_called_once_with(
            1, original_path, compressed_path, {"test": "value"}
        )
        
        # Vérifier que l'ID de tâche est correct
        assert task_id == "test-celery-task-id"

def test_save_image(temp_image_dir):
    """Test de sauvegarde d'une image"""
    service = ImageProcessingService()
    
    # Données de test
    test_bytes = b"test_image_content"
    test_filename = "test_image.jpg"
    
    # Sauvegarder l'image
    file_path = service.save_image(test_bytes, test_filename)
    
    # Vérifier que le fichier a été sauvegardé
    assert os.path.exists(file_path)
    
    # Vérifier le contenu du fichier
    with open(file_path, "rb") as f:
        content = f.read()
        assert content == test_bytes
    
    # Tester avec un sous-répertoire spécifique
    subdir_path = service.save_image(test_bytes, test_filename, subdir="test_subdir")
    
    # Vérifier que le fichier a été sauvegardé dans le sous-répertoire
    assert "test_subdir" in subdir_path
    assert os.path.exists(subdir_path)
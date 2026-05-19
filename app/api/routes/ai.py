# app/api/routes/ai.py - Routes pour la gestion des modèles IA

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth_service import get_current_user
from app.models.user import User
from app.ml.model_loader import model_manager
from app.services.image_processing_service import ImageProcessingService
from app.worker.tasks import test_ai_model

router = APIRouter()

@router.get("/models", response_model=Dict[str, Any])
async def list_ai_models(current_user: User = Depends(get_current_user)):
    """
    Liste tous les modèles IA disponibles
    """
    try:
        available_models = model_manager.list_available_models()
        downloaded_models = model_manager.list_downloaded_models()
        
        return {
            "available_models": available_models,
            "downloaded_models": downloaded_models,
            "default_model": model_manager.default_models,
            "models_directory": str(model_manager.models_dir)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération modèles: {str(e)}")

@router.get("/models/{model_name}", response_model=Dict[str, Any])
async def get_model_info(model_name: str, current_user: User = Depends(get_current_user)):
    """
    Obtient les informations détaillées d'un modèle
    """
    try:
        model_info = model_manager.get_model_info(model_name)
        if not model_info:
            raise HTTPException(status_code=404, detail=f"Modèle '{model_name}' non trouvé")
        
        return model_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur info modèle: {str(e)}")

@router.post("/models/{model_name}/download")
async def download_model(model_name: str, current_user: User = Depends(get_current_user)):
    """
    Télécharge un modèle IA
    """
    try:
        # Vérifier que le modèle existe
        if model_name not in model_manager.available_models:
            available = list(model_manager.available_models.keys())
            raise HTTPException(
                status_code=404, 
                detail=f"Modèle '{model_name}' non disponible. Modèles disponibles: {available}"
            )
        
        # Télécharger le modèle
        model_path = model_manager.get_model_path(model_name)
        
        return {
            "success": True,
            "message": f"Modèle '{model_name}' téléchargé avec succès",
            "model_path": model_path,
            "model_info": model_manager.get_model_info(model_name)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur téléchargement modèle: {str(e)}")

@router.delete("/models/{model_name}")
async def delete_model(model_name: str, current_user: User = Depends(get_current_user)):
    """
    Supprime un modèle téléchargé
    """
    try:
        success = model_manager.delete_model(model_name)
        
        if success:
            return {
                "success": True,
                "message": f"Modèle '{model_name}' supprimé avec succès"
            }
        else:
            return {
                "success": False,
                "message": f"Modèle '{model_name}' non trouvé ou déjà supprimé"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur suppression modèle: {str(e)}")

@router.post("/models/{model_name}/test")
async def test_model(model_name: str, current_user: User = Depends(get_current_user)):
    """
    Lance un test d'un modèle IA
    """
    try:
        # Lancer le test en arrière-plan avec Celery
        task = test_ai_model.delay(model_name)
        
        return {
            "success": True,
            "message": f"Test du modèle '{model_name}' lancé",
            "task_id": task.id,
            "status_url": f"/api/v1/ai/test/{task.id}/status"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur test modèle: {str(e)}")

@router.get("/test/{task_id}/status")
async def get_test_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Récupère le statut d'un test de modèle
    """
    try:
        from app.worker.celery_app import celery_app
        
        task = celery_app.AsyncResult(task_id)
        
        result = {
            "task_id": task_id,
            "status": task.status,
            "ready": task.ready()
        }
        
        if task.ready():
            if task.successful():
                result["result"] = task.result
            else:
                result["error"] = str(task.result)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statut test: {str(e)}")

@router.post("/process/test")
async def test_ai_processing(
    file: UploadFile = File(...),
    model_name: Optional[str] = None,
    background_color: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Test de traitement IA direct (sans passer par le système de tâches)
    """
    try:
        # Vérifier le type de fichier
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Le fichier doit être une image")
        
        # Lire le fichier
        contents = await file.read()
        
        # Sauvegarder temporairement
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name
        
        try:
            # Initialiser le service de traitement
            service = ImageProcessingService(model_name=model_name)
            
            # Options de traitement
            options = {}
            if background_color:
                options['background_color'] = background_color
            
            # Traitement IA
            import asyncio
            result_path = await service.process_with_ai(temp_path, options)
            
            # Lire le résultat
            with open(result_path, 'rb') as result_file:
                result_bytes = result_file.read()
            
            # Nettoyer les fichiers temporaires
            os.unlink(temp_path)
            os.unlink(result_path)
            
            # Retourner l'image traitée
            from fastapi.responses import StreamingResponse
            import io
            
            return StreamingResponse(
                io.BytesIO(result_bytes),
                media_type="image/png",
                headers={"Content-Disposition": "attachment; filename=processed_image.png"}
            )
            
        except Exception as processing_error:
            # Nettoyer en cas d'erreur
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise processing_error
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur traitement test: {str(e)}")

@router.post("/cache/cleanup")
async def cleanup_model_cache(current_user: User = Depends(get_current_user)):
    """
    Nettoie le cache des modèles
    """
    try:
        stats = model_manager.cleanup_cache()
        
        return {
            "success": True,
            "message": "Nettoyage du cache terminé",
            "stats": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur nettoyage cache: {str(e)}")

@router.get("/stats")
async def get_ai_stats(current_user: User = Depends(get_current_user)):
    """
    Statistiques sur l'utilisation de l'IA
    """
    try:
        # Statistiques des modèles
        available_count = len(model_manager.available_models)
        downloaded_models = model_manager.list_downloaded_models()
        downloaded_count = len(downloaded_models)
        
        # Taille totale des modèles téléchargés
        total_size_mb = sum(model['size_mb'] for model in downloaded_models)
        
        # Espace disque du répertoire modèles
        import shutil
        total_space, used_space, free_space = shutil.disk_usage(model_manager.models_dir)
        
        return {
            "models": {
                "available": available_count,
                "downloaded": downloaded_count,
                "total_size_mb": round(total_size_mb, 1),
                "default_model": model_manager.default_models
            },
            "disk_space": {
                "total_gb": round(total_space / (1024**3), 1),
                "used_gb": round(used_space / (1024**3), 1),
                "free_gb": round(free_space / (1024**3), 1)
            },
            "models_directory": str(model_manager.models_dir)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statistiques IA: {str(e)}")
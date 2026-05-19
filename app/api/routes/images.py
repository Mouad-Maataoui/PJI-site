# app/api/routes/images.py - Imports complets

import os
import logging
import re
import io
from typing import Optional, Dict, Any, Literal
from pathlib import Path
from PIL import Image, UnidentifiedImageError

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse  # ← Ajouter cette ligne
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.services.auth_service import get_current_user
from app.models.user import User
from app.models.image_task import ProcessingStatus, ImageTask
from app.core.config import settings
from app.services.image_processing_service import ImageProcessingService
from app.db.repositories.image_repository import ImageRepository
from app.db.repositories.user_repository import UserRepository
from fastapi.responses import FileResponse
from fastapi import BackgroundTasks
from app.services.payment_service import PaymentService
from app.core.config import settings
import json

router = APIRouter()
logger = logging.getLogger(__name__)

# Formats d'images supportés
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/bmp", 
    "image/tiff", "image/webp"
}

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(..., description="Fichier image à traiter"),
    models_type: Literal["bg_remove", "upscale"] = Form("bg_remove", description="Type de traitement à réaliser sur l'image parmi ('bg_remove', 'upscale')"),
    quality: Optional[int] = Form(85, ge=1, le=100, description="Qualité de compression (1-100)"),
    format: Optional[str] = Form(None, description="Format de sortie (jpeg, png)"),
    force_process: Optional[str] = Form(False, description="Force le process de l'image mais si le nom correspond à une image déjà process"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    models_name: Optional[str] = Form(None, description="Nom du modèle à utiliser parmi les modèles disponibles, si vide, le modèle par défaut est utilisé"),
    models_options: str = Form('{}', description="JSON string pour les options des modèles\n\
        bg_remove: background_color = 'transparent' => Couleur de fond (transparent, white, black, etc.)\n\
        upscale: \
    ")
):
    """
    Upload et traite une image via form-data.
    
    Args:
        file: Fichier image à uploader (JPEG, PNG)
        models_type: type de modèle à utiliser (bg_remove, upscale)
        quality: Qualité de compression (1-100, défaut: 85)
        format: Format de sortie souhaité 
        background_color: Couleur de fond après suppression
        current_user: Utilisateur connecté
        db: Session de base de données
        models_options: Options sous forme d'objet JSON pour les options du type de modèle utilisé (bg_remove, upscale,...) 
    """
    # Parsing models_options
    try:
        options_dict: dict = json.loads(models_options)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="models_options doit contenir un JSON valide"
        )
    background_color = options_dict.get("background_color", "transparent")
    
    from app.services.payment_service import PaymentService
    payment_service = PaymentService(db)
    
    # Vérifier que l'utilisateur a assez de points
    points_needed = settings.POINTS_COST_PER_IMAGE
    if current_user.points_balance < points_needed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Points insuffisants. Requis: {points_needed}, disponibles: {current_user.points_balance}. Achetez plus de points."
        )
    # Valider le fichier
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier requis"
        )
    
    ext = os.path.splitext(file.filename)[1].lower().strip(".")
    
    # Vérifier l'extension
    supported_formats = ["jpg", "jpeg", "png"]
    if ext not in supported_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format non supporté. Formats acceptés: {', '.join(supported_formats)}"
        )
    
    # Valider la taille du fichier
    content = await file.read()
    file_size = len(content)
    
    max_size = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024  # Convertir en bytes
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fichier trop volumineux. Taille maximale: {settings.MAX_IMAGE_SIZE_MB}MB"
        )
    
    # Vérification si le fichier est corrompu
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify() 
            
            # Double check: verify correct format matches extension (in case of renamed extension)
            if img.format.lower() not in ['jpeg', 'jpg', 'png']:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="L'en-tête du fichier ne correspond pas à son extension.")
    except (IOError, UnidentifiedImageError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier image semble corrompu ou illisible."
        )
    
    if not force_process:
        # Vérifier si le fichier n'a pas déjà était traité par le même utilisateur
        stmt = select(ImageTask.original_file_path).where(ImageTask.user_id == current_user.id)
        objs = db.scalars(stmt).all()
        for row in objs:
            original_filename = "_".join(row.split("_")[1:])
            if file.filename == original_filename:
                print(original_filename)
                logger.warning(f"Upload d'une image déjà traité (par le nom du fichier)")
                raise HTTPException(
                    status_code=500,
                    detail=f"Erreur lors du traitement de l'image, image {original_filename} déjà traité"
                )
    
    # Construire les options de traitement
    processing_options = {
        "quality": quality,
        "background_color": background_color
    }
    
    if format:
        processing_options["format"] = format
    
    
    try:
        # Créer une instance du service
        processing_service = ImageProcessingService(
            models_name=models_name if models_name != None else settings.DEFAULT_AI_MODEL_BG if models_type=="bg_remove" else settings.DEFAULT_AI_MODEL_UPSCALE,
            db_session=db,
            models_type=models_type
        )
        
        # Sauvegarder l'image originale pour le traitement
        original_path = processing_service.save_image(
            content, 
            file.filename, 
            subdir="uploads/original"
        )
        
        # Compresser l'image pour la sauvegarde
        compressed_image, detected_format = await processing_service.compress_image(content)
        
        # Sauvegarder l'image compressée
        compressed_path = processing_service.save_image(
            compressed_image, 
            file.filename, 
            subdir="uploads/compressed"
        )
        
        # Créer 2 tâches dans la base de données, une pour le traitement résolution par défaut une pour résolution originale
        image_repo = ImageRepository(db)
        task_id1 = image_repo.create_task(
            user_id=current_user.id,
            original_filename=file.filename,
            original_file_path=original_path,
            compressed_file_path=compressed_path
        )

        if models_type == 'bg_remove':
            image_repo = ImageRepository(db)
            task_id2 = image_repo.create_task(
                user_id=current_user.id,
                original_filename=file.filename,
                original_file_path=original_path,
                compressed_file_path=compressed_path
            )
        
        # Déduire les points AVANT de lancer le traitement
        points_success, points_result = payment_service.deduct_points_for_processing(
            user_id=current_user.id,
            task_id=task_id1
        )
        
        if not points_success:
            # Si la déduction échoue, supprimer la tâche créée et les fichiers
            image_repo.delete_task(task_id1)
            if models_type == 'bg_remove':
                image_repo.delete_task(task_id2)
            
            # Nettoyer les fichiers
            try:
                if os.path.exists(original_path):
                    os.remove(original_path)
                if os.path.exists(compressed_path):
                    os.remove(compressed_path)
            except Exception as cleanup_error:
                logger.warning(f"Erreur nettoyage fichiers: {cleanup_error}")
            
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=points_result.get("error", "Erreur lors de la déduction des points")
            )
        
        logger.info(f"Points déduits avec succès: {points_result}")
        
        # Lancer le traitement en arrière-plan
        celery_task_id1 = processing_service.run_processing_threads(
            task_id=task_id1,
            original_path=original_path,    # Image originale pour le traitement
            compressed_path=compressed_path, # Image compressée pour la sauvegarde
            mode='main',
            models_type=models_type,
            options=processing_options
        )

        if models_type == 'bg_remove':
            celery_task_id2 = processing_service.run_processing_threads(
                task_id=task_id2,
                original_path=original_path,    # Image originale pour le traitement
                compressed_path=compressed_path, # Image compressée pour la sauvegarde
                mode='original-res',
                options=processing_options
            )
        
        return {
            "task_id": task_id1,
            "celery_task_id": celery_task_id1,
            "status": "pending",
            "message": "Image en cours de traitement",
            "estimated_time": "30-60 secondes",
            "original_size": file_size,
            "options_applied": processing_options,
            "points_deducted": points_result["points_deducted"],
            "remaining_points": points_result["new_balance"],
            "transaction_id": points_result["transaction_id"]
        }
    
    except Exception as e:
        logger.error(f"Erreur lors du traitement de l'image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement de l'image: {str(e)}"
        )

@router.get("/tasks")
async def get_user_tasks(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Récupère les tâches d'image de l'utilisateur.
    
    Args:
        skip: Nombre d'éléments à sauter (pagination)
        limit: Nombre maximum d'éléments à retourner (max 100)
        status_filter: Filtrer par statut (pending, processing, completed, failed)
        current_user: Utilisateur connecté
        db: Session de base de données
    """
    # Valider la limite
    if limit > 100:
        limit = 100
    
    try:
        image_repo = ImageRepository(db)
        tasks = image_repo.get_user_tasks(current_user.id, limit, skip)
        
        # Filtrer par statut si demandé
        if status_filter:
            tasks = [task for task in tasks if task.status == status_filter]
        
        # Convertir les tâches en dictionnaires
        result = []
        for task in tasks:
            task_dict = {
                "id": task.id,
                "original_filename": task.original_filename,
                "status": task.status,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "error_message": task.error_message,
                "can_download": task.status == ProcessingStatus.COMPLETED.value and task.processed_file_path is not None,
                "expire_at": task.expire_at.isoformat() if task.expire_at else None
            }
            result.append(task_dict)
        
        return {
            "tasks": result,
            "total": len(result),
            "skip": skip,
            "limit": limit
        }
    
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des tâches: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération des tâches: {str(e)}"
        )

@router.get("/tasks/{task_id}")
async def get_task_details(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Récupère les détails d'une tâche spécifique.
    
    Args:
        task_id: ID de la tâche
        current_user: Utilisateur connecté
        db: Session de base de données
    """
    try:
        image_repo = ImageRepository(db)
        task = image_repo.get_task(task_id)
        
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Tâche non trouvée"
            )
        
        if task.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Vous n'êtes pas autorisé à accéder à cette tâche"
            )
        
        # Convertir la tâche en dictionnaire détaillé
        task_dict = {
            "id": task.id,
            "original_filename": task.original_filename,
            "status": task.status,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "expire_at": task.expire_at.isoformat() if task.expire_at else None,
            "error_message": task.error_message,
            "can_download": task.status == ProcessingStatus.COMPLETED.value and task.processed_file_path is not None,
            "can_retry": task.status == ProcessingStatus.FAILED.value,
            "s3_url": getattr(task, 's3_path', None)
        }
        
        return task_dict
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des détails de la tâche: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la récupération des détails de la tâche: {str(e)}"
        )
    
# Helper private function 
async def _get_image_file_for_task(task_id: int, current_user: User, db: Session):
    image_repo = ImageRepository(db)
    task = image_repo.get_task(task_id)
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tâche non trouvée"
        )
    
    # Vérifier que la tâche appartient à l'utilisateur
    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé à cette tâche"
        )
    
    # Vérifier que le traitement est terminé
    if task.status != ProcessingStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Image pas encore prête. Statut actuel: {task.status}"
        )
    
    temp_file_path = None
    content_type = "image/png"  # Par défaut
    filename = f"processed_{task.original_filename}"
    
    # Télécharger depuis le cloud vers un fichier temporaire
    if hasattr(task, 'cloud_processed_url') and task.cloud_processed_url:
        logger.info(f"Téléchargement depuis cloud: {task.cloud_processed_url}")
        
        try:
            from app.services.storage_service import get_storage_service
            storage_service = get_storage_service()
            
            # Créer répertoire temporaire
            temp_dir = Path(settings.IMAGE_STORAGE_PATH) / "temp_downloads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Générer nom de fichier temporaire unique
            import uuid
            temp_filename = f"{uuid.uuid4()}_{task.original_filename}"
            temp_file_path = temp_dir / temp_filename
            
            # Télécharger vers fichier temporaire
            success = storage_service.download_cloud_file(task.cloud_processed_url, str(temp_file_path))
            
            if success and temp_file_path.exists():
                logger.info(f"Image téléchargée depuis cloud vers: {temp_file_path}")
                
                # Déterminer le type de contenu
                if str(temp_file_path).lower().endswith('.png'):
                    content_type = "image/png"
                elif str(temp_file_path).lower().endswith(('.jpg', '.jpeg')):
                    content_type = "image/jpeg"
                else:
                    # Détecter par magic bytes
                    with open(temp_file_path, 'rb') as f:
                        header = f.read(8)
                        if header[:8] == b'\x89PNG\r\n\x1a\n':
                            content_type = "image/png"
                        elif header[:3] == b'\xff\xd8\xff':
                            content_type = "image/jpeg"
            else:
                logger.warning("Échec téléchargement cloud, tentative fichier local...")
                temp_file_path = None
                
        except Exception as e:
            logger.warning(f"Erreur téléchargement cloud: {str(e)}")
            temp_file_path = None
    
    # Fallback vers fichier local
    if temp_file_path is None:
        logger.info("Tentative lecture fichier local...")
        
        if hasattr(task, 'processed_file_path') and task.processed_file_path:
            if os.path.exists(task.processed_file_path):
                temp_file_path = Path(task.processed_file_path)
                logger.info(f"Fichier local trouvé: {temp_file_path}")
                
                # Déterminer le type
                if str(temp_file_path).lower().endswith('.png'):
                    content_type = "image/png"
                elif str(temp_file_path).lower().endswith(('.jpg', '.jpeg')):
                    content_type = "image/jpeg"
            else:
                logger.warning(f"Fichier local non trouvé: {task.processed_file_path}")
    
    # Si toujours pas de fichier, erreur 404
    if temp_file_path is None or not temp_file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image traitée non trouvée (ni cloud ni local)"
        )
    
    # Valider la taille du fichier
    file_size = temp_file_path.stat().st_size
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fichier image vide"
        )
    
    # Nettoyer le nom de fichier
    safe_filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    return temp_file_path, safe_filename, content_type

@router.get("/processed")
async def list_processed_images(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Liste toutes les images traités et original dans un dictionnaire de la forme {'original_filename_n': (url_original, url_processed)}
    
    :db: Session de base de données
    :current_user: Utilisateur connecté
    """
    try:
        from app.services.storage_service import get_storage_service
        storage_service = get_storage_service()

        dic = {}
        cpt = {}
        stmt = select(ImageTask.original_filename, ImageTask.cloud_original_url, ImageTask.cloud_processed_url).where(ImageTask.user_id == current_user.id)
        for k, c_o, c_p in db.execute(stmt):
            if k in dic.keys():
                if k in cpt: cpt[k] += 1
                else: cpt[k] = 1
                k = f"{k}({cpt[k]})"
            dw_url_co = storage_service.generate_download_url(c_o)
            dw_url_cp = storage_service.generate_download_url(c_p)
            dic[k] = (dw_url_co, dw_url_cp)
        return dic
    except Exception as e:
        logger.error(f"Error pendant le listing des images process: {e}")
        return {}


@router.get("/download/{task_id}")
async def download_processed_image(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Télécharge une image traitée avec décompression automatique
    """
    try:
        temp_file_path, safe_filename, content_type = await _get_image_file_for_task(task_id=task_id, current_user=current_user, db=db)
        
        # Import nécessaire pour FileResponse
        from fastapi.responses import FileResponse
        from fastapi import BackgroundTasks
        
        # Fonction de nettoyage pour supprimer le fichier temporaire après envoi
        def cleanup_temp_file():
            try:
                # Seulement supprimer si c'est un fichier temporaire (pas le fichier original)
                if "temp_downloads" in str(temp_file_path):
                    if temp_file_path.exists():
                        temp_file_path.unlink()
                        logger.info(f"Fichier temporaire supprimé: {temp_file_path.name}")
            except Exception as e:
                logger.warning(f"Erreur suppression fichier temporaire: {str(e)}")
    
        background_tasks = BackgroundTasks()
        
        # Ajouter la tâche de nettoyage seulement pour les fichiers temporaires
        if "temp_downloads" in str(temp_file_path):
            background_tasks.add_task(cleanup_temp_file)
    
        # DÉCOMPRESSION AUTOMATIQUE : FileResponse gère automatiquement
        # la décompression lors de l'envoi au client
        logger.info(f"Envoi fichier décompressé au client: {temp_file_path}")

        return FileResponse(
            path=str(temp_file_path),
            filename=safe_filename,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{safe_filename}\"",
                "Cache-Control": "no-cache"
            },
            background=background_tasks  # Pour nettoyer le fichier temporaire après envoi
        )
        
    except HTTPException:
        # Re-lever les erreurs HTTP
        raise
    except Exception as e:
        logger.error(f"Erreur téléchargement inattendue: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur serveur: {str(e)}"
        )
    
@router.get("/preview/{task_id}")
async def preview_processed_image(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Télécharge une image traitée avec décompression automatique
    """
    try:
        temp_file_path, safe_filename, content_type = await _get_image_file_for_task(task_id=task_id, current_user=current_user, db=db)
        
        # Import nécessaire pour FileResponse
        from fastapi.responses import FileResponse
        from fastapi import BackgroundTasks
        
        # Fonction de nettoyage pour supprimer le fichier temporaire après envoi
        def cleanup_temp_file():
            try:
                # Seulement supprimer si c'est un fichier temporaire (pas le fichier original)
                if "temp_downloads" in str(temp_file_path):
                    if temp_file_path.exists():
                        temp_file_path.unlink()
                        logger.info(f"Fichier temporaire supprimé: {temp_file_path.name}")
            except Exception as e:
                logger.warning(f"Erreur suppression fichier temporaire: {str(e)}")
    
        background_tasks = BackgroundTasks()
        
        # Ajouter la tâche de nettoyage seulement pour les fichiers temporaires
        if "temp_downloads" in str(temp_file_path):
            background_tasks.add_task(cleanup_temp_file)
    
        # DÉCOMPRESSION AUTOMATIQUE : FileResponse gère automatiquement
        # la décompression lors de l'envoi au client
        logger.info(f"Envoi fichier décompressé pour preview au client: {temp_file_path}")

        return FileResponse(
            path=str(temp_file_path),
            filename=safe_filename,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=\"{safe_filename}\"",
                "Cache-Control": "no-cache"
            },
            background=background_tasks  # Pour nettoyer le fichier temporaire après envoi
        )
        
    except HTTPException:
        # Re-lever les erreurs HTTP
        raise
    except Exception as e:
        logger.error(f"Erreur téléchargement inattendue: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur serveur: {str(e)}"
        )
                
@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Supprime une tâche et ses fichiers associés.
    
    Args:
        task_id: ID de la tâche à supprimer
        current_user: Utilisateur connecté
        db: Session de base de données
    """
    try:
        image_repo = ImageRepository(db)
        task = image_repo.get_task(task_id)
        
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Tâche non trouvée"
            )
        
        if task.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Vous n'êtes pas autorisé à supprimer cette tâche"
            )
        
        # Supprimer les fichiers physiques
        files_to_delete = [
            task.original_file_path,
            task.compressed_file_path,
            task.processed_file_path
        ]
        
        deleted_files = []
        for file_path in files_to_delete:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    deleted_files.append(os.path.basename(file_path))
                except Exception as e:
                    logger.warning(f"Erreur lors de la suppression du fichier {file_path}: {str(e)}")
        
        # Supprimer la tâche de la base de données
        image_repo.delete_task(task_id)
        
        return {
            "message": "Tâche supprimée avec succès",
            "task_id": task_id,
            "deleted_files": deleted_files
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de la tâche: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la suppression de la tâche: {str(e)}"
        )

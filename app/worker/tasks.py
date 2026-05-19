from app.worker.celery_app import celery_app
from app.db.session import SessionLocal
import logging
import os
import asyncio
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Literal

from app.worker.thread_manager import ThreadManager
from app.models.image_task import ProcessingStatus
from app.services.storage_service import StorageService
from app.services.websocket_notifier import websocket_notifier

from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.process_image_task")
def process_image_task(task_id: int, original_path: str, compressed_path: str, mode: str = 'main',
        models_type: Literal['bg_remove', 'upscale'] = 'bg_remove', options: Optional[Dict[str, Any]] = None):
    """
    Tâche principale pour le traitement d'image avec IA ONNX
    """
    db = SessionLocal()
    storage_service = StorageService()

    from app.services.queue_service import QueueService 
    from app.db.repositories.image_repository import ImageRepository
    from app.services.image_processing_service import ImageProcessingService


    try:
        # Initialisation
        image_repo = ImageRepository(db)

        # Récupérer les infos de la tâche
        task_info = image_repo.get_task(task_id)
        if not task_info:
            raise Exception(f"Tâche {task_id} non trouvée")
        
        user_id = task_info.user_id

        ai_model = settings.DEFAULT_AI_MODEL_BG if models_type == "bg_remove" else settings.DEFAULT_AI_MODEL_UPSCALE
        service = ImageProcessingService(db_session=db, models_name=ai_model, models_type=models_type)
        
        # ========================
        # PHASE 1: Traitement IA + Upload Original
        # ========================
        
        logger.info(f"Phase 1: Traitement IA + Upload original pour tâche {task_id}, mode {mode}")
        
        thread_manager = ThreadManager()
        thread_results = {}
        def upload_original_thread_func(compressed_path):
            """Thread pour upload OBLIGATOIRE de l'original compressé"""
            try:
                logger.info(f"Thread upload original: {compressed_path} => Cloud")
                
                # Upload original compressé vers cloud (OBLIGATOIRE)
                upload_success, cloud_original_url = storage_service.upload_original_backup(
                    compressed_path, user_id, task_id
                )
                
                if not upload_success or not cloud_original_url:
                    error_msg = "Upload original vers cloud ÉCHOUÉ"
                    logger.error(error_msg)
                    image_repo.update_status(task_id, ProcessingStatus.FAILED.value, error_msg)
                    raise Exception(error_msg)
                
                # Sauvegarder l'URL cloud en BDD
                image_repo.update_cloud_original_url(task_id, cloud_original_url)
                
                thread_results["upload_original_success"] = True
                thread_results["cloud_original_url"] = cloud_original_url
                logger.info(f"Thread upload original: RÉUSSI → {cloud_original_url}, mode {mode}")
                
            except Exception as e:
                logger.error(f"ERREUR upload original: {str(e)}, mode {mode}")
                thread_results["upload_original_success"] = False
                thread_results["upload_original_error"] = str(e)
                raise
        
        def process_ai_thread_func(original_path, mode):
            """Thread pour traitement IA de l'image originale"""
            if mode == 'main' and models_type == 'bg_remove':
                tmp_options = options.copy() if options else {}
                tmp_options['resize'] = {'width': settings.DEFAULT_IMAGE_WIDTH, 'height': settings.DEFAULT_IMAGE_HEIGHT}
            else:
                tmp_options = options.copy() if options else {}

            try:
                logger.info(f"Thread IA: Traitement ONNX de {original_path}, mode {mode}")
            
                # Traitement IA avec ONNX
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Essayer le traitement IA
                    processed_path = loop.run_until_complete(
                        service.process_with_ai(original_path, models_type, tmp_options)
                    )
                    logger.info(f"Traitement IA ONNX réussi: {processed_path}, mode {mode}, type de modèle: {models_type}")
                    
                except Exception as ai_error:
                    logger.warning(f"Traitement IA échoué, fallback vers mock: {str(ai_error)}")
                    # Fallback vers traitement mock
                    processed_path = loop.run_until_complete(
                        service.process_mock(original_path, tmp_options)
                    )
                    logger.info(f"Traitement fallback réussi: {processed_path}, mode {mode}, type de modèle: {models_type}")
                finally:
                    loop.close()
                
                # Compresser l'image traitée pour stockage cloud
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    compressed_processed_path = loop.run_until_complete(service.compress_and_save_image(
                        processed_path, 
                        f"compressed_processed_{os.path.basename(processed_path)}"
                    ))
                finally:
                    loop.close()
                
                thread_results["process_ai_success"] = True
                thread_results["processed_path"] = processed_path
                thread_results["compressed_processed_path"] = compressed_processed_path
                logger.info(f"Thread IA: RÉUSSI → {compressed_processed_path}")
                
            except Exception as e:
                logger.error(f"ERREUR traitement IA: {str(e)}")
                thread_results["process_ai_success"] = False
                thread_results["process_ai_error"] = str(e)
                image_repo.update_status(task_id, ProcessingStatus.FAILED.value, f"Erreur IA: {str(e)}")
                raise
        
        # Lancer Phase 1 en parallèle
        if mode == 'main':
            thread_manager.start_thread("upload_original_thread", upload_original_thread_func, compressed_path)
        else:
            cloud_url, _ = storage_service._get_cloud_url(compressed_path, user_id, task_id)
            image_repo.update_cloud_original_url(task_id, cloud_url)
        thread_manager.start_thread("process_ai_thread", process_ai_thread_func, original_path, mode)
        
        # Attendre fin Phase 1
        thread_manager.wait_all()
        
        # Vérifier succès Phase 1
        if mode == 'main':
            if not thread_results.get("upload_original_success", False):
                error_msg = thread_results.get("upload_original_error", "Upload original échoué")
                websocket_notifier.send_task_notification(
                    user_id=user_id,
                    task_id=task_id,
                    status="failed",
                    message=f"{error_msg}",
                    extra_data={}
                )
                return {"status": "error", "message": error_msg, "task_id": task_id}
            
        if not thread_results.get("process_ai_success", False):
            error_msg = thread_results.get("process_ai_error", "Traitement IA échoué")
            websocket_notifier.send_task_notification(
                user_id=user_id,
                task_id=task_id,
                status="failed",
                message=f"{error_msg}",
                extra_data={}
            )
            return {"status": "error", "message": error_msg, "task_id": task_id}
        
        # Récupérer les résultats Phase 1
        compressed_processed_path = thread_results.get("compressed_processed_path")
        processed_path = thread_results.get("processed_path")
        
        if not compressed_processed_path:
            return {"status": "error", "message": "Chemin image traitée non trouvé", "task_id": task_id}
        
        # NOTIFICATION: Phase 1 terminée
        websocket_notifier.send_task_notification(
            user_id=user_id,
            task_id=task_id,
            status="processing",
            message="Sauvegarde et préparation du téléchargement...",
            extra_data={"phase": "upload_and_delivery"}
        )
        
        # ========================
        # PHASE 2: Upload Résultat + Envoi Client 
        # ========================
        
        logger.info(f"Phase 2: Upload résultat + Envoi client pour tâche {task_id}, mode {mode}")
        
        thread_manager = ThreadManager()
        thread_results_phase2 = {}
        
        def upload_result_thread_func(compressed_processed_path):
            """Thread pour upload OBLIGATOIRE du résultat traité"""
            try:
                logger.info(f"Thread upload résultat: {compressed_processed_path} → Cloud")
                
                tag = "default_res" if mode == 'main' and models_type == "bg_remove" else ""

                # Upload résultat compressé vers cloud (OBLIGATOIRE)
                task_tmp = task_id if mode == 'main' else task_id-1
                upload_success, cloud_processed_url = storage_service.upload_processed_image(
                    compressed_processed_path, user_id, task_tmp, tag
                )
                
                if not upload_success or not cloud_processed_url:
                    error_msg = "Upload résultat vers cloud ÉCHOUÉ"
                    logger.error(error_msg)
                    image_repo.update_status(task_id, ProcessingStatus.FAILED.value, error_msg)
                    raise Exception(error_msg)
                
                # Sauvegarder l'URL cloud résultat en BDD
                image_repo.update_cloud_processed_url(task_id, cloud_processed_url)
                
                thread_results_phase2["upload_result_success"] = True
                thread_results_phase2["cloud_processed_url"] = cloud_processed_url
                logger.info(f"Thread upload résultat: RÉUSSI → {cloud_processed_url}")
                
            except Exception as e:
                logger.error(f"ERREUR upload résultat: {str(e)}")
                thread_results_phase2["upload_result_success"] = False
                thread_results_phase2["upload_result_error"] = str(e)
                raise
        
        def client_delivery_thread_func(compressed_processed_path):
            """Thread pour marquer prêt envoi immédiat client"""
            try:
                logger.info(f"Thread client: Préparation envoi immédiat depuis {compressed_processed_path}")
                
                # Vérifier que le fichier local existe encore
                if not os.path.exists(compressed_processed_path):
                    raise Exception(f"Fichier résultat local introuvable: {compressed_processed_path}")
                
                # Marquer la tâche comme COMPLETED (image disponible pour client)
                image_repo.update_status(task_id, ProcessingStatus.COMPLETED.value)
                
                thread_results_phase2["client_delivery_success"] = True 
                thread_results_phase2["local_result_path"] = compressed_processed_path
                logger.info(f"Thread client: PRÊT pour envoi immédiat")
                
            except Exception as e:
                logger.error(f"ERREUR préparation client: {str(e)}")
                thread_results_phase2["client_delivery_success"] = False
                thread_results_phase2["client_delivery_error"] = str(e)
                raise
        
        # Lancer Phase 2 en parallèle
        thread_manager.start_thread("upload_result_thread", upload_result_thread_func, compressed_processed_path)
        thread_manager.start_thread("client_delivery_thread", client_delivery_thread_func, compressed_processed_path)
        
        # Attendre fin Phase 2
        thread_manager.wait_all()
        
        # Vérifier succès Phase 2
        if not thread_results_phase2.get("upload_result_success", False):
            error_msg = thread_results_phase2.get("upload_result_error", "Upload résultat échoué")
            websocket_notifier.send_task_notification(
                user_id=user_id,
                task_id=task_id,
                status="failed",
                message=f"{error_msg}",
                extra_data={}
            )
            return {"status": "error", "message": error_msg, "task_id": task_id}
        
        if not thread_results_phase2.get("client_delivery_success", False):
            error_msg = thread_results_phase2.get("client_delivery_error", "Préparation client échouée")
            websocket_notifier.send_task_notification(
                user_id=user_id,
                task_id=task_id,
                status="failed",
                message=f"{error_msg}",
                extra_data={}
            )
            return {"status": "error", "message": error_msg, "task_id": task_id}
        
        # ========================
        # PHASE 3: Suppression Locale Complète
        # ========================
        
        logger.info(f"Phase 3: Suppression locale complète pour tâche {task_id}, mode {mode}")
        
        files_to_delete = [ 
            compressed_path,                  # Image originale compressée
            processed_path,                   # Image traitée non compressée
            compressed_processed_path         # Image traitée compressée
        ]

        if mode != 'main':
            files_to_delete.append(original_path)                    # Image originale
        
        deleted_count = 0
        for file_path in files_to_delete:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(f"Supprimé: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.warning(f"Échec suppression {file_path}: {str(e)}")
        
        # Marquer nettoyage local terminé en BDD
        image_repo.mark_local_cleanup_done(task_id)
        
        logger.info(f"Phase 3: {deleted_count} fichiers locaux supprimés, mode {mode}")
        
        # ========================
        # RÉSULTAT FINAL + NOTIFICATION SUCCÈS
        # ========================
        
        response = {
            "status": "success",
            "message": "Traitement IA complet terminé avec succès",
            "task_id": task_id,
            "ai_model": ai_model,
            "cloud_original_url": thread_results.get("cloud_original_url"),
            "cloud_processed_url": thread_results_phase2.get("cloud_processed_url"),
            "local_files_cleaned": deleted_count,
            "storage_mode": "cloud_only"
        }
        
        # NOTIFICATION: Succès complet
        logger.info(f"ENVOI NOTIFICATION COMPLETED user={user_id}, task={task_id}")
        cloud_url = thread_results_phase2.get("cloud_processed_url")
        extra_data = {
            "download_url": f"/api/v1/images/download/{task_id}",
            "preview_url": f"/api/v1/images/preview/{task_id}",
            "cloud_url": cloud_url,
            "ai_model": ai_model
        } if cloud_url else {}
        
        websocket_notifier.send_task_notification(
            user_id=user_id,
            task_id=task_id,
            status="completed",
            message="Votre image traitée par IA est prête !",
            extra_data=extra_data
        )
        
        logger.info(f"Tâche {task_id} TERMINÉE avec succès - Notification envoyée, mode {mode}")
        return response                
    
    except Exception as e:
        logger.error(f"ERREUR tâche {task_id}: {str(e)}")
        
        # NOTIFICATION: Échec général
        try:
            websocket_notifier.send_task_notification(
                user_id=user_id,
                task_id=task_id,
                status="failed",
                message=f"Erreur traitement IA: {str(e)}",
                extra_data={}
            )
        except:
            logger.error("Impossible d'envoyer notification d'échec")
        
        # Mettre à jour le statut d'erreur
        try:
            image_repo.update_status(task_id, ProcessingStatus.FAILED.value, str(e))
        except:
            logger.error("Impossible de mettre à jour le statut d'erreur")
        
        return {"status": "error", "message": str(e), "task_id": task_id}
    finally:
        db.close()

@celery_app.task(name="app.worker.tasks.delete_expired_images")
def delete_expired_images():
    """Tâche périodique pour supprimer les images expirées (cloud uniquement)"""
    logger.info("Début suppression images cloud expirées")
    db = SessionLocal()
    storage_service = StorageService()
    
    try:
        from app.db.repositories.image_repository import ImageRepository
        
        image_repo = ImageRepository(db)
        
        # Récupérer les tâches expirées
        now = datetime.now(timezone.utc)
        expired_tasks = image_repo.get_expired_images(now)
        
        count = 0
        cloud_originals_deleted = 0
        cloud_processed_deleted = 0
        
        for task in expired_tasks:
            # Supprimer fichier original cloud
            if hasattr(task, 'cloud_original_url') and task.cloud_original_url:
                try:
                    if storage_service.delete_cloud_file(task.cloud_original_url):
                        cloud_originals_deleted += 1
                        logger.info(f"Original cloud supprimé: {task.cloud_original_url}")
                except Exception as e:
                    logger.warning(f"Échec suppression original cloud: {str(e)}")
            
            # Supprimer fichier résultat cloud
            if hasattr(task, 'cloud_processed_url') and task.cloud_processed_url:
                try:
                    if storage_service.delete_cloud_file(task.cloud_processed_url):
                        cloud_processed_deleted += 1 
                        logger.info(f"Résultat cloud supprimé: {task.cloud_processed_url}")
                except Exception as e:
                    logger.warning(f"Échec suppression résultat cloud: {str(e)}")
            
            # Supprimer l'entrée BDD
            image_repo.delete_task(task.id)
            count += 1
        
        result = {
            "status": "success",
            "deleted_tasks": count,
            "deleted_cloud_originals": cloud_originals_deleted,
            "deleted_cloud_processed": cloud_processed_deleted,
            "storage_mode": "cloud_only"
        }
        
        logger.info(f"Suppression terminée: {count} tâches, {cloud_originals_deleted} originaux cloud, {cloud_processed_deleted} résultats cloud")
        return result
    
    except Exception as e:
        logger.error(f"Erreur suppression cloud expirée: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@celery_app.task(name="app.worker.tasks.test_ai_model")
def test_ai_model(models_name: str = None):
    """Tâche de test pour vérifier le bon fonctionnement d'un modèle IA"""
    try:
        from app.services.image_processing_service import ImageProcessingService
        
        # Initialiser le service avec le modèle spécifié
        service = ImageProcessingService(models_name=models_name)
        
        # Tester le modèle
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(service.test_ai_processing())
        finally:
            loop.close()
        
        logger.info(f"Test modèle IA réussi: {result}")
        return result
        
    except Exception as e:
        error_result = {
            'success': False,
            'models_name': models_name or 'default',
            'error': str(e),
            'message': f'Test échoué: {str(e)}'
        }
        logger.error(f"Test modèle IA échoué: {error_result}")
        return error_result
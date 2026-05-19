from typing import Dict, Any, Optional
from app.worker.celery_app import celery_app

class QueueService:
    """Service pour gérer les tâches en file d'attente"""
    
    @staticmethod
    def enqueue_image_processing(task_id: int, file_path: str, mode: str = 'main', options: Optional[Dict[str, Any]] = None) -> str:
        """
        Ajoute une tâche de traitement d'image à la file d'attente
        
        Args:
            task_id: ID de la tâche dans la base de données
            file_path: Chemin du fichier à traiter
            options: Options de traitement
            
        Returns:
            ID de la tâche Celery
        """
        if mode == 'main':
            queue_used = 'main-queue'
        else:
            queue_used = 'low-queue'
        task = celery_app.send_task(
            "app.worker.tasks.process_image_task", 
            args=[task_id, file_path, mode],
            kwargs={"options": options},
            queue=queue_used
        )
        print(f"DEBUG: Sending Task {task_id} (Mode: {mode}) to Queue: [{queue_used}]", flush=True)
        return task.id
    
    @staticmethod
    def get_task_status(task_id: str) -> Dict[str, Any]:
        """
        Récupère le statut d'une tâche Celery
        
        Args:
            task_id: ID de la tâche Celery
            
        Returns:
            Dictionnaire contenant le statut et les résultats/erreurs
        """
        task = celery_app.AsyncResult(task_id)
        result = {
            "task_id": task_id,
            "status": task.status
        }
        
        if task.status == "SUCCESS":
            result["result"] = task.result
        elif task.status == "FAILURE":
            result["error"] = str(task.result)
        
        return result
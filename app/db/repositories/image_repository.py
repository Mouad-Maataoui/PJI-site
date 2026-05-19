from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.image_task import ImageTask, ProcessingStatus

class ImageRepository:
    """Repository pour les tâches d'images"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_task(self, user_id: int, original_filename: str, original_file_path: str, 
                    compressed_file_path: str = None) -> int:
        """
        Crée une nouvelle tâche d'image
        
        Args:
            user_id: ID de l'utilisateur
            original_filename: Nom du fichier original
            original_file_path: Chemin vers le fichier original
            compressed_file_path: Chemin vers le fichier compressé (optionnel)
            
        Returns:
            int: ID de la tâche créée
        """
        from datetime import datetime, timedelta
        from app.core.config import settings
        
        # Calculer la date d'expiration
        expire_at = datetime.now(timezone.utc) + timedelta(days=settings.IMAGE_RETENTION_DAYS)
        
        # Créer la tâche
        image_task = ImageTask(
            user_id=user_id,
            original_filename=original_filename,
            original_file_path=original_file_path,
            compressed_file_path=compressed_file_path,
            status=ProcessingStatus.PENDING.value,
            expire_at=expire_at
        )
        
        self.db.add(image_task)
        self.db.commit()
        self.db.refresh(image_task)
        
        return image_task.id
    
    def get_task(self, task_id: int) -> Optional[ImageTask]:
        """
        Récupère une tâche par son ID
        
        Args:
            task_id: ID de la tâche
            
        Returns:
            Optional[ImageTask]: La tâche ou None si non trouvée
        """
        return self.db.query(ImageTask).filter(ImageTask.id == task_id).first()
    
    def get_user_tasks(self, user_id: int, limit: int = 50, offset: int = 0) -> List[ImageTask]:
        """
        Récupère les tâches d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            limit: Nombre maximum de tâches à récupérer
            offset: Décalage pour la pagination
            
        Returns:
            List[ImageTask]: Liste des tâches
        """
        return self.db.query(ImageTask)\
            .filter(ImageTask.user_id == user_id)\
            .order_by(desc(ImageTask.created_at))\
            .offset(offset)\
            .limit(limit)\
            .all()
    
    def update_status(self, task_id: int, status: str, error_message: Optional[str] = None) -> Optional[ImageTask]:
        """
        Met à jour le statut d'une tâche
        
        Args:
            task_id: ID de la tâche
            status: Nouveau statut
            error_message: Message d'erreur facultatif
            
        Returns:
            Optional[ImageTask]: La tâche mise à jour ou None si non trouvée
        """
        task = self.get_task(task_id)
        if task:
            task.status = status
            if error_message:
                task.error_message = error_message
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def update_processed_path(self, task_id: int, processed_file_path: str) -> Optional[ImageTask]:
        """
        Met à jour le chemin de l'image traitée
        
        Args:
            task_id: ID de la tâche
            processed_file_path: Chemin vers l'image traitée
            
        Returns:
            Optional[ImageTask]: La tâche mise à jour ou None si non trouvée
        """
        task = self.get_task(task_id)
        if task:
            task.processed_file_path = processed_file_path
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def update_s3_path(self, task_id: int, s3_path: str) -> Optional[ImageTask]:
        """
        Met à jour le chemin S3 de l'image traitée
        
        Args:
            task_id: ID de la tâche
            s3_path: URL de l'image sur S3
            
        Returns:
            Optional[ImageTask]: La tâche mise à jour ou None si non trouvée
        """
        task = self.get_task(task_id)
        if task:
            task.s3_path = s3_path
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def get_expired_images(self, reference_date: datetime) -> List[ImageTask]:
        """
        Récupère les images expirées
        
        Args:
            reference_date: Date de référence
            
        Returns:
            List[ImageTask]: Liste des tâches avec images expirées
        """
        return self.db.query(ImageTask)\
            .filter(ImageTask.expire_at <= reference_date)\
            .all()
    
    def delete_task(self, task_id: int) -> bool:
        """
        Supprime une tâche
        
        Args:
            task_id: ID de la tâche
            
        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        task = self.get_task(task_id)
        if task:
            self.db.delete(task)
            self.db.commit()
            return True
        return False
        
    def update_cloud_original_url(self, task_id: int, cloud_original_url: str) -> Optional[ImageTask]:
        """
        Met à jour l'URL cloud de l'image originale
        
        Args:
            task_id: ID de la tâche
            cloud_original_url: URL de l'image originale sur le cloud
            
        Returns:
            Optional[ImageTask]: La tâche mise à jour ou None si non trouvée
        """
        task = self.get_task(task_id)
        if task:
            task.cloud_original_url = cloud_original_url
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def update_cloud_processed_url(self, task_id: int, cloud_processed_url: str) -> Optional[ImageTask]:
        """
        Met à jour l'URL cloud de l'image traitée
        
        Args:
            task_id: ID de la tâche
            cloud_processed_url: URL de l'image traitée sur le cloud
            
        Returns:
            Optional[ImageTask]: La tâche mise à jour ou None si non trouvée
        """
        task = self.get_task(task_id)
        if task:
            task.cloud_processed_url = cloud_processed_url
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def mark_local_cleanup_done(self, task_id: int) -> Optional[ImageTask]:
        """
        Marque que le nettoyage local est terminé
        
        Args:
            task_id: ID de la tâche
            
        Returns:
            Optional[ImageTask]: La tâche mise à jour ou None si non trouvée
        """
        task = self.get_task(task_id)
        if task:
            task.local_cleanup_done = True
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def get_tasks_with_local_files(self) -> List[ImageTask]:
        """
        Récupère les tâches qui ont encore des fichiers locaux à nettoyer
        
        Returns:
            List[ImageTask]: Liste des tâches avec local_cleanup_done = False
        """
        return self.db.query(ImageTask)\
            .filter(ImageTask.local_cleanup_done == False)\
            .filter(ImageTask.status == ProcessingStatus.COMPLETED.value)\
            .all()
    
    def get_cloud_storage_stats(self) -> Dict[str, int]:
        """
        Récupère des statistiques sur le stockage cloud
        
        Returns:
            Dict[str, int]: Statistiques de stockage
        """
        total_tasks = self.db.query(ImageTask).count()
        
        tasks_with_cloud_original = self.db.query(ImageTask)\
            .filter(ImageTask.cloud_original_url.isnot(None))\
            .count()
        
        tasks_with_cloud_processed = self.db.query(ImageTask)\
            .filter(ImageTask.cloud_processed_url.isnot(None))\
            .count()
        
        tasks_cleanup_done = self.db.query(ImageTask)\
            .filter(ImageTask.local_cleanup_done == True)\
            .count()
        
        return {
            "total_tasks": total_tasks,
            "cloud_originals": tasks_with_cloud_original,
            "cloud_processed": tasks_with_cloud_processed, 
            "local_cleanup_completed": tasks_cleanup_done,
            "local_cleanup_pending": total_tasks - tasks_cleanup_done
        }
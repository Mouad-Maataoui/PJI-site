import os
import uuid
import logging
from typing import Optional, Tuple
from pathlib import Path

from app.core.config import settings
from app.s3.s3_manager import S3Manager

logger = logging.getLogger(__name__)

class StorageService:
    """Service d'abstraction pour la gestion du stockage (local + cloud)"""
    
    def __init__(self):
        self.s3_manager = S3Manager(
            account_id=settings.CLOUD_ACCOUNT_ID,
            access_key_id=settings.CLOUD_ACCESS_KEY_ID,
            secret_access_key=settings.CLOUD_SECRET_ACCESS_KEY,
            bucket_name=settings.CLOUD_BUCKET_NAME,
            cloud_endpoint=f'{settings.CLOUD_IP}:{settings.CLOUD_PORT}'
        )

    def _get_cloud_url(self, local_file_path: str, user_id: int, task_id: int, tag: str = "") -> str:
        if not os.path.exists(local_file_path):
            logger.error(f"Fichier local non trouvé: {local_file_path}")
            return False, None
        
        # Générer un nom d'objet unique dans le cloud
        file_extension = os.path.splitext(local_file_path)[1]
        cloud_object_name = f"processed/{user_id}/{task_id}/{tag+'_' if tag != '' and tag[-1] != '_' else tag}{uuid.uuid4()}{file_extension}"

        cloud_url = f"http://{self.s3_manager.cloud_endpoint}/{self.s3_manager.bucket_name}/{cloud_object_name}"

        return cloud_url, cloud_object_name


    
    def upload_processed_image(self, local_file_path: str, user_id: int, task_id: int, tag: str = "") -> Tuple[bool, Optional[str]]:
        """
        Upload une image traitée vers le stockage cloud
        
        Args:
            local_file_path: Chemin local de l'image
            user_id: ID de l'utilisateur
            task_id: ID de la tâche
            
        Returns:
            Tuple[bool, Optional[str]]: (success, cloud_url)
        """
        try:

            cloud_url, cloud_object_name = self._get_cloud_url(local_file_path, user_id, task_id, tag)
            
            # Upload vers le cloud
            success = self.s3_manager.upload_file(local_file_path, cloud_object_name)
            
            if success:
                # Générer l'URL publique
                logger.info(f"Upload réussi vers: {cloud_url}")
                return True, cloud_url
            else:
                logger.error(f"Échec de l'upload vers le cloud: {cloud_object_name}")
                return False, None
                
        except Exception as e:
            logger.error(f"Erreur lors de l'upload cloud: {str(e)}")
            return False, None
    
    def upload_original_backup(self, local_file_path: str, user_id: int, task_id: int) -> Tuple[bool, Optional[str]]:
        """
        Upload une sauvegarde de l'image originale (optionnel)
        
        Args:
            local_file_path: Chemin local de l'image
            user_id: ID de l'utilisateur  
            task_id: ID de la tâche
            
        Returns:
            Tuple[bool, Optional[str]]: (success, cloud_url)
        """
        try:
            cloud_url, cloud_object_name = self._get_cloud_url(local_file_path, user_id, task_id)

            # Upload vers le cloud
            success = self.s3_manager.upload_file(local_file_path, cloud_object_name)
            
            if success:
                cloud_url = f"http://{self.s3_manager.cloud_endpoint}/{self.s3_manager.bucket_name}/{cloud_object_name}"
                logger.info(f"Backup original réussi vers: {cloud_url}")
                return True, cloud_url
            else:
                logger.warning(f"Échec du backup original: {cloud_object_name}")
                return False, None
                
        except Exception as e:
            logger.warning(f"Erreur lors du backup original: {str(e)}")
            return False, None
    
    def delete_cloud_file(self, cloud_url: str) -> bool:
        """
        Supprime un fichier du stockage cloud
        
        Args:
            cloud_url: URL du fichier à supprimer
            
        Returns:
            bool: True si suppression réussie
        """
        try:
            # Extraire le nom d'objet de l'URL
            if settings.CLOUD_BUCKET_NAME in cloud_url:
                object_name = cloud_url.split(f"{self.s3_manager.cloud_endpoint}/{self.s3_manager.bucket_name}/")[1]                
                # Utiliser le client S3 pour supprimer
                s3_client = self.s3_manager.get_r2_client()
                s3_client.delete_object(Bucket=settings.CLOUD_BUCKET_NAME, Key=object_name)
                
                logger.info(f"Fichier cloud supprimé: {object_name}")
                return True
            else:
                logger.warning(f"URL cloud non reconnue: {cloud_url}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors de la suppression cloud: {str(e)}")
            return False
    
    def download_cloud_file(self, cloud_url: str, local_file_path: str) -> bool:
        """
        Télécharge un fichier depuis le cloud vers un fichier local temporaire
        
        Args:
            cloud_url: URL du fichier sur le cloud
            local_file_path: Chemin local où sauvegarder le fichier
            
        Returns:
            bool: True si téléchargement réussi
        """
        try:
            if settings.CLOUD_BUCKET_NAME in cloud_url:
                # Extraire le nom d'objet de l'URL
                object_name = cloud_url.split(f"{self.s3_manager.cloud_endpoint}/{self.s3_manager.bucket_name}/")[1]                
                
                # Télécharger le fichier
                success = self.s3_manager.download_file(object_name, local_file_path)
                
                if success:
                    logger.info(f"Téléchargement cloud réussi: {object_name} → {local_file_path}")
                    return True
                else:
                    logger.error(f"Échec téléchargement cloud: {object_name}")
                    return False
            else:
                logger.error(f"URL cloud non reconnue: {cloud_url}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement cloud: {str(e)}")
            return False
    
    def download_to_memory(self, cloud_url: str) -> Optional[bytes]:
        """
        Télécharge un fichier depuis le cloud directement en mémoire
        
        Args:
            cloud_url: URL du fichier sur le cloud
            
        Returns:
            Optional[bytes]: Contenu du fichier ou None si erreur
        """
        try:
            if settings.CLOUD_BUCKET_NAME in cloud_url:
                object_name = cloud_url.split(f"{self.s3_manager.cloud_endpoint}/{self.s3_manager.bucket_name}/")[1]                
                
                # Utiliser le client S3 pour récupérer directement en mémoire
                s3_client = self.s3_manager.get_r2_client()
                response = s3_client.get_object(Bucket=settings.CLOUD_BUCKET_NAME, Key=object_name)
                
                file_content = response['Body'].read()
                logger.info(f"Téléchargement mémoire réussi: {object_name} ({len(file_content)} bytes)")
                return file_content
            else:
                logger.error(f"URL cloud non reconnue pour téléchargement mémoire: {cloud_url}")
                return None
                
        except Exception as e:
            logger.error(f"Erreur téléchargement mémoire: {str(e)}")
            return None

    def generate_download_url(self, cloud_url: str, expiration_seconds: int = 3600) -> Optional[str]:
        """
        Génère une URL de téléchargement temporaire
        
        Args:
            cloud_url: URL du fichier cloud
            expiration_seconds: Durée de validité en secondes
            
        Returns:
            Optional[str]: URL de téléchargement temporaire
        """
        try:
            if settings.CLOUD_BUCKET_NAME in cloud_url:
                object_name = cloud_url.split(f"{self.s3_manager.cloud_endpoint}/{self.s3_manager.bucket_name}/")[1]  

                print(object_name)              
                
                presigned_url = self.s3_manager.generate_presigned_url(
                    object_name, 
                    expiration=expiration_seconds
                )
                
                return presigned_url
            else:
                logger.warning(f"URL cloud non reconnue pour génération presigned: {cloud_url}")
                return None
                
        except Exception as e:
            logger.error(f"Erreur lors de la génération d'URL presigned: {str(e)}")
            return None

# Instance globale pour l'injection de dépendance
def get_storage_service() -> StorageService:
    """Retourne une instance du service de stockage"""
    return StorageService()

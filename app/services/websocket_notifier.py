import json
import logging
import redis
from typing import Optional, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)

class WebSocketNotifier:
    """
    Service pour envoyer des notifications WebSocket via Redis
    Contourne les problèmes d'imports circulaires en utilisant Redis comme broker
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True
        )
    
    def send_task_notification(self, user_id: int, task_id: int, status: str, 
                             message: str, extra_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Envoie une notification de tâche via Redis pour le WebSocket manager
        
        Args:
            user_id: ID de l'utilisateur à notifier
            task_id: ID de la tâche
            status: Statut de la tâche (processing, completed, failed)
            message: Message à afficher
            extra_data: Données supplémentaires (URLs, etc.)
            
        Returns:
            bool: True si notification envoyée avec succès
        """
        try:
            notification_data = {
                "user_id": user_id,
                "task_id": task_id,
                "status": status,
                "message": message,
                "extra_data": extra_data or {},
                "timestamp": str(int(__import__('time').time()))
            }
            
            # Publier la notification dans Redis
            channel = f"websocket_notifications"
            self.redis_client.publish(channel, json.dumps(notification_data))
            
            logger.info(f"Notification envoyée via Redis: user={user_id}, task={task_id}, status={status}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi notification Redis: {str(e)}")
            return False
    
    def send_user_notification(self, user_id: int, notification_type: str, 
                             message: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Envoie une notification générale à un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            notification_type: Type de notification
            message: Message
            data: Données supplémentaires
            
        Returns:
            bool: True si succès
        """
        try:
            notification_data = {
                "user_id": user_id,
                "type": notification_type,
                "message": message,
                "data": data or {},
                "timestamp": str(int(__import__('time').time()))
            }
            
            channel = f"user_notifications"
            self.redis_client.publish(channel, json.dumps(notification_data))
            
            logger.info(f"Notification utilisateur envoyée: user={user_id}, type={notification_type}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur notification utilisateur: {str(e)}")
            return False

# Instance globale
websocket_notifier = WebSocketNotifier()
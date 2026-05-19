# app/api/routes/websockets.py
import json
import asyncio
import logging
import redis.asyncio as redis
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth_service import get_current_user
from app.models.user import User
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    """Gestionnaire de connexions WebSocket avec écoute Redis"""
    
    def __init__(self):
        # Structure: {user_id: [websocket1, websocket2, ...]}
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.redis_listener_task = None
        self.redis_client = None
    
    async def start_redis_listener(self):
        """Démarre l'écoute des notifications Redis"""
        try:
            # Créer client Redis asynchrone
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=True
            )
            
            # S'abonner aux canaux de notifications
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe("websocket_notifications", "user_notifications")
            
            logger.info("Écoute Redis démarrée pour WebSocket notifications")
            
            # Boucle d'écoute
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await self._handle_redis_message(message)
                    
        except Exception as e:
            logger.error(f"Erreur écoute Redis: {str(e)}")
    
    async def _handle_redis_message(self, message):
        """Traite un message Redis et l'envoie aux WebSockets appropriés"""
        try:
            channel = message["channel"]
            data = json.loads(message["data"])
            
            if channel == "websocket_notifications":
                # Notification de tâche
                user_id = data.get("user_id")
                task_id = data.get("task_id")
                status = data.get("status")
                msg = data.get("message")
                extra_data = data.get("extra_data", {})
                
                await self.send_task_notification(user_id, task_id, status, msg, extra_data)
                
            elif channel == "user_notifications":
                # Notification utilisateur générale
                user_id = data.get("user_id")
                notification_type = data.get("type")
                msg = data.get("message")
                notification_data = data.get("data", {})
                
                await self.send_user_notification(user_id, notification_type, msg, notification_data)
                
        except Exception as e:
            logger.error(f"Erreur traitement message Redis: {str(e)}")
    
    async def connect(self, websocket: WebSocket, user_id: int):
        """Connecte un WebSocket pour un utilisateur"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        
        # Démarrer l'écoute Redis si c'est la première connexion
        if not self.redis_listener_task and self.get_total_connections() == 1:
            self.redis_listener_task = asyncio.create_task(self.start_redis_listener())
        
        logger.info(f"User {user_id} connecté WebSocket. Connexions actives: {len(self.active_connections[user_id])}")
        
        # Message de confirmation
        await self.send_personal_message(websocket, {
            "type": "connection_established",
            "message": f"WebSocket connecté pour user {user_id}",
            "user_id": user_id,
            "total_connections": len(self.active_connections[user_id])
        })
    
    async def disconnect(self, websocket: WebSocket, user_id: int):
        """Déconnecte un WebSocket"""
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                
                logger.info(f"User {user_id} déconnecté WebSocket")
                
                # Arrêter l'écoute Redis si plus de connexions
                if self.get_total_connections() == 0 and self.redis_listener_task:
                    self.redis_listener_task.cancel()
                    self.redis_listener_task = None
                    if self.redis_client:
                        await self.redis_client.close()
                    logger.info("Écoute Redis arrêtée")
                    
            except ValueError:
                pass
    
    def get_total_connections(self) -> int:
        """Retourne le nombre total de connexions actives"""
        return sum(len(connections) for connections in self.active_connections.values())
    
    async def send_personal_message(self, websocket: WebSocket, message: dict):
        """Envoie un message à une connexion WebSocket spécifique"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.warning(f"Impossible d'envoyer message WebSocket: {str(e)}")
    
    async def send_task_notification(self, user_id: int, task_id: int, status: str, 
                                   message: str, extra_data: dict = None) -> bool:
        """Envoie une notification de tâche à un utilisateur"""
        if user_id not in self.active_connections:
            logger.warning(f"User {user_id} n'a aucune connexion WebSocket active")
            return False
        
        notification = {
            "type": "task_update",
            "task_id": task_id,
            "status": status,
            "message": message,
            "data": extra_data or {},
            "timestamp": str(int(__import__('time').time()))
        }
        
        # Envoyer à toutes les connexions de l'utilisateur
        user_connections = self.active_connections[user_id].copy()
        sent_count = 0
        
        for websocket in user_connections:
            try:
                await self.send_personal_message(websocket, notification)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Connexion WebSocket fermée pour user {user_id}: {str(e)}")
                # Retirer la connexion fermée
                try:
                    self.active_connections[user_id].remove(websocket)
                except ValueError:
                    pass
        
        logger.info(f"Notification tâche {task_id} envoyée à {sent_count} connexions pour user {user_id}")
        return sent_count > 0
    
    async def send_user_notification(self, user_id: int, notification_type: str, 
                                   message: str, data: dict = None) -> bool:
        """Envoie une notification générale à un utilisateur"""
        if user_id not in self.active_connections:
            return False
        
        notification = {
            "type": "user_notification",
            "notification_type": notification_type,
            "message": message,
            "data": data or {},
            "timestamp": str(int(__import__('time').time()))
        }
        
        user_connections = self.active_connections[user_id].copy()
        sent_count = 0
        
        for websocket in user_connections:
            try:
                await self.send_personal_message(websocket, notification)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Connexion fermée pour user {user_id}: {str(e)}")
                try:
                    self.active_connections[user_id].remove(websocket)
                except ValueError:
                    pass
        
        return sent_count > 0
    
    async def broadcast_to_all(self, message: dict):
        """Diffuse un message à toutes les connexions actives"""
        total_sent = 0
        for user_id, connections in self.active_connections.items():
            for websocket in connections.copy():
                try:
                    await self.send_personal_message(websocket, message)
                    total_sent += 1
                except Exception as e:
                    logger.warning(f"Connexion fermée lors du broadcast: {str(e)}")
                    try:
                        connections.remove(websocket)
                    except ValueError:
                        pass
        
        return total_sent

# Instance globale du gestionnaire
manager = ConnectionManager()

async def get_user_from_token(token: str, db: Session) -> User:
    """Récupère l'utilisateur à partir du token JWT"""
    try:
        from app.services.auth_service import get_current_user
        from app.core.security import oauth2_scheme
        
        # Simuler le token comme s'il venait d'OAuth2PasswordBearer
        class TokenWrapper:
            def __init__(self, token_value):
                self.token = token_value
        
        # Créer un mock de la dépendance OAuth2
        async def mock_oauth2_scheme():
            return token
        
        # Utiliser directement la logique de get_current_user
        from jose import JWTError, jwt
        from app.core.config import settings
        from app.models.schemas.token import TokenPayload
        from app.db.repositories.user_repository import UserRepository
        from fastapi import HTTPException, status
        
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Impossible de valider les informations d'identification",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id: int = int(payload.get("sub"))
            if user_id is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception
        
        user_repo = UserRepository()
        user = user_repo.get(db, user_id=user_id)
        if user is None:
            raise credentials_exception
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Utilisateur inactif",
            )
        
        return user
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalide: {str(e)}"
        )

@router.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str, db: Session = Depends(get_db)):
    """Point d'entrée WebSocket avec authentification par token"""
    try:
        # Authentifier l'utilisateur via le token
        user = await get_user_from_token(token, db)
        user_id = user.id
        
        # Connecter le WebSocket
        await manager.connect(websocket, user_id)
        
        try:
            while True:
                # Écouter les messages du client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Traiter les messages du client
                await handle_client_message(websocket, user_id, message)
                
        except WebSocketDisconnect:
            logger.info(f"Client {user_id} déconnecté")
        except Exception as e:
            logger.error(f"Erreur WebSocket pour user {user_id}: {str(e)}")
        finally:
            await manager.disconnect(websocket, user_id)
            
    except HTTPException as e:
        # Token invalide - fermer la connexion
        await websocket.close(code=4001, reason="Token invalide")
        logger.warning(f"Tentative connexion WebSocket avec token invalide")
    except Exception as e:
        await websocket.close(code=4000, reason="Erreur serveur")
        logger.error(f"Erreur WebSocket: {str(e)}")

async def handle_client_message(websocket: WebSocket, user_id: int, message: dict):
    """Traite les messages envoyés par le client WebSocket"""
    try:
        message_type = message.get("type")
        
        if message_type == "ping":
            # Répondre au ping
            await manager.send_personal_message(websocket, {
                "type": "pong",
                "timestamp": str(int(__import__('time').time()))
            })
            logger.debug(f"Pong envoyé à user {user_id}")
            
        elif message_type == "subscribe_task":
            # Abonnement à une tâche spécifique
            task_id = message.get("task_id")
            if task_id:
                await manager.send_personal_message(websocket, {
                    "type": "subscribed",
                    "task_id": task_id,
                    "message": f"Abonné aux notifications de la tâche {task_id}"
                })
                logger.info(f"User {user_id} abonné à la tâche {task_id}")
            
        elif message_type == "request_test_notification":
            # Test de notification (pour debug)
            task_id = message.get("task_id", 999)
            await manager.send_task_notification(
                user_id=user_id,
                task_id=task_id,
                status="test",
                message="Notification de test",
                extra_data={"test": True}
            )
            logger.info(f"Notification test envoyée à user {user_id} pour tâche {task_id}")
            
        elif message_type == "get_connection_info":
            # Informations sur la connexion
            await manager.send_personal_message(websocket, {
                "type": "connection_info",
                "user_id": user_id,
                "total_user_connections": len(manager.active_connections.get(user_id, [])),
                "total_server_connections": manager.get_total_connections()
            })
            
        else:
            logger.warning(f"Type de message non reconnu de user {user_id}: {message_type}")
            
    except Exception as e:
        logger.error(f"Erreur traitement message client {user_id}: {str(e)}")

# Route pour obtenir les statistiques WebSocket (debug)
@router.get("/ws/stats")
async def websocket_stats():
    """Retourne les statistiques des connexions WebSocket"""
    return {
        "total_connections": manager.get_total_connections(),
        "connected_users": list(manager.active_connections.keys()),
        "connections_by_user": {
            user_id: len(connections) 
            for user_id, connections in manager.active_connections.items()
        },
        "redis_listener_active": manager.redis_listener_task is not None and not manager.redis_listener_task.done()
    }

# Route pour envoyer une notification de test (debug)
@router.post("/ws/test-notification/{user_id}")
async def send_test_notification(user_id: int, current_user: User = Depends(get_current_user)):
    """Envoie une notification de test via Redis (pour debug)"""
    from app.services.websocket_notifier import websocket_notifier
    
    success = websocket_notifier.send_task_notification(
        user_id=user_id,
        task_id=888,
        status="test",
        message="Test notification depuis API",
        extra_data={"api_test": True}
    )
    
    return {
        "success": success,
        "message": f"Notification test envoyée à user {user_id}",
        "active_connections": user_id in manager.active_connections
    }
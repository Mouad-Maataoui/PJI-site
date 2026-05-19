import stripe
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.repositories.user_repository import UserRepository
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.user import User
from app.monitoring.metrics import metrics

logger = logging.getLogger(__name__)

# Configuration Stripe globale
stripe.api_key = settings.STRIPE_API_KEY

class PaymentService:
    """Service pour gérer les paiements Stripe et le système de points"""
    
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository()
        self._validate_stripe_config()
    
    def _validate_stripe_config(self):
        """Valide que toutes les clés Stripe nécessaires sont configurées"""
        if not settings.STRIPE_API_KEY:
            logger.error("STRIPE_API_KEY non configurée")
            raise ValueError("STRIPE_API_KEY manquante dans la configuration")
        
        if not settings.STRIPE_WEBHOOK_SECRET:
            logger.error("STRIPE_WEBHOOK_SECRET non configurée")
            raise ValueError("STRIPE_WEBHOOK_SECRET manquante dans la configuration")
        
        logger.info("Configuration Stripe validée")
    
    def create_payment_intent(self, user_id: int, amount_euros: int = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Crée un PaymentIntent Stripe pour l'achat de points
        
        Args:
            user_id: ID de l'utilisateur
            amount_euros: Montant en euros (par défaut selon settings)
            
        Returns:
            Tuple[bool, Dict]: (success, response_data)
        """
        try:
            # Montant par défaut selon la configuration
            if amount_euros is None:
                amount_euros = settings.PURCHASE_AMOUNT_EUROS
            
            # Valider le montant
            if amount_euros != settings.PURCHASE_AMOUNT_EUROS:
                logger.warning(f"Tentative d'achat avec montant invalide: {amount_euros}€")
                return False, {
                    "error": f"Montant invalide. Seuls les achats de {settings.PURCHASE_AMOUNT_EUROS}€ sont autorisés."
                }
            
            # Récupérer l'utilisateur
            user = self.user_repo.get(self.db, user_id=user_id)
            if not user:
                logger.error(f"Utilisateur non trouvé: {user_id}")
                return False, {"error": "Utilisateur non trouvé"}
            
            # Calculer le nombre de points à attribuer
            points_to_add = settings.POINTS_PER_PURCHASE
            
            # Créer une transaction en attente dans la DB
            transaction = Transaction(
                user_id=user_id,
                type=TransactionType.PURCHASE.value,
                status=TransactionStatus.PENDING.value,
                amount=float(amount_euros),
                points=points_to_add
            )
            self.db.add(transaction)
            self.db.commit()
            self.db.refresh(transaction)
            
            # Créer le PaymentIntent Stripe
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_euros * 100,  # Stripe utilise les centimes
                currency='eur',
                metadata={
                    'user_id': str(user_id),
                    'transaction_id': str(transaction.id),
                    'points': str(points_to_add),
                    'email': user.email
                },
                description=f"Achat de {points_to_add} points pour {user.email}",
                automatic_payment_methods={
                    'enabled': True,
                }
            )
            
            # Sauvegarder l'ID Stripe dans la transaction
            transaction.stripe_payment_id = payment_intent.id
            self.db.commit()
            
            logger.info(f"PaymentIntent créé: {payment_intent.id} pour user {user_id} ({amount_euros}€ = {points_to_add} points)")
            
            # Métriques
            try:
                metrics.record_payment_intent("created")
            except Exception as metric_error:
                logger.warning(f"Erreur métrique: {metric_error}")
            
            return True, {
                "client_secret": payment_intent.client_secret,
                "payment_intent_id": payment_intent.id,
                "transaction_id": transaction.id,
                "amount_euros": amount_euros,
                "points_to_receive": points_to_add,
                "current_points": user.points_balance,
                "stripe_status": payment_intent.status
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Erreur Stripe lors création PaymentIntent: {str(e)}")
            try:
                metrics.record_payment_intent("failed")
            except:
                pass
            return False, {"error": f"Erreur de paiement Stripe: {str(e)}"}
        except Exception as e:
            logger.error(f"Erreur interne lors création PaymentIntent: {str(e)}")
            try:
                metrics.record_payment_intent("error")
            except:
                pass        
            return False, {"error": f"Erreur interne: {str(e)}"}
    
    def confirm_payment(self, payment_intent_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Confirme un paiement et ajoute les points à l'utilisateur
        
        Args:
            payment_intent_id: ID du PaymentIntent Stripe
            
        Returns:
            Tuple[bool, Dict]: (success, response_data)
        """
        try:
            # Récupérer le PaymentIntent depuis Stripe
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            logger.info(f"Confirmation paiement {payment_intent_id}, statut: {payment_intent.status}")
            
            # Vérifier que le paiement est réussi
            if payment_intent.status != 'succeeded':
                logger.warning(f"Tentative confirmation paiement non réussi: {payment_intent.status}")
                return False, {
                    "error": f"Paiement non réussi. Statut: {payment_intent.status}"
                }
            
            # Récupérer la transaction dans notre DB
            transaction = self.db.query(Transaction).filter(
                Transaction.stripe_payment_id == payment_intent_id
            ).first()
            
            if not transaction:
                logger.error(f"Transaction non trouvée pour PaymentIntent: {payment_intent_id}")
                return False, {"error": "Transaction non trouvée"}
            
            # Vérifier que la transaction n'est pas déjà traitée
            if transaction.status == TransactionStatus.COMPLETED.value:
                logger.info(f"Transaction déjà traitée: {transaction.id}")
                user = self.user_repo.get(self.db, user_id=transaction.user_id)
                return True, {
                    "message": "Transaction déjà traitée",
                    "transaction_id": transaction.id,
                    "points_added": transaction.points,
                    "current_balance": user.points_balance if user else 0,
                    "amount_paid": transaction.amount
                }
            
            # Récupérer l'utilisateur
            user = self.user_repo.get(self.db, user_id=transaction.user_id)
            if not user:
                logger.error(f"Utilisateur non trouvé: {transaction.user_id}")
                return False, {"error": "Utilisateur non trouvé"}
            
            # Ajouter les points à l'utilisateur
            old_balance = user.points_balance
            user = self.user_repo.update_points_balance(
                self.db,
                user_id=user.id,
                points_delta=transaction.points
            )
            
            # Marquer la transaction comme terminée
            transaction.status = TransactionStatus.COMPLETED.value
            transaction.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            
            logger.info(f"Paiement confirmé: user {user.id}, +{transaction.points} points ({old_balance} → {user.points_balance})")
            
            # Métriques
            try:
                metrics.record_payment_completed(transaction.amount, transaction.points)
            except Exception as metric_error:
                logger.warning(f"Erreur métrique: {metric_error}")
                        
            return True, {
                "transaction_id": transaction.id,
                "points_added": transaction.points,
                "old_balance": old_balance,
                "new_balance": user.points_balance,
                "amount_paid": transaction.amount,
                "stripe_payment_id": payment_intent_id
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Erreur Stripe lors confirmation: {str(e)}")
            return False, {"error": f"Erreur Stripe: {str(e)}"}
        except Exception as e:
            logger.error(f"Erreur interne lors confirmation: {str(e)}")
            return False, {"error": f"Erreur interne: {str(e)}"}
    
    def handle_webhook(self, payload: bytes, signature: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Traite les webhooks Stripe (version optimisée pour Stripe 7.9.0)
        
        Args:
            payload: Corps de la requête webhook
            signature: Signature Stripe
            
        Returns:
            Tuple[bool, Dict]: (success, response_data)
        """
        try:
            logger.info(f"📡 Webhook reçu: {len(payload)} bytes, signature: {signature[:50]}...")
            
            # Vérifier la signature du webhook
            event = stripe.Webhook.construct_event(
                payload, 
                signature, 
                settings.STRIPE_WEBHOOK_SECRET
            )
            
            event_type = event['type']
            event_id = event.get('id', 'unknown')
            
            logger.info(f"Événement webhook: {event_type} (ID: {event_id})")
            
            # Traiter les événements pertinents
            if event_type == 'payment_intent.succeeded':
                payment_intent = event['data']['object']
                payment_intent_id = payment_intent['id']
                
                logger.info(f"Paiement réussi webhook: {payment_intent_id}")
                success, result = self.confirm_payment(payment_intent_id)
                
                return success, {
                    "event_type": event_type,
                    "event_id": event_id,
                    "payment_intent_id": payment_intent_id,
                    "processed": success,
                    "result": result
                }
            
            elif event_type == 'payment_intent.payment_failed':
                payment_intent = event['data']['object']
                payment_intent_id = payment_intent['id']
                
                logger.warning(f"Paiement échoué webhook: {payment_intent_id}")
                success, result = self.handle_payment_failure(payment_intent_id)
                
                return success, {
                    "event_type": event_type,
                    "event_id": event_id,
                    "payment_intent_id": payment_intent_id,
                    "processed": success,
                    "result": result
                }
            
            elif event_type == 'payment_intent.requires_action':
                payment_intent = event['data']['object']
                payment_intent_id = payment_intent['id']
                
                logger.info(f"Paiement nécessite action: {payment_intent_id}")
                return True, {
                    "event_type": event_type,
                    "event_id": event_id,
                    "payment_intent_id": payment_intent_id,
                    "processed": False,
                    "message": "Paiement en attente d'action utilisateur"
                }
            
            else:
                # Événement non traité mais valide
                logger.info(f"Événement webhook non traité: {event_type}")
                return True, {
                    "event_type": event_type,
                    "event_id": event_id,
                    "processed": False,
                    "message": f"Événement {event_type} ignoré"
                }
                
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Signature webhook invalide: {str(e)}")
            return False, {"error": "Signature webhook invalide"}
        except Exception as e:
            logger.error(f"Erreur webhook: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False, {"error": f"Erreur traitement webhook: {str(e)}"}
    
    def handle_payment_failure(self, payment_intent_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Traite l'échec d'un paiement
        
        Args:
            payment_intent_id: ID du PaymentIntent qui a échoué
            
        Returns:
            Tuple[bool, Dict]: (success, response_data)
        """
        try:
            # Trouver la transaction correspondante
            transaction = self.db.query(Transaction).filter(
                Transaction.stripe_payment_id == payment_intent_id
            ).first()
            
            if transaction:
                # Marquer la transaction comme échouée si elle ne l'est pas déjà
                if transaction.status != TransactionStatus.FAILED.value:
                    transaction.status = TransactionStatus.FAILED.value
                    transaction.updated_at = datetime.now(timezone.utc)
                    self.db.commit()
                    
                    logger.warning(f"Transaction marquée comme échouée: {transaction.id}")
                
                return True, {
                    "transaction_id": transaction.id,
                    "status": "failed",
                    "payment_intent_id": payment_intent_id
                }
            else:
                logger.warning(f"Transaction non trouvée pour échec: {payment_intent_id}")
                return False, {"error": "Transaction non trouvée"}
                
        except Exception as e:
            logger.error(f"Erreur traitement échec paiement: {str(e)}")
            return False, {"error": str(e)}
    
    def deduct_points_for_processing(self, user_id: int, task_id: int) -> Tuple[bool, Dict[str, Any]]:
        """
        Déduit des points pour un traitement d'image
        
        Args:
            user_id: ID de l'utilisateur
            task_id: ID de la tâche d'image
            
        Returns:
            Tuple[bool, Dict]: (success, response_data)
        """
        try:
            # Récupérer l'utilisateur
            user = self.user_repo.get(self.db, user_id=user_id)
            if not user:
                logger.error(f"Utilisateur non trouvé pour déduction: {user_id}")
                return False, {"error": "Utilisateur non trouvé"}
            
            # Vérifier que l'utilisateur a assez de points
            points_needed = settings.POINTS_COST_PER_IMAGE
            if user.points_balance < points_needed:
                logger.warning(f"Points insuffisants pour user {user_id}: {user.points_balance} < {points_needed}")
                return False, {
                    "error": f"Points insuffisants. Requis: {points_needed}, disponibles: {user.points_balance}",
                    "points_needed": points_needed,
                    "points_available": user.points_balance,
                    "points_missing": points_needed - user.points_balance
                }
            
            # Créer une transaction d'usage
            transaction = Transaction(
                user_id=user_id,
                type=TransactionType.USAGE.value,
                status=TransactionStatus.COMPLETED.value,
                points=-points_needed,  # Négatif pour déduction
                image_task_id=task_id
            )
            self.db.add(transaction)
            
            # Déduire les points
            old_balance = user.points_balance
            user = self.user_repo.update_points_balance(
                self.db,
                user_id=user_id,
                points_delta=-points_needed
            )
            
            self.db.commit()
            
            logger.info(f"Points déduits: user {user_id}, -{points_needed} points pour tâche {task_id} ({old_balance} → {user.points_balance})")
            
            # Métriques
            try:
                metrics.record_points_spent(points_needed)
            except Exception as metric_error:
                logger.warning(f"Erreur métrique: {metric_error}")
            
            return True, {
                "transaction_id": transaction.id,
                "points_deducted": points_needed,
                "old_balance": old_balance,
                "new_balance": user.points_balance,
                "task_id": task_id
            }
            
        except Exception as e:
            logger.error(f"Erreur déduction points: {str(e)}")
            return False, {"error": str(e)}
    
    def get_user_transactions(self, user_id: int, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        Récupère l'historique des transactions d'un utilisateur
        
        Args:
            user_id: ID de l'utilisateur
            limit: Nombre maximum de transactions
            offset: Décalage pour pagination
            
        Returns:
            Dict avec les transactions et métadonnées
        """
        try:
            # Limiter la requête pour éviter les abus
            limit = min(limit, 100)
            
            transactions = self.db.query(Transaction)\
                .filter(Transaction.user_id == user_id)\
                .order_by(Transaction.created_at.desc())\
                .offset(offset)\
                .limit(limit)\
                .all()
            
            transactions_data = []
            for tx in transactions:
                transactions_data.append({
                    "id": tx.id,
                    "type": tx.type,
                    "status": tx.status,
                    "points": tx.points,
                    "amount": tx.amount,
                    "created_at": tx.created_at.isoformat(),
                    "updated_at": tx.updated_at.isoformat() if tx.updated_at else None,
                    "stripe_payment_id": tx.stripe_payment_id,
                    "image_task_id": tx.image_task_id
                })
            
            # Compter le total pour la pagination
            total_count = self.db.query(Transaction)\
                .filter(Transaction.user_id == user_id)\
                .count()
            
            return {
                "transactions": transactions_data,
                "total": len(transactions_data),
                "total_count": total_count,
                "offset": offset,
                "limit": limit,
                "has_more": (offset + len(transactions_data)) < total_count
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération transactions: {str(e)}")
            return {
                "transactions": [], 
                "error": str(e),
                "total": 0,
                "total_count": 0,
                "offset": offset,
                "limit": limit,
                "has_more": False
            }
    
    def get_payment_stats(self) -> Dict[str, Any]:
        """
        Récupère des statistiques sur les paiements
        
        Returns:
            Dict avec les statistiques
        """
        try:
            # Statistiques des transactions
            total_purchases = self.db.query(Transaction)\
                .filter(Transaction.type == TransactionType.PURCHASE.value)\
                .filter(Transaction.status == TransactionStatus.COMPLETED.value)\
                .count()
            
            total_pending = self.db.query(Transaction)\
                .filter(Transaction.type == TransactionType.PURCHASE.value)\
                .filter(Transaction.status == TransactionStatus.PENDING.value)\
                .count()
            
            total_failed = self.db.query(Transaction)\
                .filter(Transaction.type == TransactionType.PURCHASE.value)\
                .filter(Transaction.status == TransactionStatus.FAILED.value)\
                .count()
            
            total_usage = self.db.query(Transaction)\
                .filter(Transaction.type == TransactionType.USAGE.value)\
                .count()
            
            # Revenus totaux
            revenue_result = self.db.query(Transaction)\
                .filter(Transaction.type == TransactionType.PURCHASE.value)\
                .filter(Transaction.status == TransactionStatus.COMPLETED.value)\
                .with_entities(Transaction.amount)\
                .all()
            
            revenue_sum = sum(tx.amount for tx in revenue_result if tx.amount)
            
            # Points totaux distribués
            points_result = self.db.query(Transaction)\
                .filter(Transaction.type == TransactionType.PURCHASE.value)\
                .filter(Transaction.status == TransactionStatus.COMPLETED.value)\
                .with_entities(Transaction.points)\
                .all()
            
            points_distributed = sum(tx.points for tx in points_result if tx.points)
            
            # Points totaux utilisés
            usage_result = self.db.query(Transaction)\
                .filter(Transaction.type == TransactionType.USAGE.value)\
                .with_entities(Transaction.points)\
                .all()
            
            points_used = abs(sum(tx.points for tx in usage_result if tx.points))
            
            return {
                "total_purchases": total_purchases,
                "total_pending": total_pending,
                "total_failed": total_failed,
                "total_usage_transactions": total_usage,
                "total_revenue_euros": round(revenue_sum, 2),
                "points_distributed": points_distributed,
                "points_used": points_used,
                "points_remaining": points_distributed - points_used,
                "success_rate": round((total_purchases / max(total_purchases + total_failed, 1)) * 100, 2),
                "config": {
                    "points_per_purchase": settings.POINTS_PER_PURCHASE,
                    "cost_per_image": settings.POINTS_COST_PER_IMAGE,
                    "purchase_amount": settings.PURCHASE_AMOUNT_EUROS
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur statistiques paiements: {str(e)}")
            return {"error": str(e)}

# Fonction d'injection de dépendance
def get_payment_service(db: Session) -> PaymentService:
    """Retourne une instance du service de paiement"""
    return PaymentService(db)
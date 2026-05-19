import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth_service import get_current_user
from app.models.user import User
from app.core.config import settings
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.db.repositories.user_repository import UserRepository
from datetime import datetime

# Import local pour éviter les imports circulaires
def get_payment_service(db: Session = Depends(get_db)):
    """Fonction pour obtenir le service de paiement"""
    from app.services.payment_service import PaymentService
    return PaymentService(db)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/balance")
async def get_points_balance(
    current_user: User = Depends(get_current_user)
):
    """
    Récupère le solde de points de l'utilisateur actuel
    """
    try:
        return {
            "success": True,
            "user_id": current_user.id,
            "points_balance": current_user.points_balance,
            "email": current_user.email,
            "system_config": {
                "cost_per_image": settings.POINTS_COST_PER_IMAGE,
                "points_per_purchase": settings.POINTS_PER_PURCHASE,
                "purchase_amount_euros": settings.PURCHASE_AMOUNT_EUROS
            },
            "user_stats": {
                "can_process_images": current_user.points_balance >= settings.POINTS_COST_PER_IMAGE,
                "images_possible": current_user.points_balance // settings.POINTS_COST_PER_IMAGE
            }
        }
    except Exception as e:
        logger.error(f"Erreur récupération balance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération du solde"
        )

@router.post("/purchase/create-intent")
async def create_payment_intent(
    current_user: User = Depends(get_current_user),
    payment_service = Depends(get_payment_service)
):
    """
    Crée un PaymentIntent Stripe pour acheter des points
    """
    try:
        logger.info(f"Création PaymentIntent pour user {current_user.id}")
        
        success, result = payment_service.create_payment_intent(current_user.id)
        
        if success:
            logger.info(f"PaymentIntent créé: {result.get('payment_intent_id')}")
            return {
                "success": True,
                "payment_data": result,
                "stripe_publishable_key": getattr(settings, 'STRIPE_PUBLISHABLE_KEY', ''),
                "message": f"PaymentIntent créé pour {settings.PURCHASE_AMOUNT_EUROS}€ = {settings.POINTS_PER_PURCHASE} points"
            }
        else:
            logger.error(f"Échec création PaymentIntent: {result}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Erreur lors de la création du paiement")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur inattendue création PaymentIntent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la création du paiement"
        )

@router.post("/purchase/confirm")
async def confirm_payment(
    payment_intent_id: str,
    current_user: User = Depends(get_current_user),
    payment_service = Depends(get_payment_service)
):
    """
    Confirme un paiement et ajoute les points (appelé par le frontend après paiement réussi)
    """
    try:
        logger.info(f"Confirmation paiement {payment_intent_id} pour user {current_user.id}")
        
        success, result = payment_service.confirm_payment(payment_intent_id)
        
        if success:
            logger.info(f"Paiement confirmé: +{result.get('points_added')} points")
            return {
                "success": True,
                "message": f"Paiement confirmé ! +{result['points_added']} points ajoutés",
                "payment_data": result
            }
        else:
            logger.error(f"Échec confirmation paiement: {result}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Erreur lors de la confirmation du paiement")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur inattendue confirmation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la confirmation"
        )

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    payment_service = Depends(get_payment_service)
):
    """
    Endpoint pour recevoir les webhooks Stripe (version optimisée)
    """
    try:
        logger.info("Webhook Stripe reçu")
        
        # Récupérer le payload et la signature
        payload = await request.body()
        signature = request.headers.get("stripe-signature")
        
        if not signature:
            logger.error("Signature Stripe manquante")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signature Stripe manquante"
            )
        
        # Traiter le webhook
        success, result = payment_service.handle_webhook(payload, signature)
        
        if success:
            logger.info(f"Webhook traité: {result.get('event_type', 'unknown')}")
            return {"received": True, "processed": result}
        else:
            logger.error(f"Erreur webhook: {result}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Erreur traitement webhook")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur webhook inattendue: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne webhook"
        )

@router.get("/transactions")
async def get_user_transactions(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    payment_service = Depends(get_payment_service)
):
    """
    Récupère l'historique des transactions de l'utilisateur
    """
    try:
        logger.info(f"Récupération transactions pour user {current_user.id}")
        
        # Valider les paramètres
        if limit > 100:
            limit = 100
        if skip < 0:
            skip = 0
        
        transactions_data = payment_service.get_user_transactions(
            user_id=current_user.id,
            limit=limit,
            offset=skip
        )
        
        return {
            "success": True,
            "user_id": current_user.id,
            "current_balance": current_user.points_balance,
            **transactions_data
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération transactions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des transactions"
        )

@router.get("/pricing")
async def get_pricing_info():
    """
    Récupère les informations de tarification
    """
    try:
        return {
            "success": True,
            "points_system": {
                "purchase_amount_euros": settings.PURCHASE_AMOUNT_EUROS,
                "points_per_purchase": settings.POINTS_PER_PURCHASE,
                "points_cost_per_image": settings.POINTS_COST_PER_IMAGE,
                "cost_per_image_euros": round(
                    settings.PURCHASE_AMOUNT_EUROS / settings.POINTS_PER_PURCHASE * settings.POINTS_COST_PER_IMAGE, 
                    2
                )
            },
            "examples": {
                "single_purchase": f"{settings.PURCHASE_AMOUNT_EUROS}€ = {settings.POINTS_PER_PURCHASE} points = {settings.POINTS_PER_PURCHASE // settings.POINTS_COST_PER_IMAGE} images",
                "cost_per_image": f"{round(settings.PURCHASE_AMOUNT_EUROS / settings.POINTS_PER_PURCHASE * settings.POINTS_COST_PER_IMAGE, 2)}€ par image"
            },
            "stripe_config": {
                "publishable_key": getattr(settings, 'STRIPE_PUBLISHABLE_KEY', ''),
                "currency": "eur"
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération tarifs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des tarifs"
        )

@router.post("/deduct")
async def deduct_points_for_image(
    task_id: int,
    current_user: User = Depends(get_current_user),
    payment_service = Depends(get_payment_service)
):
    """
    Déduit des points pour un traitement d'image (utilisé en interne)
    """
    try:
        logger.info(f"Déduction points pour tâche {task_id}, user {current_user.id}")
        
        success, result = payment_service.deduct_points_for_processing(
            user_id=current_user.id,
            task_id=task_id
        )
        
        if success:
            logger.info(f"Points déduits: -{result.get('points_deducted')}")
            return {
                "success": True,
                "message": f"Points déduits pour le traitement de l'image",
                "deduction_data": result
            }
        else:
            logger.warning(f"Échec déduction points: {result}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Erreur lors de la déduction des points")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur inattendue déduction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la déduction"
        )

@router.get("/stats")
async def get_payment_stats(
    current_user: User = Depends(get_current_user),
    payment_service = Depends(get_payment_service)
):
    """
    Récupère des statistiques sur les paiements
    """
    try:
        logger.info(f"Récupération stats pour user {current_user.id}")
        
        # Dans une vraie application, vous devriez vérifier les permissions admin ici
        # Pour l'instant, on retourne les stats pour tous les utilisateurs connectés
        
        stats = payment_service.get_payment_stats()
        
        return {
            "success": True,
            "global_stats": stats,
            "user_stats": {
                "current_balance": current_user.points_balance,
                "user_id": current_user.id,
                "can_process": current_user.points_balance >= settings.POINTS_COST_PER_IMAGE,
                "images_remaining": current_user.points_balance // settings.POINTS_COST_PER_IMAGE
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des statistiques"
        )

@router.get("/can-process")
async def check_can_process_image(
    current_user: User = Depends(get_current_user)
):
    """
    Vérifie si l'utilisateur peut traiter une image (a assez de points)
    """
    try:
        points_needed = settings.POINTS_COST_PER_IMAGE
        has_enough_points = current_user.points_balance >= points_needed
        
        return {
            "success": True,
            "can_process": has_enough_points,
            "current_balance": current_user.points_balance,
            "points_needed": points_needed,
            "points_missing": max(0, points_needed - current_user.points_balance),
            "images_possible": current_user.points_balance // points_needed,
            "message": "Traitement possible" if has_enough_points else f"Points insuffisants. Il vous faut {points_needed - current_user.points_balance} point(s) supplémentaire(s)."
        }
        
    except Exception as e:
        logger.error(f"Erreur vérification points: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la vérification des points"
        )

# Routes de test (à supprimer en production)
@router.post("/test/simulate-payment-success")
async def simulate_payment_success_for_test(
    payment_intent_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ROUTE DE TEST UNIQUEMENT - Simule un paiement réussi EN FORÇANT LE SUCCÈS
    ⚠️ À SUPPRIMER EN PRODUCTION
    """
    try:
        logger.info(f"[TEST] Simulation paiement réussi: {payment_intent_id}")
        
        # Récupérer le PaymentIntent depuis Stripe (juste pour vérifier qu'il existe)
        import stripe
        stripe.api_key = settings.STRIPE_API_KEY
        
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            logger.info(f"PaymentIntent récupéré: {payment_intent.status}")
        except stripe.error.InvalidRequestError:
            raise HTTPException(
                status_code=404,
                detail="PaymentIntent non trouvé"
            )
        
        # Trouver la transaction dans notre DB
        transaction = db.query(Transaction).filter(
            Transaction.stripe_payment_id == payment_intent_id
        ).first()
        
        if not transaction:
            raise HTTPException(
                status_code=404,
                detail="Transaction non trouvée"
            )
        
        # Vérifier que c'est bien l'utilisateur propriétaire
        if transaction.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Transaction non autorisée"
            )
        
        # SIMULATION : Marquer comme réussi dans notre système
        # (peu importe le statut Stripe réel)
        
        # Récupérer l'utilisateur
        from app.db.repositories.user_repository import UserRepository
        user_repo = UserRepository()
        user = user_repo.get(db, user_id=transaction.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        # Vérifier que la transaction n'est pas déjà traitée
        if transaction.status == TransactionStatus.COMPLETED.value:
            logger.info(f"Transaction déjà traitée: {transaction.id}")
            return {
                "success": True,
                "message": "[TEST] Transaction déjà traitée",
                "payment_data": {
                    "transaction_id": transaction.id,
                    "points_added": transaction.points,
                    "new_balance": user.points_balance,
                    "amount_paid": transaction.amount,
                    "stripe_status": payment_intent.status,
                    "test_mode": True,
                    "already_processed": True
                }
            }
        
        # FORCER LE SUCCÈS : Ajouter les points à l'utilisateur
        old_balance = user.points_balance
        user = user_repo.update_points_balance(
            db,
            user_id=user.id,
            points_delta=transaction.points
        )
        
        # Marquer la transaction comme terminée
        transaction.status = TransactionStatus.COMPLETED.value
        transaction.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"[TEST] Paiement forcé: user {user.id}, +{transaction.points} points ({old_balance} → {user.points_balance})")
        
        # Métriques (si disponibles)
        try:
            from app.monitoring.metrics import metrics
            metrics.record_payment_completed(transaction.amount, transaction.points)
        except:
            pass
        
        return {
            "success": True,
            "message": f"[TEST] Paiement simulé avec succès ! +{transaction.points} points ajoutés",
            "payment_data": {
                "transaction_id": transaction.id,
                "points_added": transaction.points,
                "old_balance": old_balance,
                "new_balance": user.points_balance,
                "amount_paid": transaction.amount,
                "stripe_status": payment_intent.status,
                "real_stripe_status": payment_intent.status,
                "test_mode": True,
                "forced_success": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur simulation test: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur simulation: {str(e)}"
        )
        
@router.get("/test/webhook-info")
async def get_webhook_test_info():
    """
    ROUTE DE TEST - Informations pour tester les webhooks
    ⚠️ À SUPPRIMER EN PRODUCTION
    """
    try:
        return {
            "webhook_url": "/api/v1/points/webhook",
            "required_headers": {
                "stripe-signature": "Signature du webhook Stripe"
            },
            "stripe_cli_command": "stripe listen --forward-to localhost:8000/api/v1/points/webhook",
            "test_events": [
                "payment_intent.succeeded",
                "payment_intent.payment_failed", 
                "payment_intent.requires_action"
            ],
            "webhook_secret_configured": bool(getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)),
            "api_key_configured": bool(getattr(settings, 'STRIPE_API_KEY', None))
        }
    except Exception as e:
        logger.error(f"Erreur info webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
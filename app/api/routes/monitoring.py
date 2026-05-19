# app/api/routes/monitoring.py
"""
Routes pour le monitoring et les métriques Prometheus
"""

from fastapi import APIRouter, Response, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.db.session import get_db
from app.monitoring.metrics import get_metrics, metrics
from app.models.user import User
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.image_task import ImageTask, ProcessingStatus

router = APIRouter()

@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """
    Endpoint pour exposer les métriques Prometheus
    """
    return get_metrics()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Endpoint de vérification de santé avec mise à jour des métriques
    """
    try:
        # Test de connexion à la base de données
        db.execute("SELECT 1")
        
        # Test Redis (optionnel)
        try:
            import redis
            from app.core.config import settings
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                socket_timeout=1
            )
            r.ping()
            redis_ok = True
        except:
            redis_ok = False
        
        # Calculer et mettre à jour les métriques utilisateurs
        await update_user_metrics(db)
        
        # Marquer l'application comme saine
        metrics.set_app_health(True)
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": "ok",
                "redis": "ok" if redis_ok else "warning"
            }
        }
        
    except Exception as e:
        # Marquer l'application comme malsaine
        metrics.set_app_health(False)
        
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.get("/metrics/business")
async def business_metrics(db: Session = Depends(get_db)):
    """
    Endpoint pour récupérer les métriques métier en JSON
    (utile pour des dashboards custom)
    """
    try:
        # Calculs des métriques métier
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)
        
        # Statistiques de paiements
        total_revenue = db.query(Transaction)\
            .filter(Transaction.type == TransactionType.PURCHASE.value)\
            .filter(Transaction.status == TransactionStatus.COMPLETED.value)\
            .with_entities(Transaction.amount)\
            .all()
        
        revenue_sum = sum(tx.amount for tx in total_revenue if tx.amount)
        
        # Revenus par période
        revenue_24h = db.query(Transaction)\
            .filter(Transaction.type == TransactionType.PURCHASE.value)\
            .filter(Transaction.status == TransactionStatus.COMPLETED.value)\
            .filter(Transaction.created_at >= last_24h)\
            .with_entities(Transaction.amount)\
            .all()
        
        revenue_24h_sum = sum(tx.amount for tx in revenue_24h if tx.amount)
        
        # Images traitées
        total_images = db.query(ImageTask).count()
        images_completed = db.query(ImageTask)\
            .filter(ImageTask.status == ProcessingStatus.COMPLETED.value)\
            .count()
        
        images_24h = db.query(ImageTask)\
            .filter(ImageTask.created_at >= last_24h)\
            .count()
        
        # Utilisateurs
        total_users = db.query(User).count()
        active_users_24h = db.query(User)\
            .filter(User.last_login >= last_24h)\
            .count() if hasattr(User, 'last_login') else 0
        
        # Points
        total_points_purchased = db.query(Transaction)\
            .filter(Transaction.type == TransactionType.PURCHASE.value)\
            .filter(Transaction.status == TransactionStatus.COMPLETED.value)\
            .with_entities(Transaction.points)\
            .all()
        
        points_purchased_sum = sum(tx.points for tx in total_points_purchased if tx.points > 0)
        
        total_points_spent = db.query(Transaction)\
            .filter(Transaction.type == TransactionType.USAGE.value)\
            .with_entities(Transaction.points)\
            .all()
        
        points_spent_sum = abs(sum(tx.points for tx in total_points_spent if tx.points < 0))
        
        return {
            "timestamp": now.isoformat(),
            "revenue": {
                "total_euros": round(revenue_sum, 2),
                "last_24h_euros": round(revenue_24h_sum, 2),
                "total_transactions": len(total_revenue)
            },
            "images": {
                "total_processed": total_images,
                "completed": images_completed,
                "success_rate": round((images_completed / total_images * 100) if total_images > 0 else 0, 1),
                "last_24h": images_24h
            },
            "users": {
                "total": total_users,
                "active_24h": active_users_24h,
                "activity_rate": round((active_users_24h / total_users * 100) if total_users > 0 else 0, 1)
            },
            "points": {
                "total_purchased": points_purchased_sum,
                "total_spent": points_spent_sum,
                "balance": points_purchased_sum - points_spent_sum
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur récupération métriques métier: {str(e)}"
        )

@router.post("/metrics/refresh")
async def refresh_metrics(db: Session = Depends(get_db)):
    """
    Force le rafraîchissement de toutes les métriques
    """
    try:
        await update_user_metrics(db)
        await update_business_metrics(db)
        
        return {
            "status": "success",
            "message": "Métriques rafraîchies",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur rafraîchissement métriques: {str(e)}"
        )

# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

async def update_user_metrics(db: Session):
    """Met à jour les métriques utilisateurs"""
    try:
        total_users = db.query(User).count()
        
        # Utilisateurs actifs dans les dernières 24h
        last_24h = datetime.utcnow() - timedelta(hours=24)
        active_24h = 0
        
        if hasattr(User, 'last_login'):
            active_24h = db.query(User)\
                .filter(User.last_login >= last_24h)\
                .count()
        
        metrics.update_user_counts(total_users, active_24h)
        
    except Exception as e:
        print(f"Erreur mise à jour métriques utilisateurs: {e}")

async def update_business_metrics(db: Session):
    """Met à jour les métriques métier depuis la base de données"""
    try:
        # Cette fonction peut être appelée périodiquement
        # pour synchroniser les métriques avec la réalité de la DB
        
        # Compter les revenus totaux
        total_revenue = db.query(Transaction)\
            .filter(Transaction.type == TransactionType.PURCHASE.value)\
            .filter(Transaction.status == TransactionStatus.COMPLETED.value)\
            .with_entities(Transaction.amount)\
            .all()
        
        # Note: Prometheus ne supporte pas la "réinitialisation" des compteurs
        # Donc on ne met à jour que les gauges ici
        
    except Exception as e:
        print(f"Erreur mise à jour métriques métier: {e}")
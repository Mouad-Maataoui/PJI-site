from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base


class TransactionType(str, enum.Enum):
    PURCHASE = "purchase"
    USAGE = "usage"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    type = Column(String, nullable=False)  # Utiliser String au lieu de Enum
    status = Column(String, default=TransactionStatus.PENDING.value)  # Utiliser .value
    amount = Column(Float, nullable=True)  # Montant en euros pour les achats
    points = Column(Integer, nullable=False)  # Points ajoutés ou retirés
    stripe_payment_id = Column(String, nullable=True)  # Pour les achats via Stripe
    image_task_id = Column(Integer, ForeignKey("image_tasks.id", ondelete="SET NULL"), nullable=True)  # Pour les usages
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Définir la relation inverse
    user = relationship("User", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction(id={self.id}, user_id={self.user_id}, type={self.type}, points={self.points})>"
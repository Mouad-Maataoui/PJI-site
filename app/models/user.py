from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    points_balance = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)  # Ajouté pour la sécurité
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    images = relationship("ImageTask", back_populates="owner")
    transactions = relationship("Transaction", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, points={self.points_balance})>"
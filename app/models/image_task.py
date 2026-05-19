from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base

class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ImageTask(Base):
    __tablename__ = "image_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    original_filename = Column(String, nullable=False)
    
    # Chemins locaux temporaires (supprimés après traitement)
    original_file_path = Column(String, nullable=False)
    compressed_file_path = Column(String, nullable=True)
    processed_file_path = Column(String, nullable=True)
    
    # URLs de stockage cloud permanent
    cloud_original_url = Column(String, nullable=True, index=True)
    cloud_processed_url = Column(String, nullable=True, index=True)
    
    # Gestion du nettoyage local
    local_cleanup_done = Column(Boolean, default=False, nullable=False, index=True)
    
    # Status et métadonnées
    status = Column(String, default=ProcessingStatus.PENDING.value)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    expire_at = Column(DateTime(timezone=True))
    
    # Relations
    owner = relationship("User", back_populates="images")
    
    def __repr__(self):
        return f"<ImageTask(id={self.id}, user_id={self.user_id}, status={self.status}, cloud_original_url={self.cloud_original_url}, cloud_processed_url={self.cloud_processed_url})>"
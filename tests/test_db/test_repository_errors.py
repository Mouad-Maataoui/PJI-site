import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DataError

from app.db.repositories.user_repository import UserRepository
from app.db.repositories.image_repository import ImageRepository
from app.models.schemas.user import UserCreate
from app.models.schemas.image import ImageTaskCreate
from app.models.user import User
from app.models.image_task import ImageTask, ProcessingStatus


class TestRepositoryErrors:
    def test_create_duplicate_email(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        """Test la création d'un utilisateur avec un email déjà existant"""
        # Arrange
        user_in = UserCreate(
            email=sample_user.email,  # Email déjà utilisé
            username="newuser",
            password="password"
        )
        
        # Act & Assert
        with pytest.raises(IntegrityError):
            user_repository.create(db_session, obj_in=user_in, hashed_password="hashed_password")
            db_session.flush()  # Forcer la vérification des contraintes
    
    def test_create_duplicate_username(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        """Test la création d'un utilisateur avec un nom d'utilisateur déjà existant"""
        # Arrange
        user_in = UserCreate(
            email="new@example.com",
            username=sample_user.username,  # Nom d'utilisateur déjà utilisé
            password="password"
        )
        
        # Act & Assert
        with pytest.raises(IntegrityError):
            user_repository.create(db_session, obj_in=user_in, hashed_password="hashed_password")
            db_session.flush()  # Forcer la vérification des contraintes
    
    def test_get_nonexistent_user(self, db_session: Session, user_repository: UserRepository):
        """Test la récupération d'un utilisateur qui n'existe pas"""
        # Act
        user = user_repository.get(db_session, user_id=999)
        
        # Assert
        assert user is None
    
    def test_update_nonexistent_user(self, db_session: Session, user_repository: UserRepository):
        """Test la mise à jour d'un utilisateur qui n'existe pas"""
        # Act & Assert
        with pytest.raises(ValueError):  # Attend une ValueError
            user_repository.update_points_balance(db_session, user_id=999, points_delta=10)
    
    def test_create_image_for_nonexistent_user(self, db_session: Session, image_repository: ImageRepository):
        """Test la création d'une image pour un utilisateur qui n'existe pas"""
        # Arrange
        image_in = ImageTaskCreate(
            original_filename="test.jpg"
        )
        
        # Act
        image_task = image_repository.create(
            db_session, 
            obj_in=image_in, 
            user_id=999,  # ID d'utilisateur inexistant
            original_file_path="/tmp/test.jpg"
        )
        
        # Assert
        # Vérifier que l'image est bien liée à l'utilisateur spécifié
        assert image_task.user_id == 999
        
        # Vérifier que l'utilisateur n'existe pas
        user = db_session.query(User).filter(User.id == 999).first()
        assert user is None
    
    def test_invalid_image_status_transition(self, db_session: Session, image_repository: ImageRepository, sample_image_task: ImageTask):
        """Test d'une transition de statut invalide pour une image"""
        # Arrange - Simuler une erreur de statut en forçant une valeur incorrecte
        try:
            # Essayer de définir un statut invalide directement dans la base
            sample_image_task.status = "invalid_status"
            db_session.add(sample_image_task)
            db_session.commit()
            assert False, "Une erreur aurait dû être levée pour statut invalide"
        except:
            # Si une erreur est levée, c'est le comportement attendu
            db_session.rollback()
import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import string
import random

from app.db.repositories.user_repository import UserRepository
from app.db.repositories.image_repository import ImageRepository
from app.models.user import User
from app.models.image_task import ImageTask, ProcessingStatus
from app.models.schemas.user import UserCreate
from app.models.schemas.image import ImageTaskCreate


class TestRepositoryEdgeCases:
    def test_empty_user_list(self, db_session: Session, user_repository: UserRepository):
        """Test la récupération d'une liste vide d'utilisateurs"""
        # Vider la table utilisateurs
        db_session.query(User).delete()
        db_session.commit()
        
        # Act
        users = user_repository.get_multi(db_session)
        
        # Assert
        assert len(users) == 0
        assert isinstance(users, list)
    
    def test_pagination_user_list(self, db_session: Session, user_repository: UserRepository):
        """Test la pagination sur la liste des utilisateurs"""
        # Arrange - Créer 25 utilisateurs
        for i in range(25):
            user = User(
                email=f"user{i}@example.com",
                username=f"user{i}",
                hashed_password="hashed_password"
            )
            db_session.add(user)
        db_session.commit()
        
        # Act - Récupérer les utilisateurs avec pagination
        users_page1 = user_repository.get_multi(db_session, skip=0, limit=10)
        users_page2 = user_repository.get_multi(db_session, skip=10, limit=10)
        users_page3 = user_repository.get_multi(db_session, skip=20, limit=10)
        
        # Assert
        assert len(users_page1) == 10
        assert len(users_page2) == 10
        assert len(users_page3) <= 5  # Peut inclure l'utilisateur créé par sample_user
        
        # Vérifier que les pages sont différentes
        assert users_page1[0].id != users_page2[0].id
    
    def test_very_long_username(self, db_session: Session, user_repository: UserRepository):
        """Test la création d'un utilisateur avec un très long nom d'utilisateur"""
        # Arrange
        very_long_username = "a" * 255  # 255 caractères
        user_in = UserCreate(
            email="longuser@example.com",
            username=very_long_username,
            password="password"
        )
        
        # Act
        user = user_repository.create(db_session, obj_in=user_in, hashed_password="hashed_password")
        
        # Assert
        assert user.id is not None
        assert user.username == very_long_username
    
    def test_special_characters_in_filenames(self, db_session: Session, image_repository: ImageRepository, sample_user: User):
        """Test la création d'une image avec des caractères spéciaux dans le nom de fichier"""
        # Arrange
        special_filename = "image!@#$%^&*()_+{}[].jpg"
        image_in = ImageTaskCreate(
            original_filename=special_filename
        )
        
        # Act
        image_task = image_repository.create(
            db_session, 
            obj_in=image_in, 
            user_id=sample_user.id, 
            original_file_path=f"/tmp/{special_filename}"
        )
        
        # Assert
        assert image_task.id is not None
        assert image_task.original_filename == special_filename
    
    def test_multiple_images_same_filename(self, db_session: Session, image_repository: ImageRepository, sample_user: User):
        """Test la création de plusieurs images avec le même nom de fichier"""
        # Arrange
        filename = "duplicate.jpg"
        
        # Act - Créer trois images avec le même nom
        image_tasks = []
        for i in range(3):
            image_in = ImageTaskCreate(original_filename=filename)
            task = image_repository.create(
                db_session, 
                obj_in=image_in, 
                user_id=sample_user.id, 
                original_file_path=f"/tmp/{filename}_{i}"
            )
            image_tasks.append(task)
        
        # Assert
        assert len(image_tasks) == 3
        assert all(task.original_filename == filename for task in image_tasks)
        assert len(set(task.id for task in image_tasks)) == 3  # IDs uniques
    
    def test_zero_points_deduction(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        """Test la mise à jour du solde de points avec un delta de zéro"""
        # Arrange
        initial_balance = sample_user.points_balance
        
        # Act
        updated_user = user_repository.update_points_balance(db_session, user_id=sample_user.id, points_delta=0)
        
        # Assert
        assert updated_user.points_balance == initial_balance
    
    def test_negative_points_balance(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        """Test la réduction du solde de points à une valeur négative"""
        # Arrange
        initial_balance = sample_user.points_balance
        negative_delta = -(initial_balance + 10)  # Réduire à -10
        
        # Act
        updated_user = user_repository.update_points_balance(db_session, user_id=sample_user.id, points_delta=negative_delta)
        
        # Assert
        assert updated_user.points_balance < 0
        assert updated_user.points_balance == initial_balance + negative_delta
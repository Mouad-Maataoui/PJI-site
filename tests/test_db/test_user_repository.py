import pytest
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.repositories.user_repository import UserRepository
from app.models.user import User
from app.models.schemas.user import UserCreate, UserUpdate


class TestUserRepository:
    def test_create_user(self, db_session: Session, user_repository: UserRepository):
        # Arrange
        user_in = UserCreate(
            email="new@example.com",
            username="newuser",
            password="password",
            ip_address="192.168.1.1"
        )
        
        # Act
        user = user_repository.create(db_session, obj_in=user_in, hashed_password="hashed_password")
        
        # Assert
        assert user.id is not None
        assert user.email == "new@example.com"
        assert user.username == "newuser"
        assert user.hashed_password == "hashed_password"
        assert user.ip_address == "192.168.1.1"
        assert user.points_balance == 0

    def test_get_user(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        # Act
        stored_user = user_repository.get(db_session, user_id=sample_user.id)
        
        # Assert
        assert stored_user
        assert stored_user.id == sample_user.id
        assert stored_user.email == sample_user.email
        assert stored_user.username == sample_user.username

    def test_get_user_by_email(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        # Act
        stored_user = user_repository.get_by_email(db_session, email=sample_user.email)
        
        # Assert
        assert stored_user
        assert stored_user.id == sample_user.id
        assert stored_user.email == sample_user.email

    def test_get_user_by_username(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        # Act
        stored_user = user_repository.get_by_username(db_session, username=sample_user.username)
        
        # Assert
        assert stored_user
        assert stored_user.id == sample_user.id
        assert stored_user.username == sample_user.username

    def test_update_user(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        # Arrange
        user_update = UserUpdate(
            username="updateduser",
            email="updated@example.com",
            ip_address="10.0.0.1"
        )
        
        # Act
        updated_user = user_repository.update(db_session, db_obj=sample_user, obj_in=user_update)
        
        # Assert
        assert updated_user.id == sample_user.id
        assert updated_user.username == "updateduser"
        assert updated_user.email == "updated@example.com"
        assert updated_user.ip_address == "10.0.0.1"

    def test_delete_user(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        # Act
        deleted_user = user_repository.delete(db_session, user_id=sample_user.id)
        remaining_user = user_repository.get(db_session, user_id=sample_user.id)
        
        # Assert
        assert deleted_user.id == sample_user.id
        assert remaining_user is None

    def test_update_points_balance(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        # Arrange
        initial_balance = sample_user.points_balance
        points_delta = 5
        
        # Act
        updated_user = user_repository.update_points_balance(db_session, user_id=sample_user.id, points_delta=points_delta)
        
        # Assert
        assert updated_user.points_balance == initial_balance + points_delta

    def test_update_last_login(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        # Arrange
        new_ip = "8.8.8.8"
        
        # Act
        before_update = datetime.now()
        updated_user = user_repository.update_last_login(db_session, user_id=sample_user.id, ip_address=new_ip)
        
        # Assert
        assert updated_user.ip_address == new_ip
        assert updated_user.last_login is not None
        assert updated_user.last_login >= before_update
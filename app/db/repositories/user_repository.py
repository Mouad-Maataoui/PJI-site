from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.user import User
from app.models.schemas.user import UserCreate, UserUpdate


class UserRepository:

    def get(self, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()
    
    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def get_multi(
        self, db: Session, *, skip: int=0, limit: int=100
    ) -> List[User]:
        return db.query(User).offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: UserCreate, hashed_password: str) -> User:
        db_obj = User(
            email=obj_in.email,
            username=obj_in.username,
            hashed_password=hashed_password,
            ip_address=obj_in.ip_address,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self, db: Session, *, db_obj: User, obj_in: UserUpdate
    ) -> User:
        update_data = obj_in.model_dump(exclude_unset=True)
        if update_data.get("password"):
            hashed_password = update_data.pop("password")
            update_data["hashed_password"] = hashed_password
        for field in update_data:
            setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, user_id: int) -> Optional[User]:    
        obj = db.get(User, user_id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj
    
    def update_points_balance(self, db: Session, *, user_id: int, points_delta: int) -> User:
        # Mise à jour atomique directement dans la base de données
        result = db.query(User).filter(User.id == user_id).update(
            {User.points_balance: User.points_balance + points_delta},
            synchronize_session=False
        )
        
        if result == 0:
            raise ValueError(f"L'utilisateur avec l'id {user_id} n'existe pas")
        
        db.commit()
        # Charger l'utilisateur mis à jour
        db_obj = db.query(User).filter(User.id == user_id).first()
        return db_obj
        
    def update_last_login(self, db: Session, *, user_id: int, ip_address: Optional[str]=None) -> User:
        """Met à jour la dernière connexion et éventuellement l'adresse IP"""
        db_obj = db.query(User).filter(User.id == user_id).first()
        if db_obj:
            db_obj.last_login = datetime.now()
            if ip_address:
                db_obj.ip_address = ip_address
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
        return db_obj

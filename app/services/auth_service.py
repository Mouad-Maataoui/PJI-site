from typing import Optional
from datetime import timedelta
from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password, create_access_token, oauth2_scheme
from app.db.repositories.user_repository import UserRepository
from app.db.session import get_db
from app.models.user import User
from app.models.schemas.user import UserCreate
from app.models.schemas.token import TokenPayload

class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository()

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authentifie un utilisateur par email et mot de passe
        """
        user = self.user_repo.get_by_email(self.db, email=email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def create_user(self, user_in: UserCreate, ip_address: Optional[str] = None) -> User:
        """
        Crée un nouvel utilisateur
        """
        # Vérifier si l'email existe déjà
        existing_email = self.user_repo.get_by_email(self.db, email=user_in.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email déjà enregistré",
            )
        
        # Vérifier si le nom d'utilisateur existe déjà
        existing_username = self.user_repo.get_by_username(self.db, username=user_in.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nom d'utilisateur déjà pris",
            )
        
        # Générer le hash du mot de passe
        from app.core.security import get_password_hash
        hashed_password = get_password_hash(user_in.password)
        
        # Créer l'utilisateur
        user = self.user_repo.create(
            self.db,
            obj_in=user_in,
            hashed_password=hashed_password,
        )
        
        # Mettre à jour l'adresse IP si fournie
        if ip_address:
            user.ip_address = ip_address
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        
        return user

    def create_access_token(self, user_id: int) -> str:
        """
        Crée un token d'accès JWT pour l'utilisateur
        """
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return create_access_token(
            subject=user_id,
            expires_delta=expires_delta
        )

    def update_last_login(self, user: User, ip_address: Optional[str] = None) -> User:
        """
        Met à jour la date de dernière connexion et éventuellement l'adresse IP
        """
        return self.user_repo.update_last_login(
            self.db, user_id=user.id, ip_address=ip_address
        )

# ===== FONCTIONS D'INJECTION DE DÉPENDANCE =====

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """
    Dépendance FastAPI pour obtenir le service d'authentification
    """
    return AuthService(db=db)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Récupère l'utilisateur actuel à partir du token JWT
    FONCTION STANDALONE pour éviter les problèmes d'injection
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les informations d'identification",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Décoder le token
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: int = int(payload.get("sub"))
        if user_id is None:
            raise credentials_exception
        token_data = TokenPayload(user_id=user_id)
    except JWTError:
        raise credentials_exception
    
    # Récupérer l'utilisateur
    user_repo = UserRepository()
    user = user_repo.get(db, user_id=token_data.user_id)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur inactif",
        )
    
    return user
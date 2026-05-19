from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.services.auth_service import AuthService, get_auth_service, get_current_user
from app.models.schemas.user import User, UserCreate
from app.models.schemas.token import Token

router = APIRouter()

@router.post("/register", response_model=User)
def register(
    *,
    user_in: UserCreate,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
) -> Any:
    """
    Inscription d'un nouvel utilisateur.
    """
    # Récupérer l'adresse IP du client
    client_ip = request.client.host if request.client else None
    
    # Créer l'utilisateur
    user = auth_service.create_user(user_in, ip_address=client_ip)
    
    return user

@router.post("/login", response_model=Token)
def login(
    *,
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
) -> Any:
    """
    Login OAuth2 pour obtenir le token JWT.
    """
    # Authentifier l'utilisateur
    user = auth_service.authenticate_user(
        email=form_data.username,  # OAuth2 utilise username pour l'email
        password=form_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Récupérer l'adresse IP du client
    client_ip = request.client.host if request.client else None
    
    # Mettre à jour la dernière connexion
    auth_service.update_last_login(user, ip_address=client_ip)
    
    # Créer le token d'accès
    access_token = auth_service.create_access_token(user.id)
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=User)
def read_users_me(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Récupère l'utilisateur actuellement connecté.
    """
    return current_user
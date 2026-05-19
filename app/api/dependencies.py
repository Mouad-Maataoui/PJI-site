from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth_service import get_current_user
from app.models.user import User

# Réexporter get_current_user pour les routes
def get_current_user(db: Session = Depends(get_db)) -> User:
    """
    Dépendance pour obtenir l'utilisateur actuel
    """
    # Cette fonction appelle directement la fonction standalone
    # L'injection du token se fait automatiquement via oauth2_scheme
    return _get_current_user

# Alias pour la rétrocompatibilité
current_user = Depends(get_current_user)
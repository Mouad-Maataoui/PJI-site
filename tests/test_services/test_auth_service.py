import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from jose import jwt

from app.core.config import settings
from app.services.auth_service import AuthService
from app.models.schemas.user import UserCreate


class TestAuthService:
    def setup_method(self):
        """Configuration initiale pour chaque test"""
        self.db = MagicMock()
        self.user_repo = MagicMock()
        self.auth_service = AuthService(db=self.db, user_repo=self.user_repo)
        
        # Au lieu d'instancier directement un modèle User, créons un mock
        self.mock_user = MagicMock()
        self.mock_user.id = 1
        self.mock_user.email = "test@example.com"
        self.mock_user.username = "testuser"
        self.mock_user.hashed_password = "hashed_password"
        self.mock_user.points_balance = 0
        
        # Vérifier les attributs exacts de votre modèle User
        # Commentez les attributs qui n'existent pas dans votre modèle
        # self.mock_user.is_active = True  # Apparemment cette colonne n'existe pas
        # self.mock_user.is_superuser = False  # Vérifiez si cette colonne existe
        self.mock_user.ip_address = "127.0.0.1"
        self.mock_user.created_at = datetime.now()

    def test_authenticate_user_success(self):
        """Test de l'authentification réussie d'un utilisateur"""
        # Configurer le mock
        self.user_repo.get_by_email.return_value = self.mock_user
        
        # Mocker verify_password pour qu'il retourne True
        with patch("app.services.auth_service.verify_password", return_value=True):
            # Exécuter la méthode à tester
            result = self.auth_service.authenticate_user("test@example.com", "password")
            
            # Vérifier les résultats
            assert result is not None
            assert result.id == 1
            assert result.email == "test@example.com"
            
            # Vérifier que get_by_email a été appelé avec le bon argument
            self.user_repo.get_by_email.assert_called_once_with(self.db, email="test@example.com")

    def test_authenticate_user_invalid_password(self):
        """Test de l'authentification avec un mot de passe invalide"""
        # Configurer le mock
        self.user_repo.get_by_email.return_value = self.mock_user
        
        # Mocker verify_password pour qu'il retourne False
        with patch("app.services.auth_service.verify_password", return_value=False):
            # Exécuter la méthode à tester
            result = self.auth_service.authenticate_user("test@example.com", "wrong_password")
            
            # Vérifier les résultats
            assert result is None
            
            # Vérifier que get_by_email a été appelé avec le bon argument
            self.user_repo.get_by_email.assert_called_once_with(self.db, email="test@example.com")

    def test_authenticate_user_invalid_email(self):
        """Test de l'authentification avec un email invalide"""
        # Configurer le mock pour qu'il retourne None (utilisateur inexistant)
        self.user_repo.get_by_email.return_value = None
        
        # Exécuter la méthode à tester
        result = self.auth_service.authenticate_user("nonexistent@example.com", "password")
        
        # Vérifier les résultats
        assert result is None
        
        # Vérifier que get_by_email a été appelé avec le bon argument
        self.user_repo.get_by_email.assert_called_once_with(self.db, email="nonexistent@example.com")

    def test_create_user_success(self):
        """Test de la création réussie d'un utilisateur"""
        # Configurer les mocks
        self.user_repo.get_by_email.return_value = None
        self.user_repo.get_by_username.return_value = None
        self.user_repo.create.return_value = self.mock_user
        
        # Mocker get_password_hash
        with patch("app.core.security.get_password_hash", return_value="hashed_password"):
            # Créer l'objet UserCreate
            user_in = UserCreate(
                email="test@example.com",
                username="testuser",
                password="password"
            )
            
            # Exécuter la méthode à tester
            result = self.auth_service.create_user(user_in, ip_address="127.0.0.1")
            
            # Vérifier les résultats
            assert result is not None
            assert result.email == "test@example.com"
            assert result.username == "testuser"
            
            # Vérifier que les méthodes du repository ont été appelées correctement
            self.user_repo.get_by_email.assert_called_once_with(self.db, email="test@example.com")
            self.user_repo.get_by_username.assert_called_once_with(self.db, username="testuser")
            self.user_repo.create.assert_called_once()

    def test_create_user_email_exists(self):
        """Test de la création d'un utilisateur avec un email déjà existant"""
        # Configurer le mock pour qu'il retourne un utilisateur existant
        self.user_repo.get_by_email.return_value = self.mock_user
        
        # Créer l'objet UserCreate
        user_in = UserCreate(
            email="test@example.com",
            username="newuser",
            password="password"
        )
        
        # Exécuter la méthode à tester et vérifier qu'elle lève une exception
        with pytest.raises(HTTPException) as excinfo:
            self.auth_service.create_user(user_in)
        
        # Vérifier les détails de l'exception
        assert excinfo.value.status_code == 400
        assert "Email déjà enregistré" in excinfo.value.detail
        
        # Vérifier que get_by_email a été appelé avec le bon argument
        self.user_repo.get_by_email.assert_called_once_with(self.db, email="test@example.com")

    def test_create_user_username_exists(self):
        """Test de la création d'un utilisateur avec un nom d'utilisateur déjà existant"""
        # Configurer les mocks
        self.user_repo.get_by_email.return_value = None
        self.user_repo.get_by_username.return_value = self.mock_user
        
        # Créer l'objet UserCreate
        user_in = UserCreate(
            email="new@example.com",
            username="testuser",
            password="password"
        )
        
        # Exécuter la méthode à tester et vérifier qu'elle lève une exception
        with pytest.raises(HTTPException) as excinfo:
            self.auth_service.create_user(user_in)
        
        # Vérifier les détails de l'exception
        assert excinfo.value.status_code == 400
        assert "Nom d'utilisateur déjà pris" in excinfo.value.detail
        
        # Vérifier que les méthodes du repository ont été appelées correctement
        self.user_repo.get_by_email.assert_called_once_with(self.db, email="new@example.com")
        self.user_repo.get_by_username.assert_called_once_with(self.db, username="testuser")

    def test_create_access_token(self):
        """Test de la création d'un token d'accès"""
        # Exécuter la méthode à tester
        token = self.auth_service.create_access_token(user_id=1)
        
        # Vérifier que le token est une chaîne non vide
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Vérifier que le token est un JWT valide avec le bon payload
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "1"
        
        # Vérifier seulement que le token expire dans le futur
        now_timestamp = datetime.utcnow().timestamp()
        assert payload["exp"] > now_timestamp

    def test_update_last_login(self):
        """Test de la mise à jour de la dernière connexion"""
        # Configurer le mock
        self.user_repo.update_last_login.return_value = self.mock_user
        
        # Exécuter la méthode à tester
        result = self.auth_service.update_last_login(self.mock_user, ip_address="192.168.1.1")
        
        # Vérifier les résultats
        assert result is self.mock_user
        
        # Vérifier que update_last_login a été appelé avec les bons arguments
        self.user_repo.update_last_login.assert_called_once_with(
            self.db, user_id=1, ip_address="192.168.1.1"
        )
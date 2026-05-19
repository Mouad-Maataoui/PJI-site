import pytest
import time
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


def random_string(length=10):
    """Génère une chaîne aléatoire de longueur spécifiée"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


class TestRepositoryPerformance:
    @pytest.mark.performance
    def test_bulk_user_creation(self, db_session: Session, user_repository: UserRepository):
        """Test la création d'un grand nombre d'utilisateurs"""
        # Arrange
        num_users = 100
        start_time = time.time()
        
        # Act
        for i in range(num_users):
            user_in = UserCreate(
                email=f"user{i}_{random_string()}@example.com",
                username=f"user{i}_{random_string()}",
                password="password"
            )
            user_repository.create(db_session, obj_in=user_in, hashed_password="hashed_password")
        
        end_time = time.time()
        
        # Assert
        elapsed_time = end_time - start_time
        print(f"\nTemps pour créer {num_users} utilisateurs: {elapsed_time:.2f} secondes")
        
        # La performance exacte dépend de l'environnement, mais vérifions au moins que ça fonctionne
        count = db_session.query(User).count()
        assert count >= num_users  # Au moins le nombre créé (plus les fixtures)
        
        # Un critère de performance arbitraire pour les tests (ajustez selon votre environnement)
        assert elapsed_time < 5.0, f"La création d'utilisateurs est trop lente: {elapsed_time:.2f} secondes"
    
    @pytest.mark.performance
    def test_bulk_image_creation(self, db_session: Session, image_repository: ImageRepository, sample_user: User):
        """Test la création d'un grand nombre de tâches d'image"""
        # Arrange
        num_images = 100
        start_time = time.time()
        
        # Act
        for i in range(num_images):
            image_in = ImageTaskCreate(
                original_filename=f"image{i}_{random_string()}.jpg"
            )
            image_repository.create(
                db_session, 
                obj_in=image_in, 
                user_id=sample_user.id, 
                original_file_path=f"/tmp/image{i}.jpg"
            )
        
        end_time = time.time()
        
        # Assert
        elapsed_time = end_time - start_time
        print(f"\nTemps pour créer {num_images} tâches d'image: {elapsed_time:.2f} secondes")
        
        # Vérifier que toutes les images ont été créées
        count = db_session.query(ImageTask).filter(ImageTask.user_id == sample_user.id).count()
        assert count >= num_images  # Au moins le nombre créé (plus les fixtures)
        
        # Un critère de performance arbitraire
        assert elapsed_time < 5.0, f"La création d'images est trop lente: {elapsed_time:.2f} secondes"
    
    @pytest.mark.performance
    def test_query_performance_with_large_dataset(self, db_session: Session, user_repository: UserRepository, sample_user: User):
        """Test les performances des requêtes avec un grand ensemble de données"""
        # Arrange - Créer un grand nombre d'images pour l'utilisateur
        num_images = 500
        
        # Créer des images avec différents statuts
        statuses = list(ProcessingStatus)
        for i in range(num_images):
            status = statuses[i % len(statuses)]
            image_task = ImageTask(
                user_id=sample_user.id,
                original_filename=f"perf_image{i}.jpg",
                original_file_path=f"/tmp/perf_image{i}.jpg",
                status=status,
                expire_at=datetime.now() + timedelta(days=30)
            )
            db_session.add(image_task)
        db_session.commit()
        
        # Act & Assert - Mesurer le temps des différentes requêtes
        
        # 1. Récupérer toutes les images d'un utilisateur
        start_time = time.time()
        all_images = db_session.query(ImageTask).filter(ImageTask.user_id == sample_user.id).all()
        query_time = time.time() - start_time
        print(f"\nTemps pour récupérer {len(all_images)} images d'un utilisateur: {query_time:.4f} secondes")
        assert query_time < 1.0, "La requête pour toutes les images est trop lente"
        
        # 2. Récupérer les images par statut
        start_time = time.time()
        pending_images = db_session.query(ImageTask).filter(
            ImageTask.user_id == sample_user.id,
            ImageTask.status == ProcessingStatus.PENDING
        ).all()
        query_time = time.time() - start_time
        print(f"\nTemps pour filtrer {len(pending_images)} images par statut: {query_time:.4f} secondes")
        assert query_time < 0.5, "La requête filtrée par statut est trop lente"
        
        # 3. Pagination
        start_time = time.time()
        for page in range(5):
            paginated_images = db_session.query(ImageTask).filter(
                ImageTask.user_id == sample_user.id
            ).offset(page * 100).limit(100).all()
        query_time = time.time() - start_time
        print(f"\nTemps pour 5 requêtes de pagination (100 éléments chacune): {query_time:.4f} secondes")
        assert query_time < 1.0, "Les requêtes de pagination sont trop lentes"
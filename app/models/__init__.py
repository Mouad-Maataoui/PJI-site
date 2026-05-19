# app/db/init_models.py
# Import all models here for Alembic to detect
from app.db.base_class import Base  # noqa

# Importer d'abord les modèles sans dépendances circulaires
# Puis importer les modèles avec dépendances
from app.models.image_task import ImageTask  # noqa
from app.models.transaction import Transaction  # noqa
from app.models.user import User  # noqa
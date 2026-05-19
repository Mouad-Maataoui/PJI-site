from typing import Optional, List
from sqlalchemy.orm import Session

class ImageService:
    """
    Service minimal pour le traitement des images.
    Cette classe sera développée ultérieurement.
    """
    def __init__(self, db: Session):
        self.db = db

    # Méthodes à implémenter plus tard
    def process_image(self):
        pass

# Fonction de commodité pour l'injection de dépendance
def get_image_service(db: Session) -> ImageService:
    return ImageService(db=db)
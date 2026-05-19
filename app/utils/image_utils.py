import os
import io
import uuid
from typing import Tuple, Optional, List
from pathlib import Path
from PIL import Image
import logging
from fastapi import UploadFile, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

class ImageUtils:
    """Utilitaires pour la manipulation d'images"""
    
    SUPPORTED_FORMATS = ["jpg", "jpeg", "png"]
    MAX_SIZE_MB = 10  # Taille maximale en MB
    
    @staticmethod
    def validate_image(upload_file: UploadFile) -> None:
        """
        Valide un fichier image
        
        Args:
            upload_file: Fichier uploadé
            
        Raises:
            HTTPException: Si le fichier n'est pas valide
        """
        # Vérifier l'extension
        ext = os.path.splitext(upload_file.filename or "")[1].lower().strip(".")
        if ext not in ImageUtils.SUPPORTED_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Format non supporté. Formats acceptés: {', '.join(ImageUtils.SUPPORTED_FORMATS)}"
            )
        
        # Essayer d'ouvrir l'image pour valider qu'il s'agit bien d'une image
        try:
            content = upload_file.file.read(1024)  # Lire un peu de contenu pour vérifier
            upload_file.file.seek(0)  # Revenir au début du fichier
            
            try:
                # Tester si le fichier peut être ouvert comme une image
                Image.open(io.BytesIO(content))
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Le fichier n'est pas une image valide"
                )
            
        except Exception as e:
            logger.error(f"Erreur lors de la validation de l'image: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Erreur lors de la validation de l'image"
            )
    
    @staticmethod
    async def compress_image(file: UploadFile, quality: int = 85) -> Tuple[bytes, str]:
        """
        Compresse une image
        
        Args:
            file: Fichier image à compresser
            quality: Qualité de compression (0-100)
            
        Returns:
            Tuple[bytes, str]: Image compressée en bytes et format
        """
        content = await file.read()
        file.file.seek(0)  # Remettre le curseur au début pour les futures lectures
        
        img = Image.open(io.BytesIO(content))
        format = img.format.lower() if img.format else "jpeg"
        
        # Si c'est du PNG avec transparence, préserver le canal alpha
        if format == "png" and img.mode == "RGBA":
            output = io.BytesIO()
            img.save(output, format=format, optimize=True)
            return output.getvalue(), format
        
        # Pour les autres formats, convertir en RGB et compresser
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        output = io.BytesIO()
        img.save(output, format=format, quality=quality, optimize=True)
        
        return output.getvalue(), format
    
    @staticmethod
    def save_image(img_bytes: bytes, filename: str) -> str:
        """
        Sauvegarde une image sur disque
        
        Args:
            img_bytes: Contenu de l'image en bytes
            filename: Nom du fichier
            
        Returns:
            str: Chemin complet de l'image sauvegardée
        """
        # Créer les répertoires si nécessaire
        upload_dir = Path(settings.IMAGE_STORAGE_PATH) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Générer un nom de fichier unique
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = upload_dir / unique_filename
        
        # Sauvegarder l'image
        with open(file_path, "wb") as f:
            f.write(img_bytes)
        
        return str(file_path)
    
    @staticmethod
    def decompress_image(file_path: str) -> bytes:
        """
        Décompresse une image pour l'envoi
        
        Args:
            file_path: Chemin vers le fichier image
            
        Returns:
            bytes: Contenu de l'image
        """
        with open(file_path, "rb") as f:
            return f.read()
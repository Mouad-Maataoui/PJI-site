import os
import logging
import uuid
import asyncio
from typing import Dict, Any, Optional, Tuple, Literal
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image
import io
import cv2
import numpy as np

from app.core.config import settings
from app.models.image_task import ProcessingStatus
from app.ml.base_onnx_processor import BaseONNXProcessor
from app.ml.model_loader import model_manager

logger = logging.getLogger(__name__)

class ImageProcessingService:
    """Service pour le traitement d'images avec IA ONNX - Version robuste"""
    
    def __init__(self, models_name: str, db_session=None, models_type: str = "bg_remove"):
        """
        Initialise le service de traitement d'images
        
        Args:
            db_session: Session de base de données
            models_name: Nom du modèle ONNX à utiliser (par défaut: rmbg-1.4-quantized)
        """
        self.db_session = db_session
        self.processors: Dict[str, BaseONNXProcessor] = {}

        available = model_manager.list_available_models()
        if available.get(models_type).get(models_name, None) == None:
            logger.warning(f"Le modèle {models_name} n'est pas disponible, modèles dispo pour type {models_type}: {available.get(models_type)}\nUtilisation du modèle par défaut")
            models_name = settings.DEFAULT_AI_MODEL_BG if models_type == "bg_remove" else settings.DEFAULT_AI_MODEL_UPSCALE

        self.default_models = {}
        self.default_models[models_type] = models_name
        
        # Initialiser le processeur ONNX de manière lazy
        # self._init_ai_processor()
    
    def _get_setting(self, setting_name: str, default_value: Any = None) -> Any:
        """
        Récupère une configuration avec fallback
        
        Args:
            setting_name: Nom de la configuration
            default_value: Valeur par défaut
            
        Returns:
            Valeur de la configuration ou valeur par défaut
        """
        return getattr(settings, setting_name, default_value)
    
    def _get_processor(self, models_type: str = "bg_remove"):
        """ Récupère ou initialise un processeur spécifique """
        if models_type in self.processors:
            return self.processors.get(models_type)

        return self._init_ai_processor(models_type)
    
    def _get_storage_path(self) -> Path:
        """Récupère le chemin de stockage avec fallback"""
        storage_path = getattr(settings, 'IMAGE_STORAGE_PATH', 'storage')
        return Path(storage_path)
    
    def _resize_image_on_disk(self, input_path: str, output_path: str, width: int, height: int):
        """
        Helper pour redimensionner une image sur le disque.
        
        Args:
            input_path: Path vers l'image
            output_path: Path vers l'image redimensionner
            width: largeur voulue
            height: hauteur voulue
        """
        try:
            with Image.open(input_path) as img:
                # Convertir en RGB si nécessaire (pour éviter erreurs sur PNG transparents)
                if img.mode != 'RGB' and img.mode != 'RGBA':
                    img = img.convert('RGB')

                org_w, org_h = img.size

                ratio_w = width / org_w
                ratio_h = height / org_h

                scale_factor = min(ratio_w, ratio_h)

                final_width = int(org_w * scale_factor)
                final_height = int(org_h * scale_factor)
                
                # Redimensionnement haute qualité (LANCZOS)
                resized = img.resize((final_width, final_height), Image.Resampling.LANCZOS)
                resized.save(output_path, quality=95)
                return True
        except Exception as e:
            logger.error(f"Erreur resize disque: {str(e)}")
            raise
    
    def _init_ai_processor(self, models_type: Literal["bg_remove", "upscale"]):
        """Initialise le processeur IA ONNX"""
        try:
            models_name = self.default_models.get(models_type)
            logger.info(f"Initialisation du processeur {models_type}: {models_name}")
            
            # Récupérer le path du modèle
            model_path = model_manager.get_model_path(models_name)

            match models_type:
                case "bg_remove":
                    from app.ml.onnx_processor_bg import create_background_remover

                    # Déterminer le type de modèle basé sur le nom
                    if 'rmbg' in models_name.lower():
                        model_spec = 'rmbg'
                    elif 'u2net' in models_name.lower():
                        model_spec = 'u2net'
                    elif 'modnet' in models_name.lower():
                        model_spec = 'modnet'
                    elif 'birefnet' in models_name.lower():
                        model_spec = 'birefnet'
                    else:
                        model_spec = 'rmbg'  # Par défaut

                    # Créer le processeur
                    processor = create_background_remover(
                        model_spec=model_spec,
                        model_path=model_path
                    )
                
                case "upscale":
                    from app.ml.onnx_processor_up import create_upscaler

                    # Créer le processeur
                    processor = create_upscaler(
                        model_path=model_path,
                    )
                
                case _:
                    raise ValueError(f"Type de modèle non supporté: {models_type}")
                
            self.processors[models_type] = processor
            
            logger.info(f"Processeur {models_type}: {models_name} initialisé avec succès")

            return processor
            
        except Exception as e:
            logger.warning(f"Erreur initialisation processeur IA: {str(e)}")
            logger.info("Utilisation du mode fallback uniquement")
            # self.default_models = {}
            return None
    
    async def compress_image(self, image_bytes: bytes, quality: int = 85) -> Tuple[bytes, str]:
        """
        Compresse une image
        
        Args:
            image_bytes: Contenu de l'image en bytes
            quality: Qualité de compression (0-100)
            
        Returns:
            Tuple[bytes, str]: Image compressée en bytes et format
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            format = img.format.lower() if img.format else "jpeg"
            
            # Si c'est du PNG avec transparence, préserver le canal alpha
            if format == "png" and img.mode == "RGBA":
                output = io.BytesIO()
                img.save(output, format="PNG", optimize=True)
                return output.getvalue(), "png"
            
            # Pour les autres formats, convertir en RGB et compresser
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=quality, optimize=True)
            
            return output.getvalue(), "jpeg"
            
        except Exception as e:
            logger.error(f"Erreur compression image: {str(e)}")
            raise
    
    async def process_with_ai(self, input_path: str, models_type: Literal['bg_remove', 'upscale'] = 'bg_remove', options: Optional[Dict[str, Any]] = None) -> str:
        """
        Traitement d'image avec IA ONNX pour suppression d'arrière-plan
        
        Args:
            input_path: Chemin vers l'image d'entrée
            models_type: Type de modèle à utilisé
            options: Options de traitement
            
        Returns:
            str: Chemin vers l'image traitée
        """
        try:
            logger.info(f"Début traitement IA ({models_type}): {input_path}")
            
            processor = self._get_processor(models_type)

            if processor is None:
                logger.warning("Processeur IA non disponible, utilisation du fallback")
                return await self.process_mock(input_path, options)
            
                
            # Options par défaut
            if options is None: options = {}
            storage_path = self._get_storage_path()
            processed_dir = storage_path / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)

            match models_type:
                case "bg_remove":
                    return await self._run_bg_remove(processor, input_path, processed_dir, options)
                case "upscale":
                    return await self._run_upscaling(processor, input_path, processed_dir, options)
                case _:
                    raise ValueError(f"Type de modèle non supporté: {models_type}")
        
        except Exception as e:
            logger.error(f"Erreur critique process_with_ai: {str(e)}")
            return await self.process_mock(input_path, options)
        
    
    async def _run_bg_remove(self, processor, input_path, processed_dir, options):
        """ Logique pour le détourage """
        ai_input_path = input_path
            
        if 'resize' in options:
            resize_opt = options['resize']
            width = resize_opt.get('width')
            height = resize_opt.get('height')
                
            if width and height:
                logger.info(f"Optimisation: Redimensionnement vers {width}x{height} avant traitement")
                    
                # Créer un dossier temporaire pour ne pas écraser l'original
                storage_path = self._get_storage_path()
                temp_dir = storage_path / "temp_processing"
                temp_dir.mkdir(parents=True, exist_ok=True)
                
                # Nom de fichier temporaire
                resized_filename = f"resized_{uuid.uuid4()}_{os.path.basename(input_path)}"
                resized_path = temp_dir / resized_filename
                
                try:
                    # Exécuter le redimensionnement dans un thread (pour ne pas bloquer l'event loop)
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        self._resize_image_on_disk,
                        input_path,
                        str(resized_path),
                        width,
                        height
                    )
                    # IMPORTANT: On dit à l'IA d'utiliser l'image réduite
                    ai_input_path = str(resized_path)
                    
                except Exception as resize_err:
                    logger.error(f"Échec du pré-redimensionnement: {resize_err}")
                    # En cas d'erreur, on continue silencieusement avec l'image originale
                    ai_input_path = input_path

        # Extraire les options
        background_color = options.get('background_color', None)  # None = transparent
        output_format = options.get('output_format', getattr(settings, 'DEFAULT_OUTPUT_FORMAT', 'png'))
        
        # Si couleur d'arrière-plan spécifiée, convertir de hex vers RGB
        if background_color and isinstance(background_color, str):
            if background_color.startswith('#'):
                background_color = tuple(int(background_color[i:i+2], 16) for i in (1, 3, 5))
        
        
        # Nom de fichier unique avec bon format
        unique_filename = f"{uuid.uuid4()}_{os.path.splitext(os.path.basename(ai_input_path))[0]}.{output_format}"
        output_path = processed_dir / unique_filename
        
        # Exécuter la suppression d'arrière-plan
        result_path = await asyncio.get_event_loop().run_in_executor(
            None,
            processor.remove_background,
            ai_input_path,
            str(output_path),
            background_color
        )
        
        logger.info(f"Traitement IA terminé: {result_path}")
        return result_path
    
    async def _run_upscaling(self, processor, input_path, output_dir, options):
        """Logique spécifique pour l'upscaling"""
        scale_factor = options.get('scale', settings.DEFAULT_UPSCALE_RATIO)
        out_fmt = options.get('output_format', 'png')
        
        filename = f"{uuid.uuid4()}_upscale_x{scale_factor}_{os.path.splitext(os.path.basename(input_path))[0]}.{out_fmt}"
        output_path = output_dir / filename

        # Exécution (suppose que votre processeur a une méthode 'upscale')
        result_path = await asyncio.get_event_loop().run_in_executor(
            None,
            processor.upscale_file,
            input_path,
            str(output_path),
            scale_factor
        )
        return result_path
        
    
    async def process_mock(self, input_path: str, options: Optional[Dict[str, Any]] = None) -> str:
        """
        Version de fallback si le traitement IA échoue
        Applique un effet simple visible
        
        Args:
            input_path: Chemin vers l'image d'entrée
            options: Options de traitement
            
        Returns:
            str: Chemin vers l'image traitée
        """
        try:
            logger.warning(f"Utilisation du traitement de fallback pour: {input_path}")
            
            # Charger l'image
            image = cv2.imread(input_path)
            if image is None:
                raise ValueError(f"Impossible de charger l'image: {input_path}")
            
            # Appliquer un effet visible (bordure + flou léger)
            # Ajouter une bordure colorée
            border_size = 10
            border_color = [0, 255, 0]  # Vert en BGR
            bordered = cv2.copyMakeBorder(
                image, border_size, border_size, border_size, border_size,
                cv2.BORDER_CONSTANT, value=border_color
            )
            
            # Appliquer un léger flou pour indiquer le traitement
            processed = cv2.GaussianBlur(bordered, (5, 5), 0)
            
            # Sauvegarder l'image traitée
            storage_path = self._get_storage_path()
            processed_dir = storage_path / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            
            unique_filename = f"{uuid.uuid4()}_mock_{os.path.basename(input_path)}"
            output_path = processed_dir / unique_filename
            
            cv2.imwrite(str(output_path), processed)
            
            logger.info(f"Traitement de fallback terminé: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Erreur traitement de fallback: {str(e)}")
            raise
    
    def run_processing_threads(self, task_id: int, original_path: str, compressed_path: str, mode: str = 'main',
            models_type: Literal['bg_remove', 'upscale'] = 'bg_remove', options: Optional[Dict[str, Any]] = None) -> str:
        """
        Exécute le traitement d'image avec des threads parallèles
        
        Args:
            task_id: ID de la tâche
            original_path: Chemin vers l'image originale (pour le traitement)
            compressed_path: Chemin vers l'image compressée (pour la sauvegarde)
            options: Options de traitement
            
        Returns:
            str: ID de la tâche Celery
        """
        from app.worker.tasks import process_image_task
        
        # Mettre à jour le statut de la tâche
        if self.db_session:
            try:
                from app.db.repositories.image_repository import ImageRepository
                image_repo = ImageRepository(self.db_session)
                image_repo.update_status(
                    task_id=task_id, 
                    status=ProcessingStatus.PENDING.value
                )
            except Exception as e:
                logger.warning(f"Impossible de mettre à jour le statut: {str(e)}")
        
        # Ajouter le modèle utilisé aux options
        if options is None:
            options = {}

        # self._get_processor(models_type)
        options['ai_model'] = self.default_models.get(models_type)

        queue_used = 'main-queue' if mode == 'main' else 'low-queue'
        
        # Lancer la tâche Celery avec les deux chemins
        task = process_image_task.apply_async(
            args=[task_id, original_path, compressed_path, mode, models_type, options],
            queue=queue_used
        )
        
        return task.id
    
    def save_image(self, img_bytes: bytes, filename: str, subdir: str = "uploads") -> str:
        """
        Sauvegarde une image sur disque
        
        Args:
            img_bytes: Contenu de l'image en bytes
            filename: Nom du fichier
            subdir: Sous-répertoire de stockage
            
        Returns:
            str: Chemin complet de l'image sauvegardée
        """
        try:
            # Créer les répertoires si nécessaire
            storage_path = self._get_storage_path()
            storage_dir = storage_path / subdir
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            # Générer un nom de fichier unique
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = storage_dir / unique_filename
            
            # Sauvegarder l'image
            with open(file_path, "wb") as f:
                f.write(img_bytes)
            
            logger.info(f"Image sauvegardée: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde image: {str(e)}")
            raise
    
    async def compress_and_save_image(self, image_path: str, output_filename: str = None) -> str:
        """
        Compresse une image existante et la sauvegarde
        
        Args:
            image_path: Chemin vers l'image à compresser
            output_filename: Nom du fichier de sortie (optionnel)
            
        Returns:
            str: Chemin de l'image compressée
        """
        try:
            # Lire l'image
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            
            # Compresser l'image
            compressed_bytes, format = await self.compress_image(image_bytes)
            
            # Générer le nom du fichier de sortie s'il n'est pas fourni
            if not output_filename:
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                output_filename = f"compressed_{base_name}.{format}"
            
            # Sauvegarder l'image compressée
            storage_path = self._get_storage_path()
            compressed_dir = storage_path / "compressed"
            compressed_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = compressed_dir / output_filename
            
            with open(output_path, "wb") as f:
                f.write(compressed_bytes)
            
            logger.info(f"Image compressée sauvegardée: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Erreur compression et sauvegarde: {str(e)}")
            raise
    
    async def decompress_for_download(self, compressed_path: str) -> bytes:
        """
        Décompresse une image pour l'envoi au client
        
        Args:
            compressed_path: Chemin vers l'image compressée
            
        Returns:
            bytes: Contenu de l'image décompressée
        """
        try:
            # Pour la décompression, nous lisons simplement l'image 
            # car la décompression est automatiquement gérée par les bibliothèques d'affichage
            with open(compressed_path, "rb") as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Erreur décompression: {str(e)}")
            raise
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Retourne les informations sur le modèle IA utilisé
        
        Returns:
            Dictionnaire avec les infos du modèle
        """
        return {
            'loaded_processors': list(self.processors.keys()),
            'defaults': self.default_models
        }
        
    
    async def test_ai_processing(self, test_image_path: str = None, models_type: Literal["bg_remove", "upscale"] = "bg_remove") -> Dict[str, Any]:
        """
        Test du processeur IA avec une image de test
        
        Args:
            test_image_path: Chemin vers une image de test (optionnel)
            
        Returns:
            Résultats du test
        """
        try:
            # Utiliser image de test par défaut si non fournie
            if test_image_path is None:
                # Créer une image de test simple
                storage_path = self._get_storage_path()
                test_dir = storage_path / "test"
                test_dir.mkdir(parents=True, exist_ok=True)
                test_image_path = test_dir / "test_image.jpg"
                
                if not test_image_path.exists():
                    # Créer une image de test simple
                    test_image = np.zeros((200, 200, 3), dtype=np.uint8)
                    test_image[50:150, 50:150] = [255, 255, 255]  # Carré blanc
                    cv2.imwrite(str(test_image_path), test_image)
            
            start_time = asyncio.get_event_loop().time()

            proc = self._get_processor(models_type)
            
            # Tester le traitement IA
            match models_type:
                case "bg_remove":
                    if  proc is not None:
                        result_path = await self.process_with_ai(str(test_image_path), models_type=models_type)
                        mode = "ai"
                    else:
                        result_path = await self.process_mock(str(test_image_path))
                        mode = "fallback"

                case "upscale":
                    result_path = await self.process_with_ai(str(test_image_path), models_type=models_type)
                    mode = "ai"
                    
            
            end_time = asyncio.get_event_loop().time()
            processing_time = end_time - start_time
            
            # Vérifier que le fichier résultat existe
            result_exists = os.path.exists(result_path)
            result_size = os.path.getsize(result_path) if result_exists else 0
            
            return {
                'success': True,
                'models_name': self.default_models.get(models_type),
                'mode': mode,
                'processing_time_seconds': round(processing_time, 2),
                'input_path': str(test_image_path),
                'output_path': result_path,
                'output_exists': result_exists,
                'output_size_bytes': result_size,
                'message': f'Test réussi en {processing_time:.2f}s ({mode})'
            }
            
        except Exception as e:
            return {
                'success': False,
                'models_name': self.default_models.get(models_type),
                'error': str(e),
                'message': f'Test échoué: {str(e)}'
            }
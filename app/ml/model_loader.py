import os
import logging
import hashlib
from typing import Dict, Optional
from pathlib import Path
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)

class ModelManager:
    """
    Gestionnaire centralisé des modèles ONNX
    Gère le téléchargement, la validation et le cache des modèles
    """
    
    def __init__(self, models_dir: str = None):
        """
        Initialise le gestionnaire de modèles
        
        Args:
            models_dir: Répertoire des modèles (par défaut depuis config)
        """
        self.models_dir = Path(models_dir or settings.MODEL_PATH)
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.models_types = settings.MODEL_TYPES
    
        self.available_models = {}
        self.default_models = {}
        self.dirs = {}
        for md_type in self.models_types:
            path = self.models_dir / md_type
            path.mkdir(parents=True, exist_ok=True)
            self.dirs[md_type] = path

            match md_type:
                case "bg_remove":
                    self.available_models[md_type] = {
                        "rmbg-1.4": {
                            "url": "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model.onnx",
                            "filename": "rmbg-1.4.onnx",
                            "size_mb": 176,
                            "sha256": None,  # Optionnel pour validation
                            "description": "RMBG 1.4 - Modèle haute qualité pour suppression d'arrière-plan générale"
                        },
                        "birefnet-com": {
                            "url": "https://huggingface.co/onnx-community/BiRefNet-ONNX/resolve/main/onnx/model.onnx",
                            "filename": "birefnet-com.onnx",
                            "size_mb": 928,
                            "sha256": None,
                            "description": "Modèle basé sur l'architedcture BiRefNet, gère des résolution de 256x à 2304x"

                        },
                        "rmbg-1.4-fp16": {
                            "url": "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model_fp16.onnx",
                            "filename": "rmbg-1.4-fp16.onnx", 
                            "size_mb": 88,
                            "sha256": None,
                            "description": "RMBG 1.4 FP16 - Version allégée avec précision réduite"
                        },
                        "rmbg-1.4-quantized": {
                            "url": "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model_quantized.onnx",
                            "filename": "rmbg-1.4-quantized.onnx",
                            "size_mb": 44,
                            "sha256": None,
                            "description": "RMBG 1.4 Quantized - Version très légère pour performance maximale"
                        },
                        "u2net": {
                            "url": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
                            "filename": "u2net.onnx",
                            "size_mb": 167,
                            "sha256": None,
                            "description": "U2-Net - Modèle classique robuste"
                        },
                        "u2net-lite": {
                            "url": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
                            "filename": "u2net-lite.onnx", 
                            "size_mb": 43,
                            "sha256": None,
                            "description": "U2-Net Lite - Version allégée de U2-Net"
                        },
                        "modnet": {
                            "url": "https://huggingface.co/datasets/huedaya/background-remover-files/resolve/main/modnet.onnx",
                            "filename": "modnet.onnx",
                            "size_mb": 25,
                            "sha256": None,
                            "description": "MODNet - Modèle efficace pour portraits"
                        }
                    }
                    self.default_models[md_type] = settings.DEFAULT_AI_MODEL_BG # Bon compromis qualité/performance
                case "upscale":
                    self.available_models[md_type] = {
                        "realesrgan-x4plus-qualcomm": {
                            "url": "https://huggingface.co/qualcomm/Real-ESRGAN-x4plus/resolve/01179a4da7bf5ac91faca650e6afbf282ac93933/Real-ESRGAN-x4plus.onnx",
                            "filename": "Real-ESRGAN-x4plus.onnx",
                            "size_mb": 67.1,
                            "sha256": None,
                            "description": "Real-ESRGAN x4plus (Qualcomm) - Modèle officiel maintenu pour inférence mobile. Robuste pour tout type d'image."
                        },
                        "realesrgan-x4-axera": {
                            "url": "https://huggingface.co/AXERA-TECH/Real-ESRGAN/resolve/7a6a599cf9ebad52cfc813a0e71322f4640f5b99/onnx/realesrgan-x4.onnx",
                            "filename": "realesrgan-x4.onnx",
                            "size_mb": 67.0,
                            "sha256": None,
                            "description": "Real-ESRGAN x4 (Axera) - Alternative viable, potentiellement optimisée pour l'inférence NPU."
                        },
                        "realesrgan-x4plus-anime": {
                            "url": "https://huggingface.co/deepghs/imgutils-models/resolve/main/real_esrgan/RealESRGAN_x4plus_anime_6B.onnx",
                            "filename": "RealESRGAN_x4plus_anime_6B.onnx",
                            "size_mb": 17.9,
                            "sha256": None,
                            "description": "Real-ESRGAN x4plus Anime 6B - Optimisé pour illustration/anime. Rapide et sans bruit indésirable."
                        },
                        "realesr-general-x4v3": {
                            "url": "https://huggingface.co/OwlMaster/AllFilesRope/resolve/main/realesr-general-x4v3.onnx",
                            "filename": "realesr-general-x4v3.onnx",
                            "size_mb": 4.87,
                            "sha256": None,
                            "description": "RealESR General x4v3 - Ultra-léger (SRVGGNetCompact) pour le temps réel ou la vidéo."
                        }
                    }
                    self.default_models[md_type] = settings.DEFAULT_AI_MODEL_UPSCALE
    
    def list_available_models(self) -> Dict[str, Dict[str, Dict]]:
        """Retourne la liste des modèles disponibles"""
        return self.available_models
    
    def list_downloaded_models(self) -> list:
        """Retourne la liste des modèles déjà téléchargés"""
        downloaded = []
        for models_type, models in self.available_models.items():
            for models_name, config in models.items():
                model_path = self.dirs[models_type] / config["filename"]
                if model_path.exists():
                    file_size = model_path.stat().st_size / (1024 * 1024)  # MB
                    downloaded.append({
                        "name": models_name,
                        "path": str(model_path),
                        "size_mb": round(file_size, 1),
                        "description": config["description"]
                    })
        return downloaded
    
    def get_model_path(self, models_name: str) -> str:
        """
        Retourne le chemin du modèle, le télécharge si nécessaire
        
        Args:
            models_name: Nom du modèle
            models_type: Type du modèle
            
        Returns:
            Chemin vers le fichier modèle
            
        Raises:
            ValueError: Si le modèle n'existe pas
            RuntimeError: Si le téléchargement échoue
        """
        model_path = None
        for models_type in self.available_models.keys():
            if models_name not in self.available_models[models_type]:
                continue
            
            config = self.available_models[models_type][models_name]
            model_path = self.dirs[models_type] / config["filename"]
            
            # Télécharger si pas présent
            if not model_path.exists():
                logger.info(f"Modèle '{models_name}' non trouvé, téléchargement...")
                self._download_model(models_name, models_type)
            
            # VALIDATION SIMPLIFIÉE ET FIABLE
            if not self._validate_model_simple(model_path):
                logger.warning(f"Modèle '{models_name}' invalide, re-téléchargement...")
                self._download_model(models_name, models_type)

        if model_path is None:
            available = [self.available_models[models_type].keys() for models_type in self.available_models.keys()]
            raise ValueError(f"Modèle '{models_name}' non disponible. Modèles disponibles: {available}")
        return str(model_path)
    
    def _download_model(self, models_name: str, models_type: str):
        """
        Télécharge un modèle
        
        Args:
            models_name: Nom du modèle à télécharger
            models_type: Type du modèle à télécharger
            
        Raises:
            RuntimeError: Si le téléchargement échoue
        """
        try:
            config = self.available_models[models_type][models_name]
            url = config["url"]
            filename = config["filename"]
            expected_size = config["size_mb"]
            
            model_path = self.dirs[models_type] / filename
            temp_path = model_path.with_suffix('.tmp')
            
            logger.info(f"Téléchargement de {models_name} depuis {url}")
            logger.info(f"   Taille attendue: ~{expected_size} MB")
            
            # Téléchargement avec progress
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # Log progress chaque 10MB
                        if downloaded_size % (10 * 1024 * 1024) < 8192:
                            progress = (downloaded_size / total_size * 100) if total_size > 0 else 0
                            logger.info(f"   Téléchargement: {progress:.1f}% ({downloaded_size/(1024*1024):.1f} MB)")
            
            # Vérifier la taille
            actual_size = temp_path.stat().st_size / (1024 * 1024)
            if abs(actual_size - expected_size) > expected_size * 0.1:  # Tolérance 10%
                logger.warning(f"Taille inattendue: {actual_size:.1f} MB vs {expected_size} MB attendus")
            
            # Déplacer le fichier temporaire
            temp_path.rename(model_path)
            
            logger.info(f"Modèle {models_name} téléchargé avec succès ({actual_size:.1f} MB)")
            
        except Exception as e:
            # Nettoyer le fichier temporaire
            if temp_path.exists():
                temp_path.unlink()
            
            error_msg = f"Erreur téléchargement {models_name}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _validate_model_simple(self, model_path: Path) -> bool:
        """
        VALIDATION SIMPLIFIÉE ET FIABLE - Corrige le problème de validation
        
        Args:
            model_path: Chemin vers le modèle
            
        Returns:
            True si le modèle est valide
        """
        try:
            # Vérifier existence
            if not model_path.exists():
                logger.warning(f"Modèle non trouvé: {model_path}")
                return False
            
            # Vérifier taille minimale (au moins 1 MB)
            actual_size = model_path.stat().st_size / (1024 * 1024)
            if actual_size < 1:
                logger.warning(f"Fichier trop petit: {actual_size:.1f} MB")
                return False
            
            # TEST ONNX RUNTIME - LE PLUS FIABLE
            try:
                import onnxruntime as ort
                # Essayer de charger le modèle avec ONNX Runtime
                session = ort.InferenceSession(
                    str(model_path), 
                    providers=['CPUExecutionProvider']
                )
                
                # Vérifier qu'il a des inputs/outputs
                inputs = session.get_inputs()
                outputs = session.get_outputs()
                
                if len(inputs) == 0 or len(outputs) == 0:
                    logger.warning(f"Modèle ONNX sans inputs/outputs: {model_path.name}")
                    return False
                
                logger.info(f"Modèle ONNX validé: {model_path.name} ({actual_size:.1f} MB)")
                return True
                
            except Exception as onnx_error:
                logger.warning(f"Validation ONNX échouée pour {model_path.name}: {str(onnx_error)}")
                return False
            
        except Exception as e:
            logger.warning(f"Erreur validation modèle {model_path.name}: {str(e)}")
            return False
    
    def delete_model(self, models_name: str) -> bool:
        """
        Supprime un modèle téléchargé
        
        Args:
            models_name: Nom du modèle à supprimer
            
        Returns:
            True si suppression réussie
        """
        try:
            for models_type in self.available_models.keys():
                if models_name not in self.available_models[models_type]:
                    continue
                
                config = self.available_models[models_type][models_name]
                model_path = self.dirs[models_type] / config["filename"]
                
                if model_path.exists():
                    model_path.unlink()
                    logger.info(f"Modèle {models_name} supprimé")
                    return True
                
            return False
            
        except Exception as e:
            logger.error(f"Erreur suppression modèle {models_name}: {str(e)}")
            return False
    
    def get_model_info(self, models_name: str) -> Optional[Dict]:
        """
        Retourne les informations d'un modèle
        
        Args:
            models_name: Nom du modèle
            
        Returns:
            Dictionnaire avec les infos ou None
        """
        for models_type in self.available_models.keys():
            if models_name not in self.available_models[models_type]:
                continue
            
            config = self.available_models[models_type][models_name].copy()
            model_path = self.dirs[models_type] / config["filename"]
            
            config["downloaded"] = model_path.exists()
            if config["downloaded"]:
                config["local_path"] = str(model_path)
                config["actual_size_mb"] = round(model_path.stat().st_size / (1024 * 1024), 1)
                # Validation simple
                config["valid"] = self._validate_model_simple(model_path)
        
        return config
    
    def cleanup_cache(self) -> Dict[str, int]:
        """
        Nettoie les fichiers obsolètes dans le cache
        
        Returns:
            Statistiques de nettoyage
        """
        stats = {
            "files_checked": 0,
            "files_deleted": 0,
            "space_freed_mb": 0
        }
        
        try:
            # Chercher tous les fichiers dans le répertoire modèles
            for models_type in self.available_models.keys():
                known_files = {config["filename"] for config in self.available_models[models_type].values()}
                
                model_dirs = self.dirs[models_type]

                for file_path in model_dirs.iterdir():
                    stats["files_checked"] += 1
                    
                    # Supprimer les fichiers temporaires
                    if file_path.suffix == '.tmp':
                        file_size = file_path.stat().st_size / (1024 * 1024)
                        file_path.unlink()
                        stats["files_deleted"] += 1
                        stats["space_freed_mb"] += file_size
                        logger.info(f"🗑️ Fichier temporaire supprimé: {file_path.name}")
                
                stats["space_freed_mb"] = round(stats["space_freed_mb"], 1)
                
                if stats["files_deleted"] > 0:
                    logger.info(f"Nettoyage terminé: {stats['files_deleted']} fichiers supprimés, {stats['space_freed_mb']} MB libérés")
            
            return stats
            
        except Exception as e:
            logger.error(f"Erreur nettoyage cache: {str(e)}")
            return stats

# Instance globale du gestionnaire de modèles
model_manager = ModelManager()
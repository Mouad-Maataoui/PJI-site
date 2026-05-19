import os
import logging
import numpy as np
import cv2
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import onnxruntime as ort
from PIL import Image, ImageOps
import io
from app.ml.base_onnx_processor import BaseONNXProcessor
from app.core.config import settings

logger = logging.getLogger(__name__)

class ONNXBackgroundRemover(BaseONNXProcessor):
    """
    Processeur ONNX pour la suppression d'arrière-plan d'images
    Supporte plusieurs modèles: RMBG-1.4, U2-Net, MODNet
    """
    
    def __init__(self, model_path: str = None, model_spec: str = "rmbg"):
        """
        Initialise le processeur ONNX
        
        Args:
            model_path: Chemin vers le modèle ONNX
            model_spec: Type de modèle ('rmbg', 'u2net', 'modnet')
        """
        # Configuration par modèle
        self.model_configs = {
            "rmbg": {
                "dynamic": False,
                "input_size": (1024, 1024),
                "normalize_mean": [0.5, 0.5, 0.5],
                "normalize_std": [1.0, 1.0, 1.0],
            },
            "u2net": {
                "dynamic": False,
                "input_size": (320, 320),
                "normalize_mean": [0.485, 0.456, 0.406],
                "normalize_std": [0.229, 0.224, 0.225],
            },
            "modnet": {
                "input_size": (512, 512),
                "normalize_mean": [0.5, 0.5, 0.5],
                "normalize_std": [0.5, 0.5, 0.5],
            },
            "birefnet": {
                "dynamic": True,
                "max_size": settings.MAX_SIZE_DYNAMIC,
                "normalize_mean": [0.485, 0.456, 0.406],
                "normalize_std": [0.229, 0.224, 0.225]
            }
        }
        
        if model_spec not in self.model_configs:
            raise ValueError(f"Type de modèle non supporté: {model_spec}")
        
        self.config = self.model_configs.get(model_spec)
        path = model_path 
        self.models_type = "bg_remove"
        self.spec = model_spec
        
        super().__init__(model_path=str(path), model_spec=model_spec)

  
    def preprocess_image(self, image: np.ndarray) -> Tuple[np.ndarray, Dict]:
        """
        Préprocessing de l'image pour l'inférence ONNX
        
        Args:
            image: Image numpy (H, W, C) en format BGR
            
        Returns:
            Tensor d'entrée normalisé (1, C, H, W)
            Informations de padding
        """
        try:
            # Convertir BGR vers RGB
            if len(image.shape) == 3 and image.shape[2] == 3:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Redimensionner à la taille d'entrée du modèle
            h, w, c = image.shape

            if self.config.get("dynamic", False):
                max_size = self.config.get("max_size")
                
                # A. Calculate Scale to fit within max_size
                scale = min(1.0, max_size / max(h, w))
                
                # B. Resize preserving aspect ratio
                new_w = int(w * scale)
                new_h = int(h * scale)
                
                # C. Align to multiples of 32 (Critical for UNet architectures)
                # We round to the nearest 32
                new_w = (new_w + 16) // 32 * 32
                new_h = (new_h + 16) // 32 * 32
                
                # Ensure we didn't shrink to 0
                new_w = max(32, new_w)
                new_h = max(32, new_h)
                
                image_resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                
                # No padding info needed for dynamic mode
                padding_info = {"original_size": (w, h), "mode": "dynamic"}
            else:
                input_height, input_width = self.config.get("input_size")
                scale = min(input_width / w, input_height / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                image_resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

                # 3. Create Square Canvas (Padding)
                # Create a black square canvas of the target size
                canvas = np.full((input_height, input_width, 3), 128, dtype=np.uint8) # 128 is neutral grey padding
                
                # Center the image on the canvas
                y_offset = (input_height - new_h) // 2
                x_offset = (input_width - new_w) // 2
                
                canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = image_resized

                image_resized = canvas
                
                # Store padding info for the post-processor
                padding_info = {
                    "mode": "fixed",
                    "new_w": new_w,
                    "new_h": new_h,
                    "x_offset": x_offset,
                    "y_offset": y_offset,
                    "original_size": (w, h)
                }

            
            # Normaliser [0, 255] -> [0, 1]
            image_normalized = image_resized.astype(np.float32) / 255.0
            
            # Normalisation spécifique au modèle
            mean = np.array(self.config["normalize_mean"], dtype=np.float32)
            std = np.array(self.config["normalize_std"], dtype=np.float32)
            image_normalized = (image_normalized - mean) / std
            
            # Convertir vers format ONNX (1, C, H, W)
            image_tensor = np.transpose(image_normalized, (2, 0, 1))  # (H, W, C) -> (C, H, W)
            image_tensor = np.expand_dims(image_tensor, axis=0)  # (C, H, W) -> (1, C, H, W)
            
            return image_tensor, padding_info
            
        except Exception as e:
            logger.error(f"Erreur preprocessing: {str(e)}")
            raise
    
    def postprocess_mask(self, mask: np.ndarray, original_size: Tuple[int, int], padding_info: Dict) -> np.ndarray:
        """
        Postprocessing du masque de sortie
        
        Args:
            mask: Masque de sortie du modèle (1, 1, H, W)
            original_size: Taille originale (width, height)
            padding_info: Information de padding
            
        Returns:
            Masque redimensionné (H, W) en [0, 255]
        """
        try:
            # Extraire le masque (1, 1, H, W) -> (H, W)
            if len(mask.shape) == 4:
                mask = mask[0, 0]  # Premier batch, premier canal
            elif len(mask.shape) == 3:
                mask = mask[0]  # Premier canal
            
            # Normaliser entre 0 et 1
            min_val, max_val = mask.min(), mask.max()
            if max_val > min_val:
                mask = (mask - min_val) / (max_val - min_val)

            if padding_info.get("mode") == "dynamic":
                # Just stretch the mask back to the original size.
                # Since we only adjusted dimensions slightly to fit the grid of 32,
                # the distortion is invisible.
                orig_w, orig_h = padding_info["original_size"]
                mask_final = cv2.resize(mask, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
            else:
                x_off = padding_info["x_offset"]
                y_off = padding_info["y_offset"]
                new_w = padding_info["new_w"]
                new_h = padding_info["new_h"]

                mask_cropped = mask[y_off:y_off+new_h, x_off:x_off+new_w]
                
                # Resize back to ORIGINAL resolution
                orig_w, orig_h = padding_info["original_size"]
                mask_final = cv2.resize(mask_cropped, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
            
            # Convert to Uint8
            mask_uint8 = (mask_final * 255).astype(np.uint8)
            
            return mask_uint8
            
        except Exception as e:
            logger.error(f"Erreur postprocessing: {str(e)}")
            raise
    
    def remove_background(self, image_path: str, output_path: str = None, 
                         background_color: Tuple[int, int, int] = None) -> str:
        """
        Supprime l'arrière-plan d'une image
        
        Args:
            image_path: Chemin vers l'image d'entrée
            output_path: Chemin de sortie (optionnel)
            background_color: Couleur d'arrière-plan (R, G, B) ou None pour transparent
            
        Returns:
            Chemin vers l'image de sortie
        """
        try:
            # Charger l'image
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Impossible de charger l'image: {image_path}")
            
            original_height, original_width = image.shape[:2]
            
            # Preprocessing
            input_tensor, padding_info = self.preprocess_image(image)
            
            # Inférence ONNX
            logger.info(f"Inférence ONNX {self.spec}...")
            outputs = self.session.run([self.output_name], {self.input_name: input_tensor})
            mask = outputs[0]
            
            # Postprocessing
            mask_final = self.postprocess_mask(mask, (original_width, original_height), padding_info)
            
            # Appliquer le masque
            result_image = self._apply_mask(image, mask_final, background_color)
            
            # Sauvegarder
            if output_path is None:
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                output_path = f"{base_name}_no_bg.png"
            
            # Assurer que le format est PNG pour la transparence
            if background_color is None and not output_path.lower().endswith('.png'):
                output_path = os.path.splitext(output_path)[0] + '.png'
            
            cv2.imwrite(output_path, result_image)
            
            logger.info(f"Arrière-plan supprimé: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Erreur suppression arrière-plan: {str(e)}")
            raise
    
    def _apply_mask(self, image: np.ndarray, mask: np.ndarray, 
                   background_color: Optional[Tuple[int, int, int]] = None) -> np.ndarray:
        """
        Applique le masque à l'image - VERSION CORRIGÉE
        
        Args:
            image: Image originale BGR
            mask: Masque en niveaux de gris [0, 255]
            background_color: Couleur d'arrière-plan ou None pour transparent
            
        Returns:
            Image avec arrière-plan supprimé
        """
        try:
            # Convertir BGR vers RGB
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            if background_color is None:
                # Arrière-plan transparent (RGBA)
                logger.info("Application masque avec arrière-plan transparent")
                
                # Créer canal alpha à partir du masque
                alpha = mask.astype(np.float32) / 255.0
                
                # Créer image RGBA
                result = np.zeros((image.shape[0], image.shape[1], 4), dtype=np.uint8)
                result[:, :, :3] = image_rgb  # Canaux RGB
                result[:, :, 3] = mask  # Canal alpha
                
                # Convertir RGBA vers BGRA pour OpenCV
                result = cv2.cvtColor(result, cv2.COLOR_RGBA2BGRA)
                
                logger.info("Masque transparent appliqué avec succès")
                
            else:
                # Arrière-plan coloré
                logger.info(f"Application masque avec arrière-plan coloré: {background_color}")
                
                # S'assurer que background_color est un tuple de 3 entiers
                if isinstance(background_color, str):
                    # Gérer les cas où background_color pourrait être une chaîne
                    if background_color.lower() in ['transparent', 'none']:
                        # Fallback vers transparent
                        return self._apply_mask(image, mask, None)
                    else:
                        # Essayer de parser la couleur hex
                        if background_color.startswith('#'):
                            bg_color = tuple(int(background_color[i:i+2], 16) for i in (1, 3, 5))
                        else:
                            # Couleur par défaut si parsing échoue
                            bg_color = (255, 255, 255)  # Blanc
                elif isinstance(background_color, (list, tuple)) and len(background_color) >= 3:
                    bg_color = tuple(int(c) for c in background_color[:3])
                else:
                    # Fallback vers blanc
                    bg_color = (255, 255, 255)
                
                # Convertir RGB vers BGR pour OpenCV
                bg_color_bgr = (bg_color[2], bg_color[1], bg_color[0])
                
                # Normaliser le masque [0, 1]
                alpha = mask.astype(np.float32) / 255.0
                alpha = np.expand_dims(alpha, axis=2)  # (H, W) -> (H, W, 1)
                
                # Mélanger avec la couleur d'arrière-plan
                result = image.astype(np.float32) * alpha + np.array(bg_color_bgr, dtype=np.float32) * (1 - alpha)
                result = result.astype(np.uint8)
                
                logger.info(f"Masque coloré appliqué: {bg_color}")
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur application masque: {str(e)}")
            # Debug des paramètres
            logger.error(f"   background_color type: {type(background_color)}")
            logger.error(f"   background_color value: {background_color}")
            raise
    
    def process_batch(self, image_paths: list, output_dir: str = "output", 
                     background_color: Optional[Tuple[int, int, int]] = None) -> list:
        """
        Traite un lot d'images
        
        Args:
            image_paths: Liste des chemins d'images
            output_dir: Répertoire de sortie
            background_color: Couleur d'arrière-plan
            
        Returns:
            Liste des chemins de sortie
        """
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        for i, image_path in enumerate(image_paths):
            try:
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                output_path = os.path.join(output_dir, f"{base_name}_no_bg.png")
                
                result_path = self.remove_background(image_path, output_path, background_color)
                results.append(result_path)
                
                logger.info(f"Traité {i+1}/{len(image_paths)}: {result_path}")
                
            except Exception as e:
                logger.error(f"Erreur traitement {image_path}: {str(e)}")
                results.append(None)
        
        return results

# Factory function pour créer le bon processeur
def create_background_remover(model_spec: str = "rmbg", model_path: str = None) -> ONNXBackgroundRemover:
    """
    Crée un processeur de suppression d'arrière-plan
    
    Args:
        model_spec: Type de modèle ('rmbg', 'u2net', 'modnet')
        model_path: Chemin personnalisé vers le modèle
        
    Returns:
        Instance du processeur ONNX
    """
    return ONNXBackgroundRemover(model_path=model_path, model_spec=model_spec)
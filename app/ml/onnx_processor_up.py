import os
import logging
import numpy as np
import cv2
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
import onnxruntime as ort
from PIL import Image, ImageOps
import io
from app.ml.base_onnx_processor import BaseONNXProcessor
from app.core.config import settings

logger = logging.getLogger(__name__)

class ONNXUpscale(BaseONNXProcessor):
    """
    Processeur ONNX pour l'upscale de la résolution d'images
    Supporte plusieurs modèles: RMBG-1.4, U2-Net, MODNet
    """
    
    def __init__(self, models_path: str = None, models_spec: str = "realesrgan-x4-plus"):
        """
        Initialise le processeur ONNX
        
        Args:
            models_path: Chemin vers le modèle ONNX
            models_type: Type de modèle ('rmbg', 'u2net', 'modnet')
        """
        # Configuration par modèle
        self.models_configs = {
            "realesrgan-x4-plus": {
                "tile_size": 128,
                "description": "Standard x4 Upscaling"
            },
            "realesrgan-general": {
                "tile_size": 128,
                "description": "Fast x4 Upscaling"
            },
            "swin2sr-x4": {
                "tile_size": 128,
                "description": "High Structure Fidelity x4"
            }
        }
        
        if models_spec not in self.models_configs:
            raise ValueError(f"Type de modèle non supporté: {models_spec}")
        
        self.config = self.models_configs.get(models_spec)
        path = models_path
        self.scale_factor = self.config.get("scale")
        self.tile_size = self.config.get("tile_size")
        self.models_type = "upscale"
        
        super().__init__(models_path=str(path), models_spec=models_spec)


    def process_image(self, image: np.ndarray) -> np.ndarray:
        """
        Main Entry Point: Decides between full processing or tiling.
        """
        h, w, _ = image.shape
        
        # Check if tiling is enabled and necessary
        # (i.e., we have a tile_size limit and the image exceeds it)
        if hasattr(self, 'tile_size') and self.tile_size and self.tile_size > 0:
            if h > self.tile_size or w > self.tile_size:
                logger.info(f"Image ({w}x{h}) exceeds tile limit ({self.tile_size}). Using Tiling Strategy.")
                return self._process_with_tiling(image)

        # Otherwise, process the full image at once (or if tile_size is None)
        return self._run_inference(image)

    def _process_with_tiling(self, image: np.ndarray) -> np.ndarray:
        """
        Handles cutting the image into tiles, processing them, and stitching back.
        """
        h, w, c = image.shape
        tile_size = self.tile_size
        
        # 1. Calculate Padding
        # We need the image dimensions to be a multiple of tile_size
        pad_h = (tile_size - (h % tile_size)) % tile_size
        pad_w = (tile_size - (w % tile_size)) % tile_size
        
        # Use Reflect padding to avoid hard edges at borders
        img_padded = cv2.copyMakeBorder(image, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
        pad_h_total, pad_w_total, _ = img_padded.shape

        # 2. Initialize Output Canvas
        # We process the first tile to detect the Scale Factor (e.g., x2, x4)
        first_tile = img_padded[0:tile_size, 0:tile_size]
        processed_first_tile = self._run_inference(first_tile)
        
        out_tile_h, out_tile_w, _ = processed_first_tile.shape
        scale_factor = out_tile_h // tile_size
        
        final_h = pad_h_total * scale_factor
        final_w = pad_w_total * scale_factor
        
        # Create empty large image for result
        output_canvas = np.zeros((final_h, final_w, 3), dtype=np.uint8)
        
        # Place the first tile we already computed
        output_canvas[0:out_tile_h, 0:out_tile_w] = processed_first_tile

        logger.info(f"Iterating over {pad_h_total//tile_size}x{pad_w_total//tile_size} for a total of {(pad_h_total//tile_size) * (pad_w_total//tile_size)}")

        # 3. Iterate over the rest of the tiles
        for y in range(0, pad_h_total, tile_size):
            logger.info(f"Currently at y: {y//tile_size} out of {pad_h_total//tile_size}")
            for x in range(0, pad_w_total, tile_size):
                # Skip the first one as we already did it
                if x == 0 and y == 0:
                    continue
                
                # Extract tile
                tile = img_padded[y : y+tile_size, x : x+tile_size]
                
                # Inference on tile
                processed_tile = self._run_inference(tile)
                
                # Calculate placement coordinates
                out_y = y * scale_factor
                out_x = x * scale_factor
                
                # Insert into canvas
                # We use specific shapes from processed_tile in case of minor model variance
                ph, pw, _ = processed_tile.shape
                output_canvas[out_y : out_y+ph, out_x : out_x+pw] = processed_tile

        # 4. Crop back to original valid region
        # We remove the padding we added at the beginning, but scaled up
        valid_h = h * scale_factor
        valid_w = w * scale_factor
        
        return output_canvas[0:valid_h, 0:valid_w]

    def _run_inference(self, image: np.ndarray) -> np.ndarray:
        """
        Core Inference Logic (The original process_image code):
        BGR Image -> Pre-process -> ONNX -> Post-process -> BGR Upscaled Image
        """
        try:
            # --- 1. PRE-PROCESS ---
            img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            img_float = img_rgb.astype(np.float32) / 255.0
            img_tensor = np.transpose(img_float, (2, 0, 1))
            img_tensor = np.expand_dims(img_tensor, axis=0)

            # --- 2. INFERENCE ---
            inputs = {self.input_name: img_tensor}
            outputs = self.session.run([self.output_name], inputs)
            result_tensor = outputs[0]

            # --- 3. POST-PROCESS ---
            result_tensor = np.squeeze(result_tensor, axis=0)
            result_tensor = np.transpose(result_tensor, (1, 2, 0))
            result_tensor = np.clip(result_tensor, 0, 1)
            result_uint8 = (result_tensor * 255.0).astype(np.uint8)
            
            return cv2.cvtColor(result_uint8, cv2.COLOR_RGB2BGR)

        except Exception as e:
            # Add context to error (helpful for debugging which tile failed)
            h, w = image.shape[:2]
            logger.error(f"Error during upscaling inference on chunk {w}x{h}: {str(e)}")
            raise

    def upscale_file(self, image_path: str, output_path: str = None, scale_factor: int = None) -> str:
        """
        Full pipeline: Reads file, Upscales, Saves file.
        """
        try:
            if scale_factor:
                self.scale_factor = scale_factor

            # 1. Load Image
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Input file not found: {image_path}")
                
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Could not decode image: {image_path}")

            h, w = image.shape[:2]
            logger.info(f"Upscaling image: {w}x{h} using {self.scale_factor}x model...")

            # 2. Process
            upscaled_image = self.process_image(image)
            
            # 3. Determine Output Path
            if output_path is None:
                base, ext = os.path.splitext(image_path)
                output_path = f"{base}_upscaled{ext}"

            # 4. Save
            # We use png by default for quality, or keep original extension
            cv2.imwrite(output_path, upscaled_image)
            
            new_h, new_w = upscaled_image.shape[:2]
            logger.info(f"Success! Saved to {output_path} ({new_w}x{new_h})")
            
            return output_path

        except Exception as e:
            logger.error(f"Failed to upscale file {image_path}: {e}")
            raise

    def process_batch(self, image_paths: List[str], output_dir: str = "output") -> List[str]:
        """
        Process a list of images.
        """
        os.makedirs(output_dir, exist_ok=True)
        results = []
        
        for img_path in image_paths:
            try:
                filename = os.path.basename(img_path)
                # Keep original name or add suffix
                save_path = os.path.join(output_dir, filename)
                
                result = self.upscale_file(img_path, save_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Skipping {img_path} due to error.")
                results.append(None)
                
        return results

# Factory function
def create_upscaler(models_path: str = None, models_spec: str = "realesrgan-x4-plus") -> ONNXUpscale:
    return ONNXUpscale(models_path=models_path, models_spec=models_spec)
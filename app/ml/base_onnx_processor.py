import os
import logging
import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class BaseONNXProcessor:
    """
    Classe parente pour la gestion de sessions ONNX, la détection de GPU, et le téléchargement des modèles.
    """
    def __init__(self, model_path: str = None, model_spec: str = None):
        self.model_path = model_path
        self.session = None
        self.input_name = None
        self.output_name = None
        self.model_spec = model_spec
        
        # Load model immediately
        self._load_model()

    def _load_model(self):
        try:
            # Si pas de chemin fourni, utiliser le chemin par défaut
            if not self.model_path:
                models_dir = Path("models")
                models_dir.mkdir(exist_ok=True)
                self.model_path = models_dir / f"{self.model_spec}.onnx"
            
            # Télécharger le modèle s'il n'existe pas
            if not os.path.exists(self.model_path):
                logger.info(f"Téléchargement du modèle {self.model_spec}...")
                self._download_model()

            available = ort.get_available_providers()
            
            # Configurer ONNX Runtime pour performance optimale
            providers = ['CPUExecutionProvider']
            
            # Essayer GPU si disponible
            if 'CUDAExecutionProvider' in available:
                providers = [
                    ('CUDAExecutionProvider', {
                        'device_id': 0,
                        'arena_extend_strategy': 'kNextPowerOfTwo',
                        'cudnn_conv_algo_search': 'EXHAUSTIVE',
                        'do_copy_in_default_stream': True,
                    }),
                    'CPUExecutionProvider',
                ]

            # Options de session pour l'optimisation
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            
            # Charger la session ONNX
            self.session = ort.InferenceSession(
                str(self.model_path), 
                sess_options=sess_options,
                providers=providers
            )
            
            
            # Récupérer les noms d'entrée et de sortie
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            
            logger.info(f"Modèle {self.model_spec} chargé avec succès")
            logger.info(f"   Input: {self.input_name}, Output: {self.output_name}")
            logger.info(f"   Providers: {self.session.get_providers()}, parmi: {available}")
        
        except Exception as e:
            logger.error(f"Erreur chargement modèle {self.model_spec}: {str(e)}")
            raise

    def _download_model(self):
        """Télécharge le modèle depuis l'URL"""
        import requests
        
        url = self.config["url"]
        
        try:
            logger.info(f"Téléchargement depuis: {url}")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Sauvegarder le modèle
            with open(self.model_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(self.model_path) / (1024 * 1024)
            logger.info(f"Modèle téléchargé: {file_size:.1f} MB")
            
        except Exception as e:
            logger.error(f"Erreur téléchargement modèle: {str(e)}")
            raise

    def process(self, image: np.ndarray):
        """Override this in child classes"""
        raise NotImplementedError
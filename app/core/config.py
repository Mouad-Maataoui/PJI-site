import secrets
from typing import Any, Dict, List, Optional, Union, Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    ALGORITHM: str = "HS256"
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []
    PROJECT_NAME: str = "Background Removal API"

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"  
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "background_removal"
    
    # Construire directement l'URL de la base de données en tant que chaîne
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        #return "postgresql://neondb_owner:npg_O9gWI4Rmzpjl@ep-lucky-union-ab9vsayn-pooler.eu-west-2.aws.neon.tech:5432/pji_2025_backend?sslmode=require&options=endpoint%3Dep-lucky-union-ab9vsayn"
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:5432/{self.POSTGRES_DB}"

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    
    # Construire les URLs pour Celery automatiquement
    @property
    def CELERY_BROKER_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.CELERY_BROKER_URL

    # Cloud storage configuration
    CLOUD_ACCOUNT_ID: str = ""
    CLOUD_ACCESS_KEY_ID: str = ""
    CLOUD_SECRET_ACCESS_KEY: str = ""
    CLOUD_BUCKET_NAME: str = ""
    CLOUD_IP: str = ""
    CLOUD_PORT: str = ""

    # Stripe Configuration - NOUVELLES VARIABLES
    STRIPE_API_KEY: str = ""  # sk_test_... ou sk_live_...
    STRIPE_WEBHOOK_SECRET: str = ""  # whsec_...
    STRIPE_PUBLISHABLE_KEY: str = ""  # pk_test_... ou pk_live_...
    
    # Configuration des points et paiements
    POINTS_PER_PURCHASE: int = 5  # Points reçus pour 10€
    POINTS_COST_PER_IMAGE: int = 1  # Points nécessaires par traitement d'image
    PURCHASE_AMOUNT_EUROS: int = 10  # Montant en euros pour l'achat de points
    
    # URLs de retour pour Stripe (frontend)
    STRIPE_SUCCESS_URL: str = "http://localhost:3000/payment/success"
    STRIPE_CANCEL_URL: str = "http://localhost:3000/payment/cancel"

    # Image Processing Configuration - TOUTES LES VARIABLES NÉCESSAIRES
    MODEL_TYPES: List[str] = ["bg_remove", "upscale"]
    MODEL_PATH: str = "models"
    IMAGE_STORAGE_PATH: str = "storage"
    IMAGE_RETENTION_DAYS: int = 7    
    MAX_IMAGE_SIZE_MB: int = 10  # Taille max en MB
    
    # IA et traitement d'images
    DEFAULT_AI_MODEL_BG: str = "rmbg-1.4-quantized"  # Modèle par défaut
    DEFAULT_AI_MODEL_UPSCALE: str = "realesrgan-x4plus-qualcomm"
    MAX_SIZE_DYNAMIC: int = 1024
    AI_PROCESSING_TIMEOUT: int = 300  # Timeout en secondes
    
    # Options de traitement d'images
    DEFAULT_BACKGROUND_COLOR: Optional[str] = None  # None = transparent, ou "#FFFFFF" pour blanc
    DEFAULT_OUTPUT_FORMAT: str = "png"  # png pour transparence, jpg pour plus petit
    DEFAULT_UPSCALE_RATIO: int = 2 
    
    # Configuration ONNX Runtime
    ONNX_EXECUTION_PROVIDERS: List[str] = ["CPUExecutionProvider"]  # Ou ["CUDAExecutionProvider", "CPUExecutionProvider"] pour GPU
    ONNX_GRAPH_OPTIMIZATION_LEVEL: str = "all"  # all, basic, extended, none
    
    # Limites de traitement
    MAX_IMAGE_RESOLUTION: int = 4096  # Résolution max en pixels (largeur ou hauteur)
    DEFAULT_IMAGE_WIDTH: int = 800
    DEFAULT_IMAGE_HEIGHT: int = 800    
    AI_CONCURRENT_TASKS: int = 2  # Nombre max de tâches IA en parallèle
    
    # Cache des modèles
    MODEL_CACHE_SIZE_GB: int = 5  # Taille max du cache en GB
    AUTO_DOWNLOAD_MODELS: bool = True  # Télécharger automatiquement les modèles manquants

    # HuggingFace — Détection deepfake
    HF_API_TOKEN: str = ""
    HF_DEEPFAKE_MODEL: str = "dima806/deepfake_vs_real_image_detection"
    HF_AI_DETECT_MODEL: str = "dima806/ai_vs_human_generated_image_detection"
    HF_TIMEOUT: int = 30  # secondes max par appel

    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "extra": "ignore",
    }

settings = Settings()
import logging
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, status

from app.services.auth_service import get_current_user
from app.services.deepfake_service import deepfake_service
from app.models.user import User
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/detect")
async def detect_deepfake(
    file: UploadFile = File(..., description="Image à analyser (JPG, PNG, WebP)"),
    current_user: User = Depends(get_current_user),
):
    """
    Analyse une image pour détecter des manipulations deepfake ou
    une génération par IA.

    Utilise 2 modèles HuggingFace en parallèle :
    - dima806/deepfake_vs_real_image_detection (visage manipulé)
    - dima806/ai_vs_human_generated_image_detection (image générée par IA)

    Retourne un verdict avec score de confiance.
    """
    # Vérifier le type de fichier
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de fichier non supporté : {file.content_type}. "
                   f"Utilisez : {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    # Lire l'image
    image_bytes = await file.read()

    # Vérifier la taille
    if len(image_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image trop grande ({len(image_bytes) // 1024 // 1024} MB). Maximum : 10 MB",
        )

    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fichier vide",
        )

    logger.info(f"Analyse deepfake — user={current_user.id} fichier={file.filename} taille={len(image_bytes)}B")

    try:
        result = await deepfake_service.detect(
            image_bytes=image_bytes,
            filename=file.filename,
        )
    except Exception as exc:
        logger.exception("Erreur inattendue dans deepfake_service.detect")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur service deepfake: {exc}",
        )

    if not result.success and result.error == "HF_API_TOKEN manquant dans .env":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service de détection non configuré. Ajoutez HF_API_TOKEN dans .env",
        )

    return result


@router.get("/models")
async def list_deepfake_models(
    current_user: User = Depends(get_current_user),
):
    """
    Liste les modèles de détection disponibles et leur configuration.
    """
    return {
        "models": [
            {
                "id": settings.HF_DEEPFAKE_MODEL,
                "name": "Deepfake vs Real",
                "task": "Détecte les visages manipulés (face-swap, GAN)",
                "labels": ["Fake", "Real"],
                "accuracy": "~90%",
                "weight": "60% dans le score agrégé",
            },
            {
                "id": settings.HF_AI_DETECT_MODEL,
                "name": "AI vs Human Generated",
                "task": "Détecte les images entièrement générées par IA",
                "labels": ["AI-generated", "Human-created"],
                "accuracy": "~98%",
                "weight": "40% dans le score agrégé",
            },
        ],
        "threshold": 0.50,
        "note": "Un score de confiance >= 50% déclenche is_manipulated=true",
        "api_configured": bool(settings.HF_API_TOKEN),
    }


@router.get("/health")
async def deepfake_health():
    """
    Vérifie que le token HuggingFace est configuré.
    Ne fait pas d'appel réseau, juste une vérification de config.
    """
    configured = bool(settings.HF_API_TOKEN)
    return {
        "configured": configured,
        "message": "Token HuggingFace présent" if configured else "HF_API_TOKEN manquant dans .env",
        "models": {
            "deepfake": settings.HF_DEEPFAKE_MODEL,
            "ai_detect": settings.HF_AI_DETECT_MODEL,
        },
    }
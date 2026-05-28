from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class SingleModelResult(BaseModel):
    """Résultat brut d'un seul modèle HuggingFace"""
    model_id: str
    label: str        # "Fake" / "Real" / "AI-generated" / "Human-created"
    score: float      # entre 0.0 et 1.0
    raw: List[Dict]   # réponse brute complète du modèle


class DeepfakeDetectionResponse(BaseModel):
    """Réponse finale agrégée retournée à l'utilisateur"""
    success: bool

    # Verdict principal
    is_manipulated: bool       # True si deepfake ou IA détecté
    confidence: float          # score de confiance global (0.0 → 1.0)
    verdict: str               # ex: "Deepfake détecté (94% confiance)"

    # Détail par modèle
    models_results: List[SingleModelResult]

    # Scores détaillés
    deepfake_score: float            # score du modèle deepfake_vs_real
    ai_generated_score: float        # score du modèle ai_vs_human

    # Métadonnées
    models_used: List[str]
    image_filename: Optional[str] = None
    error: Optional[str] = None      # message d'erreur si partial failure
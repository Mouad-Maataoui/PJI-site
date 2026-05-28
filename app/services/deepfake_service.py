import logging
import asyncio
import httpx
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings
from app.models.schemas.deepfake import SingleModelResult, DeepfakeDetectionResponse

logger = logging.getLogger(__name__)

HF_BASE_URL = "https://api-inference.huggingface.co/models"


class DeepfakeService:

    def __init__(self):
        self.token = settings.HF_API_TOKEN
        self.model_deepfake = settings.HF_DEEPFAKE_MODEL
        self.model_ai_detect = settings.HF_AI_DETECT_MODEL
        self.timeout = settings.HF_TIMEOUT
        self.headers = {"Authorization": f"Bearer {self.token}"}

    # ──────────────────────────────────────────────
    # Appel HTTP vers un seul modèle HuggingFace
    # ──────────────────────────────────────────────

    async def _call_model(
        self,
        client: httpx.AsyncClient,
        model_id: str,
        image_bytes: bytes,
    ) -> Tuple[bool, List[Dict], str]:
        """
        Envoie l'image à un modèle HuggingFace Inference API.
        Retourne (success, raw_response, error_detail).
        """
        url = f"{HF_BASE_URL}/{model_id}"
        try:
            response = await client.post(
                url,
                content=image_bytes,
                headers=self.headers,
                timeout=self.timeout,
            )

            if response.status_code == 503:
                data = response.json()
                wait_time = data.get("estimated_time", 20)
                logger.warning(f"Modèle {model_id} en chargement, attente {wait_time}s")
                await asyncio.sleep(min(wait_time, 30))
                response = await client.post(
                    url, content=image_bytes,
                    headers=self.headers, timeout=self.timeout
                )

            if response.status_code == 200:
                return True, response.json(), ""
            else:
                detail = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"Erreur {model_id}: {detail}")
                return False, [], detail

        except httpx.TimeoutException:
            msg = f"Timeout ({self.timeout}s) pour {model_id}"
            logger.error(msg)
            return False, [], msg
        except Exception as e:
            msg = f"Erreur {model_id}: {e}"
            logger.error(msg)
            return False, [], msg

    # ──────────────────────────────────────────────
    # Extraire le score "manipulé" d'une réponse brute
    # ──────────────────────────────────────────────

    def _extract_fake_score(self, raw: List[Dict], fake_labels: List[str]) -> float:
        """
        Cherche le score correspondant aux labels de manipulation.
        fake_labels = ["Fake", "AI-generated"] selon le modèle.
        Retourne 0.0 si rien trouvé.
        """
        for item in raw:
            if item.get("label") in fake_labels:
                return item.get("score", 0.0)
        return 0.0

    # ──────────────────────────────────────────────
    # Méthode principale : analyser une image
    # ──────────────────────────────────────────────

    async def detect(
        self,
        image_bytes: bytes,
        filename: Optional[str] = None,
    ) -> DeepfakeDetectionResponse:
        """
        Analyse une image avec 2 modèles en parallèle.
        Retourne un verdict agrégé.
        """
        if not self.token:
            return DeepfakeDetectionResponse(
                success=False,
                is_manipulated=False,
                confidence=0.0,
                verdict="Service non configuré",
                models_results=[],
                deepfake_score=0.0,
                ai_generated_score=0.0,
                models_used=[],
                image_filename=filename,
                error="HF_API_TOKEN manquant dans .env",
            )

        # Appels parallèles aux 2 modèles
        async with httpx.AsyncClient() as client:
            task1, task2 = await asyncio.gather(
                self._call_model(client, self.model_deepfake, image_bytes),
                self._call_model(client, self.model_ai_detect, image_bytes),
                return_exceptions=False,
            )

        success1, raw1, err1 = task1
        success2, raw2, err2 = task2

        # Si les deux ont échoué
        if not success1 and not success2:
            return DeepfakeDetectionResponse(
                success=False,
                is_manipulated=False,
                confidence=0.0,
                verdict="Analyse impossible — API HuggingFace inaccessible",
                models_results=[],
                deepfake_score=0.0,
                ai_generated_score=0.0,
                models_used=[],
                image_filename=filename,
                error=f"model1: {err1} | model2: {err2}",
            )

        # Extraire les scores de manipulation
        deepfake_score = self._extract_fake_score(raw1, ["Fake"]) if success1 else 0.0
        ai_score = self._extract_fake_score(raw2, ["AI-generated"]) if success2 else 0.0

        # Résultats individuels
        models_results = []
        models_used = []

        if success1 and raw1:
            top = max(raw1, key=lambda x: x["score"])
            models_results.append(SingleModelResult(
                model_id=self.model_deepfake,
                label=top["label"],
                score=top["score"],
                raw=raw1,
            ))
            models_used.append(self.model_deepfake)

        if success2 and raw2:
            top = max(raw2, key=lambda x: x["score"])
            models_results.append(SingleModelResult(
                model_id=self.model_ai_detect,
                label=top["label"],
                score=top["score"],
                raw=raw2,
            ))
            models_used.append(self.model_ai_detect)

        # Score agrégé : moyenne pondérée (deepfake pèse plus)
        if success1 and success2:
            confidence = (deepfake_score * 0.6) + (ai_score * 0.4)
        elif success1:
            confidence = deepfake_score
        else:
            confidence = ai_score

        # Seuil de décision : 50%
        is_manipulated = confidence >= 0.50

        # Verdict lisible
        pct = int(confidence * 100)
        if is_manipulated:
            if confidence >= 0.85:
                verdict = f"Deepfake/manipulation très probablement détecté ({pct}% confiance)"
            elif confidence >= 0.65:
                verdict = f"Manipulation probable ({pct}% confiance)"
            else:
                verdict = f"Manipulation possible ({pct}% confiance)"
        else:
            if confidence <= 0.20:
                verdict = f"Image authentique ({100 - pct}% confiance authenticité)"
            else:
                verdict = f"Probablement authentique ({100 - pct}% confiance authenticité)"

        partial_error = None
        if not success1:
            partial_error = f"Modèle {self.model_deepfake} indisponible: {err1}"
        elif not success2:
            partial_error = f"Modèle {self.model_ai_detect} indisponible: {err2}"

        return DeepfakeDetectionResponse(
            success=True,
            is_manipulated=is_manipulated,
            confidence=round(confidence, 4),
            verdict=verdict,
            models_results=models_results,
            deepfake_score=round(deepfake_score, 4),
            ai_generated_score=round(ai_score, 4),
            models_used=models_used,
            image_filename=filename,
            error=partial_error,
        )


# Instance partagée (singleton)
deepfake_service = DeepfakeService()
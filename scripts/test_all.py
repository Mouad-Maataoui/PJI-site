#!/usr/bin/env python3
"""
Script de test complet — tous les endpoints de Background Removal App

Usage:
    # 1. D'abord obtenir un token
    python scripts/auth_script.py

    # 2. Lancer les tests
    python scripts/test_all.py
"""

import io
import re
import sys
import time
import requests
from pathlib import Path
from typing import Optional

BASE_URL   = "http://localhost:8000/api/v1"
TOKEN_FILE = "auth_token.txt"
TIMEOUT    = 15   # secondes par requête
TASK_POLL_MAX = 30  # tentatives de polling (~60 s max)


# ──────────────────────────────────────────────
# Couleurs & helpers d'affichage
# ──────────────────────────────────────────────

class C:
    GREEN   = '\033[92m'
    RED     = '\033[91m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    CYAN    = '\033[96m'
    MAGENTA = '\033[95m'
    RESET   = '\033[0m'


def ok(msg):    print(f"{C.GREEN}  ✅ {msg}{C.RESET}")
def fail(msg):  print(f"{C.RED}  ❌ {msg}{C.RESET}")
def info(msg):  print(f"{C.BLUE}  ℹ  {msg}{C.RESET}")
def warn(msg):  print(f"{C.YELLOW}  ⚠  {msg}{C.RESET}")
def section(t): print(f"\n{C.CYAN}{'─'*60}\n  {t}\n{'─'*60}{C.RESET}")
def title(t):
    bar = '═' * 60
    print(f"\n{C.MAGENTA}{bar}\n  {t}\n{bar}{C.RESET}\n")


def print_json(data, indent=2):
    import json
    if isinstance(data, (dict, list)):
        print(f"{C.BLUE}{json.dumps(data, indent=indent, ensure_ascii=False, default=str)}{C.RESET}")
    else:
        print(f"  {data}")


# ──────────────────────────────────────────────
# Classe principale
# ──────────────────────────────────────────────

class Tester:
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token
        self._passed = 0
        self._failed = 0
        # IDs collectés pendant les tests pour les réutiliser
        self._task_id: Optional[str] = None
        self._payment_intent_id: Optional[str] = None

    # ── HTTP helper ──────────────────────────────
    def _req(self, method: str, path: str, *, auth=True, json=None,
             data=None, files=None) -> tuple[bool, int, any]:
        url = f"{self.base_url}{path}"
        headers = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = requests.request(
                method, url,
                headers=headers,
                json=json,
                data=data,
                files=files,
                timeout=TIMEOUT,
            )
            try:
                body = r.json()
            except Exception:
                body = r.text
            return r.status_code < 400, r.status_code, body
        except requests.exceptions.RequestException as e:
            return False, 0, str(e)

    # ── Enregistrement résultat ───────────────────
    def _record(self, name: str, success: bool, code: int = 0, detail: str = ""):
        tag = f"[{code}]" if code else ""
        if success:
            self._passed += 1
            ok(f"{name} {tag}")
        else:
            self._failed += 1
            fail(f"{name} {tag}  → {detail[:120]}")

    # ── Rapport final ─────────────────────────────
    def report(self):
        total = self._passed + self._failed
        print(f"\n{C.CYAN}{'═'*60}{C.RESET}")
        print(f"  Résultats : {self._passed}/{total} tests passés")
        if self._failed:
            print(f"  {C.RED}{self._failed} échec(s){C.RESET}")
        else:
            print(f"  {C.GREEN}Tous les tests sont verts ✅{C.RESET}")
        print(f"{C.CYAN}{'═'*60}{C.RESET}\n")

    # ── Créer image de test ───────────────────────
    @staticmethod
    def _make_image() -> bytes:
        """Génère une image PNG RGB 200×200 en mémoire (sans fichier disque)."""
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (200, 200), "white")
            draw = ImageDraw.Draw(img)
            draw.rectangle([40, 40, 160, 160], fill="blue")
            draw.ellipse([70, 70, 130, 130], fill="red")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            # Fallback: minimal valid PNG (1×1 blanc)
            return (
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
                b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
                b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
                b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
            )

    # ──────────────────────────────────────────────
    # Groupe 1 — Auth
    # ──────────────────────────────────────────────

    def test_auth(self):
        section("AUTH")

        # GET /auth/me
        ok_flag, code, body = self._req("GET", "/auth/me")
        self._record("GET /auth/me", ok_flag, code, str(body))
        if ok_flag and isinstance(body, dict):
            info(f"Connecté : {body.get('email', '?')}")

    # ──────────────────────────────────────────────
    # Groupe 2 — Images
    # ──────────────────────────────────────────────

    def test_images(self):
        section("IMAGES")

        img_bytes = self._make_image()

        # POST /images/upload
        import time as _time
        unique_name = f"test_{int(_time.time())}.png"
        ok_flag, code, body = self._req(
            "POST", "/images/upload",
            files={"file": (unique_name, img_bytes, "image/png")},
        )
        self._record("POST /images/upload", ok_flag, code, str(body))
        if ok_flag and isinstance(body, dict):
            # Récupérer le task_id depuis différents champs possibles
            self._task_id = (
                body.get("task_id")
                or body.get("id")
                or (body.get("data") or {}).get("task_id")
            )
            if self._task_id:
                info(f"Task ID : {self._task_id}")

        # GET /images/tasks
        ok_flag, code, body = self._req("GET", "/images/tasks")
        self._record("GET /images/tasks", ok_flag, code, str(body))

        if self._task_id:
            # GET /images/tasks/{task_id}
            ok_flag, code, body = self._req("GET", f"/images/tasks/{self._task_id}")
            self._record(f"GET /images/tasks/{{task_id}}", ok_flag, code, str(body))

            # Attendre que la tâche se termine (polling)
            info("Attente du traitement de la tâche...")
            final_status = self._wait_for_task(self._task_id)
            info(f"Statut final : {final_status}")

            if final_status == "completed":
                # GET /images/download/{task_id}
                ok_flag, code, body = self._req("GET", f"/images/download/{self._task_id}")
                self._record("GET /images/download/{task_id}", ok_flag, code,
                             str(body)[:80] if isinstance(body, str) else "")

                # GET /images/preview/{task_id}
                ok_flag, code, body = self._req("GET", f"/images/preview/{self._task_id}")
                self._record("GET /images/preview/{task_id}", ok_flag, code, str(body)[:80])
            else:
                warn(f"Download/preview ignorés — tâche en statut '{final_status}'")
                warn("Vérifiez que le worker Celery tourne : celery -A app.worker.celery_app worker --pool=solo --loglevel=INFO --queues=main-queue,low-queue")

        # GET /images/processed
        ok_flag, code, body = self._req("GET", "/images/processed")
        self._record("GET /images/processed", ok_flag, code, str(body))

        # DELETE /images/tasks/{task_id} — en dernier
        if self._task_id:
            ok_flag, code, body = self._req("DELETE", f"/images/tasks/{self._task_id}")
            self._record("DELETE /images/tasks/{task_id}", ok_flag, code, str(body))

    def _wait_for_task(self, task_id: str) -> str:
        """Polling jusqu'à completion ou timeout."""
        for _ in range(TASK_POLL_MAX):
            _, _, body = self._req("GET", f"/images/tasks/{task_id}")
            if isinstance(body, dict):
                status = body.get("status", "")
                if status in ("completed", "success", "done", "failed", "error"):
                    return status
            time.sleep(2)
        return "timeout"

    # ──────────────────────────────────────────────
    # Groupe 3 — Points & Paiements
    # ──────────────────────────────────────────────

    def test_points(self):
        section("POINTS & PAIEMENTS")

        # GET /points/balance
        ok_flag, code, body = self._req("GET", "/points/balance")
        self._record("GET /points/balance", ok_flag, code, str(body))
        if ok_flag and isinstance(body, dict):
            info(f"Solde : {body.get('points_balance', '?')} points")

        # GET /points/pricing  (public)
        ok_flag, code, body = self._req("GET", "/points/pricing", auth=False)
        self._record("GET /points/pricing", ok_flag, code, str(body))

        # GET /points/can-process
        ok_flag, code, body = self._req("GET", "/points/can-process")
        self._record("GET /points/can-process", ok_flag, code, str(body))

        # GET /points/transactions
        ok_flag, code, body = self._req("GET", "/points/transactions")
        self._record("GET /points/transactions", ok_flag, code, str(body))

        # GET /points/stats
        ok_flag, code, body = self._req("GET", "/points/stats")
        self._record("GET /points/stats", ok_flag, code, str(body))

        # POST /points/purchase/create-intent
        ok_flag, code, body = self._req(
            "POST", "/points/purchase/create-intent",
            json={"amount": 10},
        )
        self._record("POST /points/purchase/create-intent", ok_flag, code, str(body))
        if ok_flag and isinstance(body, dict):
            self._payment_intent_id = (
                (body.get("payment_data") or {}).get("payment_intent_id")
            )
            if self._payment_intent_id:
                info(f"Payment Intent : {self._payment_intent_id[:30]}...")

        # POST /points/test/simulate-payment-success
        if self._payment_intent_id:
            ok_flag, code, body = self._req(
                "POST",
                f"/points/test/simulate-payment-success?payment_intent_id={self._payment_intent_id}",
            )
            self._record("POST /points/test/simulate-payment-success", ok_flag, code, str(body))

        # GET /points/test/webhook-info
        ok_flag, code, body = self._req("GET", "/points/test/webhook-info")
        self._record("GET /points/test/webhook-info", ok_flag, code, str(body))

    # ──────────────────────────────────────────────
    # Groupe 4 — AI / Modèles
    # ──────────────────────────────────────────────

    def test_ai(self):
        section("AI / MODÈLES")

        # GET /ai/models
        ok_flag, code, body = self._req("GET", "/ai/models")
        self._record("GET /ai/models", ok_flag, code, str(body))

        first_model = None
        if ok_flag and isinstance(body, (list, dict)):
            models = body if isinstance(body, list) else body.get("models", [])
            if models and isinstance(models[0], dict):
                first_model = models[0].get("name") or models[0].get("model_name")
            elif models and isinstance(models[0], str):
                first_model = models[0]
            if first_model:
                info(f"Premier modèle trouvé : {first_model}")

        model_name = first_model or "rmbg-1.4"

        # GET /ai/models/{model_name}
        ok_flag, code, body = self._req("GET", f"/ai/models/{model_name}")
        self._record(f"GET /ai/models/{{model_name}}", ok_flag, code, str(body))

        # GET /ai/stats
        ok_flag, code, body = self._req("GET", "/ai/stats")
        self._record("GET /ai/stats", ok_flag, code, str(body))

        # POST /ai/cache/cleanup
        ok_flag, code, body = self._req("POST", "/ai/cache/cleanup")
        self._record("POST /ai/cache/cleanup", ok_flag, code, str(body))

    # ──────────────────────────────────────────────
    # Groupe 5 — Monitoring
    # ──────────────────────────────────────────────

    def test_monitoring(self):
        section("MONITORING")

        # GET /monitoring/health
        ok_flag, code, body = self._req("GET", "/monitoring/health", auth=False)
        self._record("GET /monitoring/health", ok_flag, code, str(body))
        if ok_flag and isinstance(body, dict):
            info(f"Status : {body.get('status', '?')}")

        # GET /monitoring/metrics
        ok_flag, code, body = self._req("GET", "/monitoring/metrics", auth=False)
        self._record("GET /monitoring/metrics", ok_flag, code,
                     "(prometheus text)" if ok_flag else str(body))

        # GET /monitoring/metrics/business
        ok_flag, code, body = self._req("GET", "/monitoring/metrics/business")
        self._record("GET /monitoring/metrics/business", ok_flag, code, str(body))

        # POST /monitoring/metrics/refresh
        ok_flag, code, body = self._req("POST", "/monitoring/metrics/refresh")
        self._record("POST /monitoring/metrics/refresh", ok_flag, code, str(body))

    # ──────────────────────────────────────────────
    # Groupe 6 — Racine & OpenAPI
    # ──────────────────────────────────────────────

    def test_root(self):
        section("ROOT")

        ok_flag, code, body = self._req("GET", "/", auth=False)
        # La racine est sur http://localhost:8000/ pas /api/v1/
        if not ok_flag:
            try:
                r = requests.get("http://localhost:8000/", timeout=TIMEOUT)
                ok_flag, code, body = r.status_code < 400, r.status_code, r.json() if r.headers.get("content-type","").startswith("application/json") else r.text
            except Exception:
                pass
        self._record("GET /", ok_flag, code, str(body)[:80])
    
    def test_deepfake(self):
        section("DEEPFAKE DETECTION")

        # GET /deepfake/health
        ok_flag, code, body = self._req("GET", "/deepfake/health", auth=False)
        self._record("GET /deepfake/health", ok_flag, code, str(body))

        if ok_flag and isinstance(body, dict):
            if not body.get("configured"):
                warn("HF_API_TOKEN non configuré — test /detect ignoré")
                return

        # GET /deepfake/models
        ok_flag, code, body = self._req("GET", "/deepfake/models")
        self._record("GET /deepfake/models", ok_flag, code, str(body))

        # POST /deepfake/detect  (image de test générée en mémoire)
        img_bytes = self._make_image()
        ok_flag, code, body = self._req(
            "POST", "/deepfake/detect",
            files={"file": ("test_deepfake.png", img_bytes, "image/png")},
        )
        self._record("POST /deepfake/detect", ok_flag, code, str(body))

        if ok_flag and isinstance(body, dict):
            info(f"Verdict     : {body.get('verdict', '?')}")
            info(f"Manipulé    : {body.get('is_manipulated', '?')}")
            info(f"Confiance   : {round(body.get('confidence', 0) * 100, 1)}%")
            info(f"Score deepfake : {round(body.get('deepfake_score', 0) * 100, 1)}%")
            info(f"Score IA       : {round(body.get('ai_generated_score', 0) * 100, 1)}%")

    # ──────────────────────────────────────────────
    # Tout en un
    # ──────────────────────────────────────────────

    def run_all(self):
        title("TEST COMPLET — Background Removal App")
        self.test_root()
        self.test_auth()
        self.test_points()
        self.test_images()
        self.test_ai()
        self.test_monitoring()
        self.test_deepfake()
        self.report()


# ──────────────────────────────────────────────
# Menu interactif
# ──────────────────────────────────────────────

MENU = """
  1  → Auth (GET /auth/me)
  2  → Images (upload, list, download, delete)
  3  → Points & Paiements
  4  → AI / Modèles
  5  → Monitoring & Health
  6  → ROOT
  7  → Deepfake Detection
  0  → Tout tester (rapport complet)
  q  → Quitter
"""


def load_token() -> Optional[str]:
    p = Path(TOKEN_FILE)
    if not p.exists():
        print(f"{C.RED}❌ Fichier {TOKEN_FILE} introuvable.{C.RESET}")
        print(f"   Lancez d'abord : python scripts/auth_script.py")
        return None
    m = re.search(r'TOKEN=(.+?)(?:\n|$)', p.read_text())
    return m.group(1).strip('"').strip() if m else None


def check_api() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/monitoring/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def main():
    title("Script de test complet — Background Removal App")
    print(f"  API : {BASE_URL}\n")

    if not check_api():
        print(f"{C.RED}❌ API inaccessible. Lancez d'abord : python run_dev.py{C.RESET}")
        sys.exit(1)

    print(f"{C.GREEN}✅ API accessible{C.RESET}")

    token = load_token()
    if not token:
        sys.exit(1)

    m = re.search(r'# Email: (.+)', Path(TOKEN_FILE).read_text())
    if m:
        print(f"{C.GREEN}✅ Connecté : {m.group(1).strip()}{C.RESET}")

    tester = Tester(BASE_URL, token)

    while True:
        print(f"\n{C.CYAN}{'─'*50}{C.RESET}")
        print(MENU)
        choice = input("  Choix : ").strip().lower()

        if   choice == "1": tester.test_auth()
        elif choice == "2": tester.test_images()
        elif choice == "3": tester.test_points()
        elif choice == "4": tester.test_ai()
        elif choice == "5": tester.test_monitoring()
        elif choice == "6": tester.test_root()
        elif choice == "7": tester.test_deepfake()
        elif choice == "0": tester.run_all()
        elif choice == "q":
            print(f"\n{C.YELLOW}Au revoir !{C.RESET}")
            break
        else:
            print(f"{C.RED}  Option invalide.{C.RESET}")

        if choice in ("1","2","3","4","5","6","7"):
            tester.report()
            # Reset compteurs pour le prochain groupe
            tester._passed = 0
            tester._failed = 0

        input(f"\n{C.BLUE}  Appuyez sur Entrée pour continuer...{C.RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Interrompu.{C.RESET}")

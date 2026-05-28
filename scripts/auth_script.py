#!/usr/bin/env python3
"""
Script d'authentification — Inscription et connexion
Sauvegarde le token dans auth_token.txt pour être utilisé par les autres scripts.

Usage:
    python scripts/auth_script.py
"""

import requests
from pathlib import Path
from typing import Optional

BASE_URL = "http://localhost:8000/api/v1"
TOKEN_FILE = "auth_token.txt"


class Colors:
    GREEN  = '\033[92m'
    RED    = '\033[91m'
    YELLOW = '\033[93m'
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    RESET  = '\033[0m'


def ok(msg):  print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")
def err(msg): print(f"{Colors.RED}❌ {msg}{Colors.RESET}")
def info(msg):print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")


# ──────────────────────────────────────────────
# API calls
# ──────────────────────────────────────────────

def check_api() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/monitoring/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def register(email: str, password: str, full_name: str) -> bool:
    """POST /auth/register"""
    try:
        # The API expects 'username' in the payload (UserCreate schema).
        # Use the email as username by default.
        payload = {"email": email, "username": email, "password": password}
        r = requests.post(
            f"{BASE_URL}/auth/register",
            json=payload,
            timeout=10,
        )
        if r.status_code in (200, 201):
            ok(f"Utilisateur créé : {email}")
            return True
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
        # Already registered is not a hard failure — continue to login
        if r.status_code == 400 and any(w in str(body).lower() for w in ("already", "exist", "registered")):
            info(f"Compte déjà existant : {email}")
            return True
        err(f"Inscription échouée ({r.status_code}) : {body}")
        return False
    except Exception as e:
        err(f"Erreur réseau : {e}")
        return False


def login(email: str, password: str) -> Optional[str]:
    """POST /auth/login  (OAuth2 form)"""
    try:
        r = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": email, "password": password},
            timeout=10,
        )
        if r.status_code == 200:
            token = r.json().get("access_token")
            if token:
                ok("Connexion réussie !")
                return token
        err(f"Login échoué ({r.status_code}) : {r.text}")
        return None
    except Exception as e:
        err(f"Erreur réseau : {e}")
        return None


def save_token(token: str, email: str):
    Path(TOKEN_FILE).write_text(f"# Email: {email}\nTOKEN={token}\n")
    ok(f"Token sauvegardé dans {TOKEN_FILE}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    print(f"\n{Colors.CYAN}{'='*55}{Colors.RESET}")
    print(f"{Colors.CYAN}  Script d'authentification — Background Removal App{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*55}{Colors.RESET}\n")

    info(f"API : {BASE_URL}")

    if not check_api():
        err("API inaccessible. Lancez d'abord : python run_dev.py")
        return

    ok("API accessible")
    print()

    email     = input("Email     (défaut: test@example.com) : ").strip() or "test@example.com"
    password  = input("Password  (défaut: Test1234!)        : ").strip() or "Test1234!"
    full_name = input("Nom       (défaut: Test User)         : ").strip() or "Test User"

    print()
    if not register(email, password, full_name):
        return

    token = login(email, password)
    if not token:
        return

    save_token(token, email)
    print()
    ok("Prêt ! Lancez maintenant :")
    print(f"   python scripts/test_all.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Interrompu.{Colors.RESET}")

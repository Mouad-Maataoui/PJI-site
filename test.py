# scripts/test_auth_manual.py
import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:8000/api/v1"

def test_register():
    """Teste l'enregistrement d'un nouvel utilisateur"""
    print("\n=== Test d'enregistrement ===")
    
    # Données avec un timestamp pour éviter les conflits
    timestamp = int(time.time())
    user_data = {
        "email": f"test{timestamp}@example.com",
        "username": f"testuser{timestamp}",
        "password": "password123"
    }
    
    print(f"Envoi des données: {json.dumps(user_data)}")
    
    try:
        response = requests.post(f"{BASE_URL}/auth/register", json=user_data, timeout=5)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            print(f"Réponse: {json.dumps(response.json(), indent=2)}")
            return response.json()
        else:
            print(f"Erreur: {response.text}")
            return None
    except Exception as e:
        print(f"Exception lors de la requête: {e}")
        return None

def test_login(email, password):
    """Teste la connexion"""
    print("\n=== Test de connexion ===")
    
    # Données d'authentification
    login_data = {
        "username": email,  # OAuth2 utilise username pour l'email
        "password": password
    }
    
    print(f"Envoi des données: {json.dumps(login_data)}")
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", data=login_data, timeout=5)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            print(f"Réponse: {json.dumps(response.json(), indent=2)}")
            return response.json()
        else:
            print(f"Erreur: {response.text}")
            return None
    except Exception as e:
        print(f"Exception lors de la requête: {e}")
        return None

def test_me(token):
    """Teste l'endpoint /me"""
    print("\n=== Test de l'endpoint /me ===")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    print(f"En-têtes: {json.dumps(headers)}")
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=5)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            print(f"Réponse: {json.dumps(response.json(), indent=2)}")
            return response.json()
        else:
            print(f"Erreur: {response.text}")
            return None
    except Exception as e:
        print(f"Exception lors de la requête: {e}")
        return None

def run_tests():
    """Exécute tous les tests manuellement"""
    print("Démarrage des tests d'authentification")
    
    # 1. Enregistrer un utilisateur
    user = test_register()
    if not user:
        print("❌ Test d'enregistrement échoué")
        return
    
    # 2. Se connecter
    login_data = test_login(user["email"], "password123")
    if not login_data or "access_token" not in login_data:
        print("❌ Test de connexion échoué")
        return
    
    # 3. Obtenir les informations de l'utilisateur
    me_data = test_me(login_data["access_token"])
    if not me_data:
        print("❌ Test de l'endpoint /me échoué")
        return
    
    print("\n✅ Tous les tests ont réussi!")

if __name__ == "__main__":
    run_tests()
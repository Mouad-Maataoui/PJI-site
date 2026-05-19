#!/usr/bin/env python3
"""
Script de test pour le système de paiement Stripe
Usage: python test_payment_system.py
"""

import asyncio
import json
import requests
import sys
from typing import Dict, Any

# Configuration de test
BASE_URL = "http://localhost:8000/api/v1"
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "password"

class PaymentTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.session = requests.Session()
    
    def test_user_registration_login(self) -> bool:
        """Test d'inscription et connexion utilisateur"""
        print("🔐 Test inscription/connexion utilisateur...")
        
        # Inscription
        register_data = {
            "email": TEST_USER_EMAIL,
            "username": "testuser",
            "password": TEST_USER_PASSWORD
        }
        
        try:
            # Essayer de s'inscrire (peut échouer si l'utilisateur existe déjà)
            response = self.session.post(f"{self.base_url}/auth/register", json=register_data)
            if response.status_code not in [200, 400]:  # 400 = utilisateur existe déjà
                print(f"❌ Erreur inscription: {response.status_code} - {response.text}")
                return False
            
            # Connexion
            login_data = {
                "username": TEST_USER_EMAIL,  # FastAPI OAuth2 utilise username pour email
                "password": TEST_USER_PASSWORD
            }
            
            response = self.session.post(f"{self.base_url}/auth/login", data=login_data)
            if response.status_code != 200:
                print(f"❌ Erreur connexion: {response.status_code} - {response.text}")
                return False
            
            token_data = response.json()
            self.token = token_data["access_token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            
            print("✅ Inscription/connexion réussie")
            return True
            
        except Exception as e:
            print(f"❌ Erreur inscription/connexion: {str(e)}")
            return False
    
    def test_points_balance(self) -> Dict[str, Any]:
        """Test récupération du solde de points"""
        print("💰 Test récupération solde de points...")
        
        try:
            response = self.session.get(f"{self.base_url}/points/balance")
            
            if response.status_code != 200:
                print(f"❌ Erreur balance: {response.status_code} - {response.text}")
                return {}
            
            balance_data = response.json()
            print(f"✅ Solde actuel: {balance_data['points_balance']} points")
            return balance_data
            
        except Exception as e:
            print(f"❌ Erreur récupération balance: {str(e)}")
            return {}
    
    def test_pricing_info(self) -> bool:
        """Test récupération des informations de tarification"""
        print("💵 Test informations de tarification...")
        
        try:
            response = self.session.get(f"{self.base_url}/points/pricing")
            
            if response.status_code != 200:
                print(f"❌ Erreur pricing: {response.status_code} - {response.text}")
                return False
            
            pricing_data = response.json()
            print(f"✅ Tarification: {pricing_data['points_system']}")
            return True
            
        except Exception as e:
            print(f"❌ Erreur récupération pricing: {str(e)}")
            return False
    
    def test_payment_intent_creation(self) -> Dict[str, Any]:
        """Test création d'un PaymentIntent"""
        print("💳 Test création PaymentIntent...")
        
        try:
            response = self.session.post(f"{self.base_url}/points/purchase/create-intent")
            
            if response.status_code != 200:
                print(f"❌ Erreur PaymentIntent: {response.status_code} - {response.text}")
                return {}
            
            intent_data = response.json()
            print(f"✅ PaymentIntent créé: {intent_data['payment_data']['payment_intent_id']}")
            print(f"   Client Secret: {intent_data['payment_data']['client_secret'][:20]}...")
            return intent_data
            
        except Exception as e:
            print(f"❌ Erreur création PaymentIntent: {str(e)}")
            return {}
    
    def test_can_process_check(self) -> bool:
        """Test vérification capacité de traitement"""
        print("🔍 Test vérification capacité de traitement...")
        
        try:
            response = self.session.get(f"{self.base_url}/points/can-process")
            
            if response.status_code != 200:
                print(f"❌ Erreur can-process: {response.status_code} - {response.text}")
                return False
            
            check_data = response.json()
            can_process = check_data["can_process"]
            print(f"✅ Peut traiter: {can_process} (Balance: {check_data['current_balance']}, Requis: {check_data['points_needed']})")
            return True
            
        except Exception as e:
            print(f"❌ Erreur vérification can-process: {str(e)}")
            return False
    
    def test_transactions_history(self) -> bool:
        """Test récupération historique des transactions"""
        print("📋 Test historique des transactions...")
        
        try:
            response = self.session.get(f"{self.base_url}/points/transactions")
            
            if response.status_code != 200:
                print(f"❌ Erreur transactions: {response.status_code} - {response.text}")
                return False
            
            transactions_data = response.json()
            print(f"✅ Transactions récupérées: {len(transactions_data['transactions'])} transactions")
            return True
            
        except Exception as e:
            print(f"❌ Erreur récupération transactions: {str(e)}")
            return False
    
    def test_stats(self) -> bool:
        """Test récupération des statistiques"""
        print("📊 Test statistiques paiements...")
        
        try:
            response = self.session.get(f"{self.base_url}/points/stats")
            
            if response.status_code != 200:
                print(f"❌ Erreur stats: {response.status_code} - {response.text}")
                return False
            
            stats_data = response.json()
            print(f"✅ Stats récupérées: {stats_data['global_stats']}")
            return True
            
        except Exception as e:
            print(f"❌ Erreur récupération stats: {str(e)}")
            return False
    
    def run_all_tests(self) -> bool:
        """Lance tous les tests"""
        print("🚀 Début des tests du système de paiement")
        print("=" * 50)
        
        tests = [
            ("Inscription/Connexion", self.test_user_registration_login),
            ("Solde de points", lambda: bool(self.test_points_balance())),
            ("Informations tarifaires", self.test_pricing_info),
            ("Création PaymentIntent", lambda: bool(self.test_payment_intent_creation())),
            ("Vérification capacité", self.test_can_process_check),
            ("Historique transactions", self.test_transactions_history),
            ("Statistiques", self.test_stats),
        ]
        
        results = []
        for test_name, test_func in tests:
            print(f"\n--- Test: {test_name} ---")
            try:
                result = test_func()
                results.append((test_name, result))
                if not result:
                    print(f"⚠️ Test {test_name} échoué")
            except Exception as e:
                print(f"❌ Erreur test {test_name}: {str(e)}")
                results.append((test_name, False))
        
        print("\n" + "=" * 50)
        print("📋 RÉSUMÉ DES TESTS")
        print("=" * 50)
        
        passed = 0
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
            if result:
                passed += 1
        
        print(f"\nRésultat: {passed}/{len(results)} tests réussis")
        
        if passed == len(results):
            print("🎉 Tous les tests sont passés ! Le système de paiement fonctionne.")
            return True
        else:
            print("⚠️ Certains tests ont échoué. Vérifiez la configuration.")
            return False

def main():
    """Fonction principale"""
    print("🧪 Testeur du système de paiement Stripe")
    print("Assurez-vous que:")
    print("1. Le serveur FastAPI est lancé (python run_dev.py)")
    print("2. La base de données est configurée")
    print("3. Les variables Stripe sont dans le .env")
    print()
    
    tester = PaymentTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎯 Prochaines étapes:")
        print("1. Tester les paiements avec Stripe CLI")
        print("2. Configurer les webhooks")
        print("3. Intégrer avec le frontend")
    else:
        print("\n🔧 Actions recommandées:")
        print("1. Vérifier les logs du serveur")
        print("2. Contrôler les variables d'environnement")
        print("3. Tester les endpoints individuellement")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
# tests/debug_routes.py
"""
Script de debug pour analyser les routes de l'application
"""
import sys
import os

# Add the project root directory to Python's search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from app.main import app

def debug_all_routes():
    """Debug complet de toutes les routes"""
    print("🔍 ANALYSE COMPLÈTE DES ROUTES")
    print("=" * 50)
    
    print(f"📱 Type d'app: {type(app)}")
    print(f"📊 Nombre total de routes: {len(app.routes)}")
    
    print("\n📋 TOUTES LES ROUTES DÉTECTÉES:")
    print("-" * 30)
    
    for i, route in enumerate(app.routes):
        print(f"{i+1}. Route: {route}")
        print(f"   Type: {type(route)}")
        
        # Attributs disponibles
        attrs = [attr for attr in dir(route) if not attr.startswith('_')]
        print(f"   Attributs: {attrs}")
        
        # Path si disponible
        if hasattr(route, 'path'):
            print(f"   Path: {route.path}")
        
        # Methods si disponible
        if hasattr(route, 'methods'):
            print(f"   Methods: {route.methods}")
        
        # Si c'est un Mount ou APIRouter
        if hasattr(route, 'routes'):
            print(f"   🔗 Sous-routes ({len(route.routes)}):")
            for j, subroute in enumerate(route.routes):
                print(f"      {j+1}. {subroute}")
                if hasattr(subroute, 'path'):
                    print(f"         Path: {subroute.path}")
                if hasattr(subroute, 'methods'):
                    print(f"         Methods: {subroute.methods}")
        
        print()

def test_specific_endpoints():
    """Test des endpoints spécifiques"""
    client = TestClient(app)
    
    print("🎯 TEST D'ENDPOINTS SPÉCIFIQUES")
    print("=" * 40)
    
    # Liste des endpoints à tester
    endpoints_to_test = [
        "/",
        "/api/v1/auth/register",
        "/api/v1/auth/login", 
        "/api/v1/images/upload",
        "/api/v1/images/tasks",
        "/api/images/upload",
        "/api/images/tasks",
        "/images/upload",
        "/images/tasks",
        "/upload",
        "/tasks"
    ]
    
    for endpoint in endpoints_to_test:
        try:
            response = client.get(endpoint)
            print(f"✅ GET {endpoint} -> {response.status_code}")
        except Exception as e:
            print(f"❌ GET {endpoint} -> Erreur: {e}")
        
        try:
            response = client.post(endpoint)
            print(f"📤 POST {endpoint} -> {response.status_code}")
        except Exception as e:
            print(f"❌ POST {endpoint} -> Erreur: {e}")

def check_router_imports():
    """Vérifier que les routers sont bien importés"""
    print("\n🔧 VÉRIFICATION DES IMPORTS")
    print("=" * 35)
    
    try:
        from app.api.routes.images import router as images_router
        print(f"✅ Router images importé: {images_router}")
        print(f"   Routes dans le router: {len(images_router.routes)}")
        for route in images_router.routes:
            print(f"   - {route.path} ({route.methods})")
    except Exception as e:
        print(f"❌ Erreur import router images: {e}")
    
    try:
        from app.api.routes.auth import router as auth_router
        print(f"✅ Router auth importé: {auth_router}")
        print(f"   Routes dans le router: {len(auth_router.routes)}")
        for route in auth_router.routes:
            print(f"   - {route.path} ({route.methods})")
    except Exception as e:
        print(f"❌ Erreur import router auth: {e}")

def check_openapi_schema():
    """Vérifier le schéma OpenAPI pour voir les routes"""
    print("\n📄 SCHÉMA OPENAPI")
    print("=" * 25)
    
    try:
        schema = app.openapi()
        paths = schema.get('paths', {})
        print(f"📊 Nombre de paths dans OpenAPI: {len(paths)}")
        
        for path in sorted(paths.keys()):
            methods = list(paths[path].keys())
            print(f"   {path} -> {methods}")
            
    except Exception as e:
        print(f"❌ Erreur récupération OpenAPI: {e}")

def main():
    """Fonction principale de debug"""
    debug_all_routes()
    test_specific_endpoints()
    check_router_imports()
    check_openapi_schema()
    
    print("\n🎉 DEBUG TERMINÉ!")
    print("Utilisez ces informations pour corriger les préfixes des routes dans vos tests.")

if __name__ == "__main__":
    main()

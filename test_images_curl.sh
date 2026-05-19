#!/bin/bash

# Script de test complet pour les routes d'images
# Usage: ./test_images_api.sh

BASE_URL="http://localhost:8000/api/v1"
TEST_EMAIL="ameur@example.com"
TEST_PASSWORD="password123"
TEST_USERNAME="ameur"

echo "🚀 Test des routes d'images - API Backend Remove BG"
echo "=================================================="

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Fonction d'aide
print_step() {
    echo -e "\n${YELLOW}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Vérifier qu'une image de test existe
if [ ! -f "test.jpg" ] && [ ! -f "test.png" ]; then
    print_error "Aucune image de test trouvée (test.jpg ou test.png)"
    echo "Créez une image de test ou téléchargez-en une :"
    echo "curl -o test.jpg https://via.placeholder.com/500x300.jpg"
    exit 1
fi

# Déterminer le fichier de test
TEST_IMAGE="test.jpg"
if [ -f "test.png" ]; then
    TEST_IMAGE="test.png"
fi

print_step "Étape 1: Enregistrement utilisateur"
register_response=$(curl -s -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"username\": \"$TEST_USERNAME\", 
    \"password\": \"$TEST_PASSWORD\"
  }")

if echo "$register_response" | grep -q "error\|Error"; then
    print_error "Échec enregistrement (utilisateur existe peut-être déjà)"
    echo "$register_response"
else
    print_success "Utilisateur créé ou existe déjà"
fi

print_step "Étape 2: Connexion et récupération token"
login_response=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$TEST_EMAIL&password=$TEST_PASSWORD")

echo "Réponse login: $login_response"

# Extraire le token
TOKEN=$(echo "$login_response" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    print_error "Impossible de récupérer le token JWT"
    echo "Réponse: $login_response"
    exit 1
fi

print_success "Token JWT récupéré: ${TOKEN}"

print_step "Étape 3: Test profil utilisateur"
profile_response=$(curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $TOKEN")
echo "Profil: $profile_response"

print_step "Étape 4: Upload d'image pour traitement"
upload_response=$(curl -s -X POST "$BASE_URL/images/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TEST_IMAGE" \
  -F "quality=85" \
  -F "force_process=True" \
  -F "background_color=transparent")

echo "Réponse upload: $upload_response"

# Extraire l'ID de la tâche
TASK_ID=$(echo "$upload_response" | grep -o '"task_id":[0-9]*' | cut -d':' -f2)

if [ -z "$TASK_ID" ]; then
    print_error "Impossible de récupérer l'ID de la tâche"
    exit 1
fi

print_success "Tâche créée avec ID: $TASK_ID"

print_step "Étape 5: Vérification liste des tâches"
tasks_response=$(curl -s -X GET "$BASE_URL/images/tasks" \
  -H "Authorization: Bearer $TOKEN")
echo "Liste tâches: $tasks_response"

print_step "Étape 6: Détails de la tâche $TASK_ID"
task_details_response=$(curl -s -X GET "$BASE_URL/images/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN")
echo "Détails tâche: $task_details_response"

print_step "Étape 7: Attente du traitement (30 secondes)..."
echo "⏳ Patientez pendant que l'IA traite l'image..."
sleep 30

print_step "Étape 8: Vérification du statut après traitement"
task_status_response=$(curl -s -X GET "$BASE_URL/images/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN")
echo "Statut après traitement: $task_status_response"

STATUS=$(echo "$task_status_response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
echo "Statut extrait: $STATUS"

if [ "$STATUS" = "completed" ]; then
    print_success "Traitement terminé avec succès!"
    
    print_step "Étape 9: Téléchargement de l'image traitée"
    curl -X GET "$BASE_URL/images/download/$TASK_ID" \
      -H "Authorization: Bearer $TOKEN" \
      -o "processed_$TEST_IMAGE"
    
    if [ -f "processed_$TEST_IMAGE" ]; then
        print_success "Image téléchargée: processed_$TEST_IMAGE"
        ls -la "processed_$TEST_IMAGE"
    else
        print_error "Échec téléchargement"
    fi
    
elif [ "$STATUS" = "failed" ]; then
    print_error "Traitement échoué"
    
    print_step "Étape 9: Test relance du traitement"
    retry_response=$(curl -s -X POST "$BASE_URL/images/retry/$TASK_ID" \
      -H "Authorization: Bearer $TOKEN" \
      -F "quality=90" \
      -F "background_color=white")
    echo "Réponse relance: $retry_response"
    
else
    print_error "Traitement encore en cours ou statut inconnu: $STATUS"
fi

print_step "Étape 10: Test suppression de la tâche"
delete_response=$(curl -s -X DELETE "$BASE_URL/images/tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN")
echo "Réponse suppression: $delete_response"

print_step "Tests terminés!"
echo "=========================================="
echo "📊 Résumé:"
echo "- Token JWT: ✅"
echo "- Upload image: ✅" 
echo "- Statut final: $STATUS"
echo "- Fichier traité: $([ -f "processed_$TEST_IMAGE" ] && echo "✅" || echo "❌")"

print_success "Tests des routes d'images terminés!"
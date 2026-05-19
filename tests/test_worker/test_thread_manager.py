# tests/test_worker/test_thread_manager.py
import pytest
import time
import threading
from unittest.mock import MagicMock

from app.worker.thread_manager import ThreadManager

def test_start_thread():
    """Test du démarrage d'un thread"""
    manager = ThreadManager()
    
    # Créer un Event pour synchroniser le test
    event = threading.Event()
    
    # Mock de fonction avec pause
    def slow_func(*args, **kwargs):
        # Attendre que le test vérifie que le thread est en vie
        event.wait(timeout=1.0)
        return {"test": "value"}
    
    mock_func = MagicMock(side_effect=slow_func)
    
    # Démarrer le thread
    thread = manager.start_thread("test_thread", mock_func, "arg1", "arg2", kwarg1="value1")
    
    # Vérifier que le thread a été créé
    assert "test_thread" in manager.threads
    assert isinstance(thread, threading.Thread)
    
    # Vérifier que le thread est en cours d'exécution
    assert thread.is_alive()
    
    # Signaler au thread de continuer
    event.set()
    
    # Attendre que le thread se termine
    thread.join(timeout=1.0)
    
    # Vérifier que la fonction a été appelée avec les bons arguments
    mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1")
    
    # Vérifier que le résultat a été stocké
    assert "test_thread" in manager.results
    assert manager.results["test_thread"] == {"test": "value"}
    
def test_wait_all():
    """Test d'attente de tous les threads"""
    manager = ThreadManager()
    
    # Créer des fonctions qui prennent du temps
    def slow_function(duration):
        time.sleep(duration)
        return duration
    
    # Démarrer plusieurs threads
    manager.start_thread("thread1", slow_function, 0.1)
    manager.start_thread("thread2", slow_function, 0.2)
    
    # Mesurer le temps d'attente
    start_time = time.time()
    results = manager.wait_all()
    elapsed_time = time.time() - start_time
    
    # Vérifier que l'attente a duré au moins 0.2 seconde (thread le plus long)
    assert elapsed_time >= 0.2
    
    # Vérifier que tous les résultats sont présents
    assert "thread1" in results
    assert "thread2" in results
    assert results["thread1"] == 0.1
    assert results["thread2"] == 0.2

def test_thread_error_handling():
    """Test de gestion d'erreur dans un thread"""
    manager = ThreadManager()
    
    # Fonction qui lève une exception
    def error_function():
        raise ValueError("Test error")
    
    # Démarrer le thread
    manager.start_thread("error_thread", error_function)
    
    # Attendre que le thread termine
    with pytest.raises(Exception) as excinfo:
        manager.wait_all()
    
    # Vérifier que l'erreur a été capturée et remontée
    assert "Erreurs dans les threads: error_thread: Test error" in str(excinfo.value)
    
    # Vérifier que l'erreur a été stockée
    assert "error_thread" in manager.errors
    assert isinstance(manager.errors["error_thread"], ValueError)
    assert str(manager.errors["error_thread"]) == "Test error"

def test_is_running():
    """Test de vérification si un thread est en cours d'exécution"""
    manager = ThreadManager()
    
    # Fonction qui prend du temps
    def slow_function():
        time.sleep(0.2)
    
    # Démarrer le thread
    manager.start_thread("test_thread", slow_function)
    
    # Vérifier que le thread est en cours d'exécution
    assert manager.is_running("test_thread") is True
    
    # Attendre que le thread termine
    manager.wait_all()
    
    # Vérifier que le thread n'est plus en cours d'exécution
    assert manager.is_running("test_thread") is False
    
    # Vérifier qu'un thread inexistant n'est pas en cours d'exécution
    assert manager.is_running("nonexistent_thread") is False
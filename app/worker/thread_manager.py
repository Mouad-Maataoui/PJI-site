import threading
import logging
from typing import Dict, Any, Callable

logger = logging.getLogger(__name__)

class ThreadManager:
    """Gestionnaire de threads pour exécuter des tâches en parallèle"""
    
    def __init__(self):
        self.threads = {}
        self.results = {}
        self.errors = {}
    
    def start_thread(self, name: str, target_func: Callable, *args, **kwargs):
        """Démarrer un nouveau thread avec la fonction cible et les arguments"""
        thread = threading.Thread(
            target=self._thread_wrapper,
            args=(name, target_func, args, kwargs)
        )
        self.threads[name] = thread
        thread.start()
        logger.info(f"Thread '{name}' démarré")
        return thread
    
    def _thread_wrapper(self, name: str, target_func: Callable, args: tuple, kwargs: Dict[str, Any]):
        """Wrapper qui capture les résultats et les exceptions des threads"""
        try:
            result = target_func(*args, **kwargs)
            self.results[name] = result
            logger.info(f"Thread '{name}' terminé avec succès")
        except Exception as e:
            self.errors[name] = e
            logger.error(f"Thread '{name}' a échoué avec l'erreur: {str(e)}")
    
    def wait_all(self):
        """Attendre que tous les threads terminent"""
        for name, thread in self.threads.items():
            thread.join()
        
        # Vérifier s'il y a des erreurs
        if self.errors:
            error_details = ", ".join([f"{name}: {str(err)}" for name, err in self.errors.items()])
            raise Exception(f"Erreurs dans les threads: {error_details}")
        
        return self.results
    
    def is_running(self, name: str) -> bool:
        """Vérifier si un thread spécifique est en cours d'exécution"""
        thread = self.threads.get(name)
        return thread is not None and thread.is_alive()
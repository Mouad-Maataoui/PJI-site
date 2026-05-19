import json
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

class JsonFormatter(logging.Formatter):
    """Formateur de logs au format JSON"""
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record, ensure_ascii=False)

def configure_logging():
    """Configure le système de logging avec JSON et rotation de fichiers"""
    # Créer le répertoire de logs
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Formatter JSON pour fichiers
    json_formatter = JsonFormatter()
    
    # Formatter texte pour console
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    # Handler pour logs vers fichiers JSON
    file_handler = RotatingFileHandler(
        filename="logs/app.log",
        maxBytes=10485760,
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(logging.INFO)
    
    # Handler pour console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Configuration du logger racine
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

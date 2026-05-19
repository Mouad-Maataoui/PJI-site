# app/db/init_db.py
# Import all models for Alembic to detect
from app.models.user import User
from app.models.image_task import ImageTask
from app.models.transaction import Transaction

def init_db():
    """Initialize the database models"""
    # This function will be used later for database initialization
    pass
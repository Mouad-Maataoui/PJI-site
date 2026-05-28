from fastapi import APIRouter
from app.api.routes import auth, images, points, ai, monitoring, websockets, deepfake

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(images.router, prefix="/images", tags=["images"])
api_router.include_router(points.router, prefix="/points", tags=["points"])
api_router.include_router(websockets.router, prefix="/ws", tags=["websockets"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(deepfake.router,prefix="/deepfake",tags=["Deepfake Detection"])
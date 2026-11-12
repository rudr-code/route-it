from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from api import __version__
from api.database import get_db
from api.routes.benchmark import router as benchmark_router
from api.routes.delivery import router as delivery_router
from api.routes.events import router as events_router
from api.routes.health import router as health_router
from api.routes.problems import router as problems_router
from api.routes.ws import router as ws_router
from contextlib import asynccontextmanager
import asyncio, logging, os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("route_it_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    get_db()
    logger.info(f"[API] Route.it Service v{__version__} initialized.")
    yield
    logger.info("[API] Route.it Service shutting down.")

def create_app() -> FastAPI:
    app = FastAPI(title="Route.it API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers with both direct and /api prefixes
    api_routers = [
        health_router,
        problems_router,
        events_router,
        ws_router,
        delivery_router,
        benchmark_router,
    ]
    for r in api_routers:
        app.include_router(r)
        app.include_router(r, prefix="/api")

    # Static file serving for deployed frontend SPA (dashboard/dist)
    dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard", "dist"))
    if os.path.exists(dist_dir):
        assets_dir = os.path.join(dist_dir, "assets")
        if os.path.exists(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        async def serve_root():
            return FileResponse(os.path.join(dist_dir, "index.html"))

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = os.path.join(dist_dir, full_path)
            if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(dist_dir, "index.html"))

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port)

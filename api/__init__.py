"""Route.it API & WebSocket Service Package.

Exposes RESTful endpoints for routing tasks and real-time WebSockets
for live solver telemetry and dynamic event dispatch.
"""

__version__ = "0.1.0"

from api.main import app, create_app
from api.store import InMemoryProblemStore, ProblemStore, get_store, set_store
from api.websocket import ConnectionManager, manager

__all__ = [
    "__version__",
    "app",
    "create_app",
    "ProblemStore",
    "InMemoryProblemStore",
    "get_store",
    "set_store",
    "ConnectionManager",
    "manager",
]

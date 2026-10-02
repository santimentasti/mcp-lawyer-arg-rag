"""Entrypoint ASGI para Vercel (y cualquier servidor ASGI: `uvicorn app:app`).

El endpoint MCP queda en /mcp; /health devuelve el estado de la base.
"""

import os
import sys
from pathlib import Path

# Detrás del proxy de la plataforma: el Host es el dominio público, no localhost.
os.environ.setdefault("HOST", "0.0.0.0")

sys.path.insert(0, str(Path(__file__).parent / "src"))

from lexar.server import mcp  # noqa: E402

app = mcp.streamable_http_app()

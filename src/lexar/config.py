"""Constantes y configuración por variables de entorno."""

from __future__ import annotations

import os
from pathlib import Path

SERVER_NAME = "lexar_mcp"
CHARACTER_LIMIT = 25_000          # tope de caracteres por respuesta de herramienta
LIMITE_DEFAULT = 10
LIMITE_MAX = 50

# En Vercel (serverless) sólo /tmp es escribible.
DB_PATH = os.environ.get(
    "LEXAR_DB",
    "/tmp/lexar.db" if os.environ.get("VERCEL") else str(Path.cwd() / "data" / "lexar.db"),
)
AUTO_INGEST = os.environ.get("LEXAR_AUTO_INGEST", "1") != "0"

# Por seguridad se escucha sólo en localhost (y FastMCP activa la protección
# contra DNS rebinding). En contenedores/PaaS se define HOST=0.0.0.0.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")

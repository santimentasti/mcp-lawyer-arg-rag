# Imagen del servidor MCP. La base se construye en el build desde clarius/normas.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    LEXAR_DB=/app/data/lexar.db \
    PORT=8000 \
    HOST=0.0.0.0 \
    MCP_TRANSPORT=streamable-http

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
 && mkdir -p /app/data \
 && lexar-ingest --db "$LEXAR_DB"

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')" || exit 1
CMD ["lexar-server"]

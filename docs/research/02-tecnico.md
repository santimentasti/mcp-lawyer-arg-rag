# Investigación técnica (2026-10-02)

> Los docs de OpenAI e instacloud.com estaban bloqueados desde el entorno de investigación. Lo marcado `[no verificado]` sale de fuentes secundarias.

## 0. Spec MCP 2026-07-28 (fuentes secundarias)
- **Se eliminan las sesiones** (`Mcp-Session-Id`, handshake `initialize`): el protocolo es stateless.
- El estado entre llamadas se maneja con **handles explícitos**: una herramienta devuelve un ID y el modelo lo vuelve a pasar como argumento.
- Auth: **CIMD** (Client ID Metadata Documents) es lo recomendado; DCR queda deprecado pero se mantiene por compatibilidad.
- → Diseñamos el server **stateless desde el día 1**.

## 1. ChatGPT
- **Planes [no verificado, fuentes en conflicto]**: Business/Enterprise/Edu con Developer Mode habilitado por un admin. Según guías de terceros, Plus/Pro también tendrían Developer Mode. Hay que probarlo en la cuenta real.
- **Transporte**: Streamable HTTP, URL pública HTTPS terminada en `/mcp`.
- **Herramientas `search(query)` y `fetch(id)`**, ambas obligatorias para deep research / company knowledge:
  - `search(query)` → `{"results":[{"id","title","url"}]}`
  - `fetch(id)` → `{"id","title","text","url","metadata"}`
- **Directorio**: org verificada, dominio propio, anotaciones justificadas en cada herramienta, cuenta demo si hay auth.

## 2. Claude
- Conectores custom por URL en Free (1 conector), Pro, Max, Team y Enterprise.
- Transporte: Streamable HTTP.
- Auth: ninguna / OAuth con CIMD / DCR / client propio / API keys en headers (beta).
- **Directorio**: cada herramienta necesita `title` + `readOnlyHint` o `destructiveHint`; URLs de docs y política de privacidad; ícono; cuenta de prueba.

→ **Un solo endpoint `/mcp`, stateless, read-only, con anotaciones, `search`/`fetch` y sin auth (normativa pública) sirve para ambos.**

## 3. instacloud.com y sandbox
- La opción relevante es **InstaCloud de InsForge** ([instacloud-oss](https://github.com/InsForge/instacloud-oss)): PaaS Apache-2.0 "agent-native" con Postgres 16, storage S3, contenedores Docker con URL HTTPS, forks por rama (copy-on-write) y scale-to-zero.
- **Muy joven (~59 estrellas)**. instacloud.com devolvió 403. **Precio, free tier y soporte de pgvector sin confirmar** (la imagen `postgres:16-alpine` no trae pgvector).
- **Veredicto: técnicamente viable, inmaduro. No usarlo como sandbox principal**; sirve como experimento por su feature de forks por rama.

| Opción | Encaje | Costo aprox. |
|---|---|---|
| Local + MCP Inspector + `cloudflared`/`ngrok` | URL HTTPS para pegar en ChatGPT Developer Mode / Claude | gratis |
| **Railway** | contenedor + Postgres (template con pgvector) | US$1/mes de crédito gratis; Hobby US$5 |
| Render | contenedor + Postgres | free duerme a los 15 min (el cold start puede romper los timeouts) |
| Fly.io | cualquier contenedor | sin free tier nuevo |
| Supabase | Postgres + pgvector + tsvector | free 500 MB, se pausa a los 7 días; Pro US$25 |
| Cloudflare Workers | mejores templates MCP+OAuth | sólo TS |
| Modal | jobs batch de embeddings | US$30/mes de créditos |

**Recomendación**: local + túnel → **Railway (contenedor) + Supabase (pgvector)**.

## 4. RAG para legislación que cambia
- **Datos**: datos abiertos de InfoLEG en datos.gob.ar, con CSV de **"Normas Modificadas" / "Normas Modificatorias"** (aristas de modificación ya listas; la metadata decía actualizado 2023, verificar frescura).
- **Chunking por artículo**, incisos intactos, con breadcrumb (`Ley 26.994 › Libro III › … › Art. 1061`).
- **Búsqueda híbrida**:
  - Citas exactas por regex/SQL primero.
  - `tsvector` en español + `unaccent`.
  - `pgvector` HNSW.
  - Fusión con RRF + reranker opcional.
- **Versionado temporal**: `article_version(valid_from, valid_to, source_norma)` + aristas (`modifica`/`sustituye`/`deroga`/`incorpora`), consultas con `as_of`.
- **Grafos**:
  - **Graphiti**: KG temporal; buen encaje conceptual, pero requiere Neo4j + ingesta con LLM (cara, no determinista).
  - **LightRAG / MS GraphRAG**: sin temporalidad nativa.
  - → **Para el MVP, aristas SQL deterministas > grafo extraído por LLM.**
- **No perder contexto**: el estado vive en el servidor detrás de handles. Recursos `matter://{id}`, prompts, salidas compactas con citas.

## 5. SDKs (versiones a 2026-10-02)
- Python: `fastmcp` 4.0.10; `mcp` oficial 2.2.0.
- TS: `@modelcontextprotocol/server` 2.3.0.
- El repo hoy apunta a `mcp>=1.28,<2` (probado en este entorno). Migrar a `mcp` 2.x / FastMCP 4 es una tarea aparte.

# Sandbox: cómo probarlo en ChatGPT y Claude

## ¿instacloud.com sirve?
**Veredicto: técnicamente sí, pero no como sandbox principal (todavía).**
- El "InstaCloud" relevante es el de **InsForge** ([instacloud-oss](https://github.com/InsForge/instacloud-oss), Apache-2.0): PaaS "agent-native" con Postgres, storage S3 y contenedores Docker con URL HTTPS pública. Clona todo el entorno por rama (copy-on-write) y escala a cero.
- Contras:
  - Muy joven (~59 estrellas).
  - instacloud.com no respondió a la verificación (403).
  - Precio, free tier y soporte de **pgvector** sin confirmar.
- Sería interesante para v2 por los entornos por rama (probar una reforma legal en un fork de la base sin tocar producción).
- Si querés probarlo igual: el `Dockerfile` de este repo corre tal cual en cualquier PaaS de contenedores.

## Opción A — local + túnel (gratis, 5 minutos)
```bash
pip install -e ".[dev]"
lexar-ingest                       # descarga CCyCN + CPCCN desde clarius/normas → data/lexar.db
lexar-server                       # http://localhost:8000/mcp  (health: /health)
npx @modelcontextprotocol/inspector   # probar herramientas → URL http://localhost:8000/mcp
cloudflared tunnel --url http://localhost:8000   # o: ngrok http 8000 → https://xxxx.trycloudflare.com
```
La URL pública + `/mcp` es la que se pega en ChatGPT o Claude.

Para Claude Desktop / Claude Code por stdio:
```json
{"mcpServers": {"lexar": {"command": "lexar-server", "env": {"MCP_TRANSPORT": "stdio", "LEXAR_DB": "/ruta/data/lexar.db"}}}}
```

## Opción V — Vercel (gratis, ya preparado: `app.py` + `requirements.txt`)
1. vercel.com → **Add New → Project → Import** `santimentasti/mcp-lawyer-arg-rag`. Framework: *Other / Python* (lo detecta solo por `app.py`).
2. Mientras el código esté en la rama `claude/mcp-derecho-ar-mvp`: Settings → Git → **Production Branch** = esa rama, o mergear el PR a `main`.
3. Deploy. En el primer request la función arma la base en `/tmp` desde clarius/normas (cold start ~3–5 s).
4. Probar `https://<proyecto>.vercel.app/health` → `{"ok": true, "articulos_vigentes": 3473, ...}`.
5. URL MCP: `https://<proyecto>.vercel.app/mcp`.
6. **Deployment Protection**: la URL de *producción* tiene que ser pública. Los previews quedan detrás de Vercel Auth y un cliente MCP no puede autenticarse ahí.

## Opción B — Railway (contenedor persistente)
1. New Project → Deploy from GitHub repo → este repo (detecta el `Dockerfile`).
2. La base se construye en el build (`lexar-ingest`). Variables: ninguna obligatoria (`PORT` la inyecta Railway).
3. Generate Domain → `https://<app>.up.railway.app/mcp`.
- Costo: plan Hobby ~US$5/mes. Render free también sirve, pero duerme a los 15 min y el arranque en frío puede cortar la llamada del conector.
- Cuando migremos a Postgres + pgvector: **Supabase** (free 500 MB) o el Postgres de Railway.

## Conectar a ChatGPT
1. Settings → Apps & Connectors → Advanced → activar **Developer mode**. La disponibilidad por plan varía: en Business/Enterprise/Edu lo habilita un admin; en Plus/Pro, verificar en la cuenta.
2. Create → nombre "Derecho AR", URL `https://…/mcp`, autenticación **No authentication** (todo es normativa pública).
3. En un chat, elegí el conector y probá:
   - "¿En qué plazo debo contestar una demanda ordinaria en un juzgado civil nacional? Citá el artículo."
   - "Me notificaron electrónicamente el traslado el 14/7/2026. ¿Cuándo vence?"
   - "Verificá las citas de este escrito: …"
- Deep research usa sólo `search`/`fetch`, que ya están implementados.

## Conectar a Claude
- claude.ai → Settings → Connectors → **Add custom connector** → URL `https://…/mcp`, sin autenticación. Disponible en Free (1 conector), Pro, Max, Team y Enterprise.
- Para publicar en el directorio: cada herramienta ya tiene `title` + `readOnlyHint`. Faltan política de privacidad, docs, ícono y contacto.

## Checklist antes de mostrárselo a abogados
- [ ] Revisar con un abogado todo lo marcado `verificar: true` (feriados trasladables 2026, feria de invierno, PBA).
- [ ] Cargar el texto del CPCC PBA (hoy los plazos PBA vienen sólo del modelo).
- [ ] Política de privacidad: no se guardan consultas con datos de clientes (Ley 25.326).
- [ ] Disclaimer visible: herramienta orientativa, no reemplaza el control profesional.

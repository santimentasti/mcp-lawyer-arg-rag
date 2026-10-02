# Arquitectura y enfoques para "no perder contexto"

## Vista general

```
                ┌───────────── ChatGPT (Developer Mode / Apps) ─────────────┐
                │                                                            │
 Abogado ──► LLM ── MCP Streamable HTTP /mcp (stateless, sólo lectura) ──► lexar_mcp
                │                                                            │
                └───────────── Claude (conector custom / Desktop) ───────────┘
                                                                             │
             ┌───────────────────────────────┬───────────────────────────────┤
             ▼                               ▼                               ▼
   Store de normas (SQLite→Postgres)   Modelo procesal (YAML)         Calendario judicial (YAML)
   - artículo = unidad                  - procesos → fases             - feriados, ferias, asuetos
   - versiones con vigencia             - plazos + norma + actor       - reglas de notificación
   - aristas modifica/deroga            - ramas (rebeldía, etc.)       - plazo de gracia
   - FTS5 / BM25 sin tildes             - herencia nacion→pba/caba
             ▲
   Ingesta: clarius/normas (SAIJ, diario) ─ InfoLEG "modificatorias" (v2) ─ normas.gba.gob.ar (PBA, v2)
```

## Ideas clave (versión corta)

1. **El LLM no "sabe" derecho: lo lee.** Todo lo que se cita sale de una herramienta que devuelve texto oficial con id y fuente. El modelo razona y la base de datos da los hechos.
2. **La unidad de conocimiento es el artículo, no el "chunk".** En RAG genérico se corta el texto cada N tokens. En derecho, la unidad natural es el artículo con su ubicación (Libro › Título › Capítulo), su epígrafe y su vigencia. Cortar por artículo hace que cada resultado sea citable.
3. **El tiempo es una dimensión de primera clase.** Una ley nueva no pisa el texto viejo: cierra la versión anterior (`vigente_hasta`) y abre una nueva (`vigente_desde`, `modificado_por`). Así se puede responder "¿qué decía el art. 1198 cuando se firmó el contrato en 2021?". Esto es lo que evita "perder contexto" ante normas nuevas.
4. **El conocimiento procesal es determinista, no probabilístico.** Etapas, plazos y transiciones son un grafo explícito (YAML revisable por un abogado), no algo que el LLM "recuerda". El cómputo de días hábiles es código, no texto generado.
5. **Mostrar el trabajo.** Cada vencimiento incluye los días salteados y por qué, las reglas con su artículo y las advertencias. Cada cita se puede verificar (`lexar_verificar_citas`).
6. **Stateless.** La spec MCP 2026-07 elimina las sesiones. El "contexto" de la conversación lo lleva el LLM; si en v2 se guardan expedientes, se referencian con un handle (`expediente_id`) que el modelo pasa en cada llamada.

## Comparación de enfoques para el corpus que cambia

| Enfoque | Cómo funciona | A favor | En contra | Uso |
|---|---|---|---|---|
| **SQL temporal (implementado)** | tabla de versiones de artículos + aristas `modifica/deroga` + FTS | determinista, auditable, barato, sin LLM en la ingesta | búsqueda semántica débil, sin multi-salto conceptual | **MVP** |
| + **embeddings híbridos** | pgvector (bge-m3) + BM25 + fusión RRF + reranker | encuentra "responsabilidad del dueño del perro" → art. 1759 sin palabras exactas | costo de embeddings, ajuste del modelo | **v1.1** |
| **Graphiti** (KG bi-temporal) | nodos/aristas con validez temporal en Neo4j/FalkorDB | modela "norma A modifica art. X desde fecha F" de forma nativa; consultas multi-salto | infraestructura extra; ingesta con LLM costosa y no determinista → **cargar aristas deterministas desde InfoLEG** | v2 (normas ↔ jurisprudencia ↔ conceptos) |
| **LightRAG / MS GraphRAG** | entidades y resúmenes de comunidades extraídos por LLM | preguntas temáticas globales ("¿cómo trata el CCyCN la buena fe?") | sin temporalidad; mezcla versiones | quizás para doctrina/jurisprudencia |
| **Graphify** | skill de Claude Code que convierte un repo de código en grafo | rápido para explorar código | **sin noción de vigencia ni de versiones; pensado para código** | no apto como núcleo |
| **Contexto largo puro** | meter el código entero en el prompt | simple | caro, sin citas confiables, sin control de versiones, se "pierde en el medio" | no |

### Cómo entra una ley nueva (flujo objetivo)
1. Un job diario (GitHub Action o cron) hace `git pull` de clarius/normas, o consume el Boletín Oficial.
2. Si cambia el texto de un artículo, se compara con la versión vigente: `Store.modificar_articulo(norma, art, nuevo_texto, desde=fecha_vigencia, por=norma_modificatoria)`.
3. Se registra la arista en `relaciones`, que expone `lexar_listar_versiones_articulo` y alimenta un futuro `lexar_listar_cambios_normativos(desde)`.
4. Se re-indexa sólo lo que cambió (FTS y embeddings).
5. Se corre `python -m lexar.verificar_modelo` para detectar plazos procesales afectados por la reforma.

## Herramientas MCP

| Herramienta | Para qué |
|---|---|
| `search`, `fetch` | Contrato de ChatGPT (deep research / conectores). Indexan artículos y fases. |
| `lexar_buscar_normativa` | BM25 sobre artículos vigentes |
| `lexar_obtener_articulo(norma, articulo, fecha?)` | texto oficial, vigente o a una fecha |
| `lexar_listar_versiones_articulo` | versiones y normas modificatorias |
| `lexar_verificar_citas` | anti-alucinación: verifica cada "art. N del X" en un borrador |
| `lexar_listar_procesos`, `lexar_obtener_etapas_proceso` | mapa procesal por jurisdicción |
| `lexar_obtener_siguiente_paso` | fase actual → próximo acto, plazo, ramas, caducidad + texto del artículo |
| `lexar_obtener_reglas_procesales` | cómputo, gracia, notificaciones, caducidad, práctica (Lex100/MEV/Augusta) |
| `lexar_calcular_vencimiento` | días hábiles judiciales con feriados, ferias y perfeccionamiento de la notificación |
| prompt `analizar_expediente` | flujo guiado: etapa → próximo acto → vencimiento → riesgos |

## Verificación del modelo procesal
`python -m lexar.verificar_modelo` contrasta los plazos del YAML con el texto del CPCCN cargado. En la primera corrida detectó 3 errores de la investigación automática: art. 506 → **505**, 546 → **547** y 350 → **150**. Hoy confirma 23/23. **El marcado `verificar: true` sigue siendo obligatorio de revisar por un abogado.**

## Buenas prácticas MCP aplicadas
| Práctica | Cómo está implementada |
|---|---|
| Nombre del servidor `{servicio}_mcp` | `lexar_mcp` |
| Herramientas `{servicio}_{acción}_{recurso}` en snake_case | `lexar_obtener_articulo`, `lexar_calcular_vencimiento`, … Excepción: `search`/`fetch`, que ChatGPT exige con ese nombre exacto |
| Anotaciones | `title`, `readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False` en todas |
| Entradas validadas | modelos Pydantic (`schemas.py`) con `extra='forbid'`, `str_strip_whitespace`, enums y rangos (`ge`/`le`, `pattern`) |
| Formatos de respuesta | `formato`: `markdown` (default, legible) o `json` (estructurado) |
| Salida estructurada | `search`/`fetch` devuelven modelos Pydantic → `outputSchema` + `structuredContent` |
| Paginación | `limite`/`offset` → `total`, `count`, `has_more`, `next_offset` |
| Límite de contexto | `CHARACTER_LIMIT = 25.000` con aviso de truncado y sugerencia |
| Errores | `ToolError` con mensaje accionable ("usá lexar_buscar_normativa…"); los errores internos se loguean a stderr y al cliente sólo le llega el tipo |
| Docstrings | qué hace, cuándo usar / cuándo no, esquema de retorno, errores |
| Async | herramientas `async`; la base se construye la primera vez con `httpx.AsyncClient` y el parseo corre en un hilo |
| Transporte | Streamable HTTP stateless + `json_response` (escala horizontal / serverless); stdio para clientes locales |
| Seguridad | bind por defecto a `127.0.0.1` → FastMCP activa la protección contra DNS rebinding (un `Host` ajeno recibe 421); en PaaS se setea `HOST=0.0.0.0` |
| Recursos y prompts | `lexar://articulo/{norma}/{numero}`, `lexar://proceso/{jurisdiccion}/{proceso}`; prompt `analizar_expediente` |
| Tests | `tests/test_server.py` a nivel protocolo (cliente MCP en memoria): nombres, anotaciones, esquemas, formatos, paginación, errores, recursos |
| Evaluación | `evals/lexar_eval.xml`: 10 preguntas multi-paso con respuestas verificadas |

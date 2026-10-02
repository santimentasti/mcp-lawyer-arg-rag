# Relevamiento open source (GitHub, 2026-10-02)

> Licencias: **sólo reutilizar código MIT / Apache**. NO copiar código de `abenassi/argentina-data-mcp` (PolyForm Noncommercial), `worldwidelaw/legal-sources` (AGPL), el scraper del Boletín de sandbox-ai (GPL) ni de repos sin LICENSE. Sus datos e ideas se pueden estudiar.

## TL;DR priorizado
1. **Corpus**: [clarius/normas](https://github.com/clarius/normas) (MIT, sync diario desde SAIJ). Markdown por ley, anchor `<a id="N">` por artículo, JSON de SAIJ con estado/vigencia. Se complementa con el **CSV/ZIP InfoLEG de datos.jus.gob.ar** (CC BY 2.5 AR, ~420k normas + CSVs "modificadas/modificatorias" = aristas del grafo).
2. **Esqueleto de referencia**: [juanterraf/argentina-legal-data-mcp](https://github.com/juanterraf/argentina-legal-data-mcp) (MIT, FastMCP, remoto, SQLite FTS5, ya funciona en Claude y ChatGPT). Su `DECISIONS.md` documenta los endpoints no documentados de InfoLEG (`buscarNormas.do`, `verVinculos.do`, latin-1, carpetas de anexos de 5.000).
3. **SAIJ**: [joaquinescalante23/saij-mcp](https://github.com/joaquinescalante23/saij-mcp) (MIT, TS: cliente SAIJ, resolución de citas, OCR) y `hernan-cc/saij-mcp` (MIT, Python, PyPI).
4. **CSJN**:
   - [LautaroMoya25/citador-ar-mcp](https://github.com/LautaroMoya25/citador-ar-mcp) (MIT): "Shepard's" de la CSJN, grafo de citas con tratamiento (seguido/distinguido/abandonado).
   - [guillee1010/corpus-csjn](https://github.com/guillee1010/corpus-csjn) (CC-BY 4.0): 5.890 fallos estructurados.
5. **Jurisprudencia SAIJ**: dataset HF `marianbasti/jurisprudencia-Argentina-SAIJ` (Apache-2.0, actualización diaria).
6. **UX anti-alucinación**: [ciri-cuervo/derecho-argentino](https://github.com/ciri-cuervo/derecho-argentino), skill con marcas `[VERIFICAR]`, chequeo semanal de drift y calculadoras deterministas. Licencias mixtas, sólo ideas.

## MCPs legales de otros países (patrones)
- **ComputingVictor/MCP-BOE** (España, MIT, Python): el análogo más cercano en castellano.
- **cyanheads/eur-lex-mcp-server**, **courtlistener-mcp-server**: recorren grafos de relaciones.
- **john-walkoe/courtlistener_citations_mcp**: chequea citas alucinadas → idea para `verificar_citas`.
- **aa0101181514/tw-legal-rag** (327★): MCP remoto gratis, sólo retrieval, con chequeo de citas.
- **anthropics/claude-for-legal** (Apache-2.0): capa de skills que puede montarse sobre nuestro MCP.

## Graphify vs. GraphRAG
| Herramienta | Qué es | Veredicto |
|---|---|---|
| **Graphify** (Graphify-Labs, Apache-2.0) | Skill de Claude Code que convierte un *repo de código* en un KG (tree-sitter + una pasada LLM). Sin embeddings, **sin noción de tiempo ni de versiones**. | **No sirve como núcleo.** A lo sumo para explorar nuestro propio repo. |
| **Graphiti** (Zep, Apache-2.0) | KG **bi-temporal**: aristas con validez desde/hasta | **v2** para versiones y derogaciones, con aristas deterministas desde InfoLEG (no extraídas por LLM) |
| MS GraphRAG / LightRAG | entidades + resúmenes de comunidades | quizás para jurisprudencia temática |
| hadronomy/canary | fragmentos temporales del BOE español | ideas |

## Embeddings en castellano
- **bge-m3**: denso + sparse, 8k de contexto. Default recomendado.
- **littlejohn-ai/bge-m3-spa-law-qa**: bge-m3 fine-tuneado en QA legal en castellano. Probar contra el base.
- **Qwen3-Embedding**: si hay GPU.
- Rerankers: **bge-reranker-v2-m3** / Qwen3-Reranker.

## Camino sugerido
Patrones de juanterraf → corpus de clarius/normas + aristas de modificatorias InfoLEG → cliente SAIJ + citador CSJN → bge-m3 híbrido + reranker → Graphiti → `search`/`fetch` + herramientas ricas (`get_articulo(norma, art, fecha)`, `vigencia`, `modificaciones`, `verificar_citas`).

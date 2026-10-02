# mcp-lawyer-arg-rag

Conector MCP de **derecho argentino — Civil y Comercial** para **ChatGPT** y **Claude**. Le da al LLM:

- **Normativa citable y versionada**: Código Civil y Comercial (2.674 artículos) y CPCCN (799), con texto oficial (SAIJ vía [clarius/normas](https://github.com/clarius/normas)), ubicación, epígrafe y vigencia en el tiempo.
- **Mapa procesal**: 16 tipos de proceso por jurisdicción (Nación / CABA / PBA), cada uno con sus fases, plazo, artículo, quién actúa, escritos típicos, ramas (rebeldía, allanamiento, excepciones…) y caducidad.
- **Cómputo de plazos** en días hábiles judiciales: feriados, ferias, notificación electrónica vs. ministerio legis, plazo de gracia. Muestra cada día salteado y la regla aplicada.
- **Verificador de citas** anti-alucinación: detecta "art. N del X" en un borrador y marca las citas inexistentes, derogadas o del Código Civil viejo.

> Herramienta orientativa: no reemplaza el control profesional. Lo marcado `verificar: true` está pendiente de revisión contra la fuente oficial.

## Uso rápido
```bash
pip install -e ".[dev]"
lexar-ingest            # arma data/lexar.db desde clarius/normas
lexar-server            # MCP en http://localhost:8000/mcp (stateless, Streamable HTTP)
pytest                  # tests
python -m lexar.verificar_modelo   # contrasta los plazos del modelo con el texto del CPCCN
```
Docker: `docker build -t lexar . && docker run -p 8000:8000 lexar`. Vercel: importar el repo (usa `app.py`).
Para conectarlo a ChatGPT / Claude ver **[docs/sandbox.md](docs/sandbox.md)**.

## Estructura
```
src/lexar/
  server.py            # FastMCP: search/fetch (ChatGPT) + herramientas ar_*
  store.py             # SQLite + FTS5; artículos versionados (vigente_desde/hasta) + aristas modifica/deroga
  procesos.py          # motor de etapas (herencia nacion → caba/pba)
  plazos.py            # días hábiles judiciales, notificaciones, plazo de gracia
  citas.py             # extracción y verificación de citas
  verificar_modelo.py  # control del YAML procesal contra el texto legal
  ingest/              # parser de clarius/normas + registro de fuentes
  data/
    calendario.yaml    # feriados, ferias y reglas por jurisdicción
    procesos/{nacion,caba,pba}.yaml   # modelo procesal (editable por abogados)
docs/
  arquitectura.md      # diseño, enfoques RAG/grafo, cómo entra una ley nueva
  sandbox.md           # instacloud vs. Railway, túnel, conectar ChatGPT/Claude
  preguntas-de-diseno.md
  research/            # mercado/PMF, técnica, relevamiento GitHub
```

## Roadmap
1. **Ahora**: revisión jurídica de lo marcado `verificar`; deploy del sandbox; piloto con 10 abogados.
2. **v1.1**: texto del CPCC PBA; Ley 24.522 y Ley 26.589; búsqueda híbrida (bge-m3 + pgvector); job diario de actualización con versionado automático.
3. **v1.2**: calculadora de intereses (tasas BNA / actas); export `.ics` de vencimientos.
4. **v2**: jurisprudencia (SAIJ, CSJN, citador), grafo temporal (Graphiti) normas ↔ fallos; OAuth y, si se decide, expedientes del usuario por handle.

Licencias de datos: normativa pública (SAIJ/InfoLEG); clarius/normas es MIT.

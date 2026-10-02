"""lexar_mcp — servidor MCP de derecho argentino (Civil y Comercial) para ChatGPT y Claude.

Transporte: Streamable HTTP *stateless* en ``/mcp`` (sirve igual para ChatGPT
Developer Mode / Apps y para conectores custom de Claude) o stdio para Claude
Desktop / Claude Code.

Herramientas:
- ``search`` / ``fetch``: contrato requerido por ChatGPT (deep research /
  conectores). Indexan artículos y fases procesales.
- ``ar_*``: herramientas ricas (artículos con versión temporal, etapas
  procesales, próximo paso, cómputo de plazos, verificador de citas).
Todas son de sólo lectura.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from lexar import citas, plazos, procesos
from lexar.ingest.clarius import es_derogado
from lexar.store import Articulo, Store

DB_PATH = os.environ.get("LEXAR_DB", str(Path.cwd() / "data" / "lexar.db"))

INSTRUCCIONES = """\
Conector de derecho argentino, Civil y Comercial (Nación/CABA y Provincia de Buenos Aires).
Reglas de uso:
1. Citá SIEMPRE el artículo con su id (p.ej. 'ccycn:1198') y transcribí el texto devuelto; nunca cites de memoria.
2. Para saber en qué etapa está un expediente y qué sigue: ar_etapas_proceso → ar_siguiente_paso.
3. Para vencimientos usá ar_calcular_vencimiento y mostrá las advertencias y días salteados al usuario.
4. Antes de entregar un escrito, pasá el borrador por ar_verificar_citas.
5. Si una regla dice verificar=true, decilo explícitamente: es información pendiente de control contra la fuente.
Las respuestas son orientativas y no reemplazan el criterio profesional del abogado."""

mcp = FastMCP(
    "lexar_mcp",
    instructions=INSTRUCCIONES,
    stateless_http=True,
    json_response=True,
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
)

RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
Jurisdiccion = Annotated[
    Literal["nacion", "caba", "pba"],
    Field(description="'nacion' (Justicia Nacional/Federal, CPCCN), 'caba' (juicios civiles/comerciales de CABA: tramitan ante la Justicia Nacional) o 'pba' (Provincia de Buenos Aires, CPCC PBA)"),
]

_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        if not Path(DB_PATH).exists():
            raise RuntimeError(f"No existe la base {DB_PATH}. Ejecutá `lexar-ingest` primero.")
        _store = Store(DB_PATH)
    return _store


# ---------------------------------------------------------------- helpers

def _url_articulo(a: Articulo) -> str:
    n = store().get_norma(a.norma_id)
    base = (n.fuente_url if n and n.fuente_url else "").rstrip("/")
    return base or f"lexar://{a.id}"


def _art_dict(a: Articulo, extracto: bool = False) -> dict:
    n = store().get_norma(a.norma_id)
    return {
        "id": a.id,
        "norma": n.nombre if n else a.norma_id,
        "articulo": a.numero,
        "epigrafe": a.epigrafe,
        "ubicacion": a.ubicacion,
        "texto": a.texto[:400] + " …" if extracto and len(a.texto) > 400 else a.texto,
        "estado": "derogado" if es_derogado(a.texto) else ("vigente" if a.vigente_hasta is None else "histórico"),
        "vigente_desde": a.vigente_desde,
        "vigente_hasta": a.vigente_hasta,
        "modificado_por": a.modificado_por,
        "fuente": _url_articulo(a),
    }


_CITA_NORMA = re.compile(r"\b(CPCCN|CCyCN|LCQ)\s+arts?\.\s*(\d+)", re.IGNORECASE)


def _textos_citados(*textos: str | None, max_n: int = 3) -> list[dict]:
    """Adjunta el texto de los artículos citados en una fase (CPCCN/CCyCN)."""
    out, vistos = [], set()
    for t in textos:
        for cod, num in _CITA_NORMA.findall(t or ""):
            nid = cod.lower()
            if (nid, num) in vistos or nid not in ("cpccn", "ccycn"):
                continue
            vistos.add((nid, num))
            a = store().get_articulo(nid, num)
            if a:
                out.append({"id": a.id, "epigrafe": a.epigrafe, "texto": a.texto[:900]})
            if len(out) >= max_n:
                return out
    return out


def _fase_doc_id(jur: str, proceso: str, fase: str) -> str:
    return f"proceso:{jur}:{proceso}:{fase}"


def _buscar_fases(query: str, limit: int) -> list[dict]:
    toks = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 3]
    if not toks:
        return []
    hits = []
    for jur in procesos.JURISDICCIONES:
        if jur == "caba":
            continue  # idéntico a nación en Civil y Comercial
        for pid, p in procesos.modelo(jur)["procesos"].items():
            for f in p.get("fases", []):
                blob = " ".join(str(x) for x in (p.get("nombre"), f.get("nombre"), f.get("notas"), f.get("plazo"))).lower()
                score = sum(blob.count(t[:6]) for t in toks)
                if score:
                    hits.append((score, jur, pid, p, f))
    hits.sort(key=lambda h: -h[0])
    return [
        {"id": _fase_doc_id(j, pid, f["id"]), "title": f"[{j.upper()}] {p.get('nombre')} — {f.get('nombre')}",
         "url": f"lexar://{_fase_doc_id(j, pid, f['id'])}"}
        for _, j, pid, p, f in hits[:limit]
    ]


# ---------------------------------------------------------------- ChatGPT search/fetch

@mcp.tool(annotations={"title": "Buscar (artículos y etapas procesales)", **RO})
def search(query: Annotated[str, Field(description="Consulta en lenguaje natural o cita, p.ej. 'plazo locación vivienda' o 'contestación de demanda'")]) -> dict:
    """Busca en el Código Civil y Comercial, el CPCCN y el modelo de etapas procesales.

    Devuelve {results: [{id, title, url}]}. Usá `fetch` con el id para leer el documento completo.
    """
    s = store()
    results = []
    for h in s.buscar(query, limit=8):
        a = h.articulo
        n = s.get_norma(a.norma_id)
        title = f"{n.nombre if n else a.norma_id} — Art. {a.numero}" + (f" ({a.epigrafe})" if a.epigrafe else "")
        results.append({"id": a.id, "title": title, "url": _url_articulo(a)})
    results.extend(_buscar_fases(query, limit=4))
    return {"results": results}


@mcp.tool(annotations={"title": "Leer documento por id", **RO})
def fetch(id: Annotated[str, Field(description="id devuelto por `search`, p.ej. 'ccycn:1198' o 'proceso:nacion:ordinario:contestacion'")]) -> dict:
    """Devuelve el texto completo de un artículo o de una fase procesal: {id, title, text, url, metadata}."""
    if id.startswith("proceso:"):
        try:
            _, jur, pid, fid = id.split(":", 3)
            d = procesos.siguientes(jur, pid, fid)
        except (ValueError, KeyError) as e:
            raise ValueError(f"id de fase inválido '{id}': {e}") from e
        f = d["fase_actual"]
        lines = [f"# {f.get('nombre')} ({jur.upper()} — {pid})"]
        for k in ("articulos", "actor", "plazo", "escritos", "notas", "ramas", "siguiente"):
            if f.get(k):
                lines.append(f"**{k}**: {f[k]}")
        lines.append(f"**próximos pasos**: {d['proximos_pasos']}")
        for t in _textos_citados(str(f.get("plazo")), f.get("articulos") and f"CPCCN art. {f['articulos']}"):
            lines.append(f"\n> {t['id']} — {t['texto']}")
        return {"id": id, "title": lines[0][2:], "text": "\n".join(lines), "url": f"lexar://{id}", "metadata": {"tipo": "fase_procesal", "verificar": bool(f.get("verificar"))}}
    norma, _, num = id.partition(":")
    a = store().get_articulo(norma, num)
    if a is None:
        raise ValueError(f"No existe '{id}'. Formato: '<norma>:<articulo>' (normas: {', '.join(n.id for n in store().list_normas())}).")
    d = _art_dict(a)
    return {"id": a.id, "title": f"{d['norma']} — Art. {a.numero}", "text": a.texto, "url": d["fuente"],
            "metadata": {k: d[k] for k in ("epigrafe", "ubicacion", "estado", "vigente_desde", "modificado_por")}}


# ---------------------------------------------------------------- normativa

@mcp.tool(annotations={"title": "Buscar normativa", **RO})
def ar_buscar_normativa(
    consulta: Annotated[str, Field(description="Términos de búsqueda (insensible a tildes)", min_length=2)],
    norma: Annotated[str | None, Field(description="Filtrar por norma: 'ccycn' o 'cpccn'")] = None,
    limite: Annotated[int, Field(ge=1, le=25)] = 8,
) -> dict:
    """Búsqueda léxica (BM25) sobre los artículos vigentes. Devuelve extractos con id para citar."""
    hits = store().buscar(consulta, norma_id=norma, limit=limite)
    return {"resultados": [{**_art_dict(h.articulo, extracto=True), "relevancia": round(h.score, 2), "fragmento": h.snippet} for h in hits]}


@mcp.tool(annotations={"title": "Obtener artículo (con versión a una fecha)", **RO})
def ar_obtener_articulo(
    norma: Annotated[str, Field(description="'ccycn' (Código Civil y Comercial) o 'cpccn' (Código Procesal Civil y Comercial de la Nación)")],
    articulo: Annotated[str, Field(description="Número: '1198', '1221 bis', 'art. 1.198'")],
    fecha: Annotated[date | None, Field(description="Opcional: devuelve el texto vigente a esa fecha (YYYY-MM-DD)")] = None,
) -> dict:
    """Texto oficial de un artículo, con ubicación, estado (vigente/derogado) y fuente SAIJ."""
    a = store().get_articulo(norma, articulo, fecha)
    if a is None:
        raise ValueError(f"No se encontró {norma} art. {articulo}" + (f" vigente al {fecha}" if fecha else "") + ". Probá ar_buscar_normativa.")
    return _art_dict(a)


@mcp.tool(annotations={"title": "Historial de versiones de un artículo", **RO})
def ar_historial_articulo(
    norma: Annotated[str, Field(description="'ccycn' o 'cpccn'")],
    articulo: Annotated[str, Field(description="Número de artículo")],
) -> dict:
    """Todas las versiones conocidas del artículo y las normas que lo modificaron."""
    vs = store().historial(norma, articulo)
    if not vs:
        raise ValueError(f"No hay registros de {norma} art. {articulo}.")
    return {"versiones": [_art_dict(v) for v in vs], "relaciones": store().relaciones_de(f"{norma}:{vs[0].numero}")}


@mcp.tool(annotations={"title": "Verificar citas normativas de un escrito", **RO})
def ar_verificar_citas(
    texto: Annotated[str, Field(description="Borrador de escrito o párrafo con citas (p.ej. 'conforme art. 1198 CCyCN y arts. 338 y 356 CPCCN')", min_length=5, max_length=60000)],
) -> dict:
    """Detecta citas a artículos (CCyCN, CPCCN, Código Civil derogado) y verifica que existan y estén vigentes.

    Estados: OK, NO_ENCONTRADO (posible alucinación), DEROGADO, NORMA_DEROGADA.
    """
    return citas.verificar(store(), texto)


# ---------------------------------------------------------------- procesos

@mcp.tool(annotations={"title": "Listar tipos de proceso", **RO})
def ar_listar_procesos(jurisdiccion: Jurisdiccion) -> dict:
    """Tipos de proceso civil y comercial modelados (ordinario, sumarísimo, ejecutivo, sucesiones, concursos, cautelares, etc.)."""
    return {"jurisdiccion": jurisdiccion, "procesos": procesos.listar_procesos(jurisdiccion)}


@mcp.tool(annotations={"title": "Etapas de un proceso", **RO})
def ar_etapas_proceso(
    jurisdiccion: Jurisdiccion,
    proceso: Annotated[str, Field(description="id de ar_listar_procesos, p.ej. 'ordinario', 'juicio_ejecutivo', 'sucesion_ab_intestato'")],
) -> dict:
    """Todas las fases de un proceso en orden, con artículos, plazos, actor, escritos típicos y ramas."""
    try:
        p = procesos.get_proceso(jurisdiccion, proceso)
    except KeyError as e:
        raise ValueError(str(e)) from e
    return {"jurisdiccion": jurisdiccion, "proceso": proceso, **p}


@mcp.tool(annotations={"title": "Próximo paso procesal", **RO})
def ar_siguiente_paso(
    jurisdiccion: Jurisdiccion,
    proceso: Annotated[str, Field(description="id del proceso, p.ej. 'ordinario'")],
    fase_actual: Annotated[str, Field(description="id de la fase en que está el expediente, p.ej. 'contestacion' (ver ar_etapas_proceso)")],
) -> dict:
    """Dada la fase actual de un expediente: qué se hace ahora, plazo y norma, próximos pasos, ramas y caducidad, con el texto de los artículos citados."""
    try:
        d = procesos.siguientes(jurisdiccion, proceso, fase_actual)
    except KeyError as e:
        raise ValueError(str(e)) from e
    f = d["fase_actual"]
    d["texto_normativo"] = _textos_citados(str(f.get("plazo")), f.get("articulos") and f"CPCCN art. {f['articulos']}") if jurisdiccion != "pba" else []
    if jurisdiccion == "pba":
        d["nota"] = "Los textos del CPCC PBA todavía no están cargados: verificar la numeración en normas.gba.gob.ar."
    return d


@mcp.tool(annotations={"title": "Reglas procesales generales", **RO})
def ar_reglas_procesales(jurisdiccion: Jurisdiccion) -> dict:
    """Reglas transversales: cómputo de plazos, plazo de gracia, notificaciones, caducidad, rebeldía, modos anormales de terminación y práctica (sistemas, mesa de entradas, cédulas)."""
    return procesos.reglas_generales(jurisdiccion)


@mcp.tool(annotations={"title": "Calcular vencimiento de plazo", **RO})
def ar_calcular_vencimiento(
    jurisdiccion: Jurisdiccion,
    fecha: Annotated[date, Field(description="Fecha de la notificación (cédula/personal), del día en que quedó disponible la notificación electrónica, o de la resolución si es ministerio legis (YYYY-MM-DD)")],
    dias: Annotated[int, Field(ge=1, le=365, description="Cantidad de días del plazo, p.ej. 15 para contestar demanda en ordinario")],
    modo_notificacion: Annotated[Literal["electronica", "ministerio_legis", "cedula", "personal"], Field(description="Cómo se notificó")] = "electronica",
    tipo: Annotated[Literal["habiles", "corridos"], Field(description="'habiles' (regla procesal) o 'corridos' (p.ej. mediación)")] = "habiles",
) -> dict:
    """Calcula el vencimiento en días hábiles judiciales: excluye fines de semana, feriados y ferias, aplica el perfeccionamiento de la notificación según la jurisdicción e informa el plazo de gracia. Devuelve los días salteados, las reglas aplicadas y advertencias."""
    return plazos.calcular_vencimiento(jurisdiccion, fecha, dias, modo_notificacion, tipo).to_dict()


# ---------------------------------------------------------------- prompts

@mcp.prompt(title="Analizar el estado de un expediente")
def analizar_expediente(jurisdiccion: str, proceso: str, descripcion: str) -> str:
    """Guía al modelo para ubicar la etapa, el próximo acto y su vencimiento."""
    return (
        f"Jurisdicción: {jurisdiccion}. Tipo de proceso: {proceso}.\n"
        f"Situación del expediente: {descripcion}\n\n"
        "1) Con ar_etapas_proceso identificá la fase actual. 2) Con ar_siguiente_paso obtené el próximo acto, el plazo y la norma. "
        "3) Si hay una notificación con fecha, calculá el vencimiento con ar_calcular_vencimiento. "
        "4) Respondé con: etapa actual, próximo acto, quién lo realiza, vencimiento (con días salteados y advertencias), "
        "riesgos (rebeldía, caducidad, negligencia probatoria) y artículos citados con su id."
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    try:
        return JSONResponse({"ok": True, **store().stats()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()

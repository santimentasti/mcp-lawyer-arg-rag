"""lexar_mcp — servidor MCP de derecho argentino (Civil y Comercial) para ChatGPT y Claude.

Transporte: Streamable HTTP *stateless* en ``/mcp`` (ChatGPT Developer Mode /
Apps y conectores custom de Claude) o stdio (Claude Desktop / Claude Code).

Herramientas (todas de sólo lectura):
- ``search`` / ``fetch``: contrato exigido por ChatGPT (deep research). Llevan
  esos nombres exactos por requisito de la plataforma, sin prefijo.
- ``lexar_*``: herramientas ricas con entrada Pydantic, salida markdown o JSON,
  paginación y errores accionables.

Recursos: ``lexar://articulo/{norma}/{numero}`` y ``lexar://proceso/{jurisdiccion}/{proceso}``.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from lexar import citas, config, formato, plazos, procesos
from lexar.ingest.clarius import es_derogado
from lexar.schemas import (
    BuscarNormativaInput,
    CalcularVencimientoInput,
    FetchOutput,
    ListarProcesosInput,
    ListarVersionesInput,
    ObtenerArticuloInput,
    ObtenerEtapasInput,
    ObtenerReglasInput,
    ObtenerSiguientePasoInput,
    ResultadoBusqueda,
    SearchOutput,
    VerificarCitasInput,
)
from lexar.store import Articulo, Store

log = logging.getLogger("lexar")  # FastMCP loguea a stderr: seguro para stdio

INSTRUCCIONES = """\
Conector de derecho argentino, Civil y Comercial (Nación/CABA y Provincia de Buenos Aires).
Reglas de uso:
1. Citá SIEMPRE el artículo con su id (p.ej. 'ccycn:1198') y el texto devuelto por las herramientas; nunca cites de memoria.
2. Para ubicar un expediente: lexar_listar_procesos → lexar_obtener_etapas_proceso → lexar_obtener_siguiente_paso.
3. Para vencimientos usá lexar_calcular_vencimiento y mostrale al usuario los días salteados y las advertencias.
4. Antes de entregar un escrito, pasá el borrador por lexar_verificar_citas.
5. Lo marcado 'verificar' está pendiente de control contra la fuente oficial: decilo explícitamente.
Las respuestas son orientativas y no reemplazan el criterio profesional del abogado."""

mcp = FastMCP(
    config.SERVER_NAME,
    instructions=INSTRUCCIONES,
    stateless_http=True,
    json_response=True,
    host=config.HOST,
    port=config.PORT,
)

T = TypeVar("T")

# ---------------------------------------------------------------- store (carga lazy y async)

_store: Store | None = None
_store_lock = asyncio.Lock()


async def get_store() -> Store:
    """Abre la base; si no existe y LEXAR_AUTO_INGEST != '0', la construye (serverless: /tmp)."""
    global _store
    if _store is not None:
        return _store
    async with _store_lock:
        if _store is None:
            path = Path(config.DB_PATH)
            if not path.exists():
                if not config.AUTO_INGEST:
                    raise ToolError("La base normativa no está inicializada. El administrador debe ejecutar `lexar-ingest`.")
                from lexar.ingest.cli import aingest

                log.info("Construyendo la base normativa en %s", path)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.unlink(missing_ok=True)
                await aingest(Store(tmp))
                tmp.replace(path)
            _store = Store(path)
    return _store


# ---------------------------------------------------------------- errores

class LexarError(Exception):
    """Error esperable con un mensaje accionable para el modelo."""


def manejar_errores(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Traduce errores a mensajes accionables, sin filtrar detalles internos."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            raise
        except (LexarError, KeyError, ValueError) as e:
            raise ToolError(f"Error: {e.args[0] if e.args else e}") from e
        except Exception as e:  # noqa: BLE001
            log.exception("Error inesperado en %s", fn.__name__)
            raise ToolError(f"Error interno inesperado ({type(e).__name__}). Reintentá; si persiste, reportalo.") from e

    return wrapper


def _anotaciones(titulo: str) -> dict:
    # openWorldHint=False: sólo consulta la base local de normas y el modelo procesal.
    return {"title": titulo, "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}


# ---------------------------------------------------------------- helpers

def _art_dict(s: Store, a: Articulo, extracto: bool = False) -> dict:
    n = s.get_norma(a.norma_id)
    texto = a.texto[:400] + " …" if extracto and len(a.texto) > 400 else a.texto
    return {
        "id": a.id,
        "norma": n.nombre if n else a.norma_id,
        "articulo": a.numero,
        "epigrafe": a.epigrafe,
        "ubicacion": a.ubicacion,
        "texto": texto,
        "estado": "derogado" if es_derogado(a.texto) else ("vigente" if a.vigente_hasta is None else "histórico"),
        "vigente_desde": a.vigente_desde,
        "vigente_hasta": a.vigente_hasta,
        "modificado_por": a.modificado_por,
        "fuente": (n.fuente_url if n and n.fuente_url else f"lexar://articulo/{a.norma_id}/{a.numero}"),
    }


def _paginar(items: list, total: int, offset: int) -> dict:
    count = len(items)
    has_more = offset + count < total
    return {"total": total, "count": count, "offset": offset, "has_more": has_more,
            "next_offset": offset + count if has_more else None}


_CITA_NORMA = re.compile(r"\b(CPCCN|CCyCN)\s+arts?\.\s*(\d+)", re.IGNORECASE)


def _textos_citados(s: Store, *textos: str | None, max_n: int = 3) -> list[dict]:
    """Adjunta el texto oficial de los artículos que cita una fase procesal."""
    out, vistos = [], set()
    for t in textos:
        for cod, num in _CITA_NORMA.findall(t or ""):
            key = (cod.lower(), num)
            if key in vistos:
                continue
            vistos.add(key)
            a = s.get_articulo(*key)
            if a:
                out.append({"id": a.id, "epigrafe": a.epigrafe, "texto": a.texto[:900]})
            if len(out) >= max_n:
                return out
    return out


def _fase_textos(s: Store, jurisdiccion: str, f: dict) -> list[dict]:
    if jurisdiccion == "pba":
        return []
    arts = f.get("articulos")
    return _textos_citados(s, str((f.get("plazo") or {}).get("norma", "")), arts and f"CPCCN art. {arts}")


def _buscar_fases(query: str, limit: int) -> list[ResultadoBusqueda]:
    toks = [t[:6] for t in re.findall(r"\w+", query.lower()) if len(t) > 3]
    if not toks:
        return []
    hits = []
    for jur in ("nacion", "pba"):  # caba = nacion en Civil y Comercial
        for pid, p in procesos.modelo(jur)["procesos"].items():
            for f in p.get("fases", []):
                blob = " ".join(str(x) for x in (p.get("nombre"), f.get("nombre"), f.get("notas"), f.get("plazo"))).lower()
                score = sum(blob.count(t) for t in toks)
                if score:
                    hits.append((score, jur, pid, p, f))
    hits.sort(key=lambda h: -h[0])
    return [
        ResultadoBusqueda(id=f"proceso:{j}:{pid}:{f['id']}", title=f"[{j.upper()}] {p.get('nombre')} — {f.get('nombre')}",
                          url=f"lexar://proceso/{j}/{pid}#{f['id']}")
        for _, j, pid, p, f in hits[:limit]
    ]


# ================================================================ ChatGPT: search / fetch

@mcp.tool(name="search", annotations=_anotaciones("Buscar artículos y etapas procesales"))
@manejar_errores
async def search(
    query: str = Field(..., min_length=2, max_length=300, description="Consulta en lenguaje natural o cita. Ej.: 'plazo para contestar la demanda'"),
) -> SearchOutput:
    """Busca en el Código Civil y Comercial, el CPCCN y el modelo de etapas procesales (contrato `search` de ChatGPT).

    Returns:
        {"results": [{"id": str, "title": str, "url": str}]}. Ids: '<norma>:<articulo>' (ej. 'ccycn:1198')
        o 'proceso:<jurisdiccion>:<proceso>:<fase>'. Pasá el id a `fetch` para leer el documento.
    """
    s = await get_store()
    res = []
    for h in s.buscar(query, limit=8):
        a = h.articulo
        n = s.get_norma(a.norma_id)
        title = f"{n.nombre if n else a.norma_id} — Art. {a.numero}" + (f" ({a.epigrafe})" if a.epigrafe else "")
        res.append(ResultadoBusqueda(id=a.id, title=title, url=_art_dict(s, a)["fuente"]))
    return SearchOutput(results=res + _buscar_fases(query, limit=4))


@mcp.tool(name="fetch", annotations=_anotaciones("Leer documento por id"))
@manejar_errores
async def fetch(
    id: str = Field(..., min_length=3, max_length=120, description="id devuelto por `search`, ej. 'ccycn:1198' o 'proceso:nacion:ordinario:contestacion'"),
) -> FetchOutput:
    """Devuelve el texto completo de un artículo o de una fase procesal (contrato `fetch` de ChatGPT).

    Returns:
        {"id", "title", "text", "url", "metadata"}. En fases procesales, `text` incluye el plazo, los
        próximos pasos y el texto de los artículos citados.
    """
    s = await get_store()
    if id.startswith("proceso:"):
        partes = id.split(":")
        if len(partes) != 4:
            raise LexarError(f"id de fase inválido '{id}'. Formato: 'proceso:<jurisdiccion>:<proceso>:<fase>'.")
        _, jur, pid, fid = partes
        d = procesos.siguientes(jur, pid, fid)
        d["texto_normativo"] = _fase_textos(s, jur, d["fase_actual"])
        return FetchOutput(id=id, title=f"[{jur.upper()}] {pid} — {d['fase_actual'].get('nombre')}",
                           text=formato.truncar(formato.md_siguiente(d)), url=f"lexar://proceso/{jur}/{pid}#{fid}",
                           metadata={"tipo": "fase_procesal", "verificar": bool(d["fase_actual"].get("verificar"))})
    norma, _, num = id.partition(":")
    a = s.get_articulo(norma, num) if num else None
    if a is None:
        raise LexarError(f"No existe '{id}'. Formato: '<norma>:<articulo>', normas: {', '.join(n.id for n in s.list_normas())}. Usá `search` para encontrar ids.")
    d = _art_dict(s, a)
    return FetchOutput(id=a.id, title=f"{d['norma']} — Art. {a.numero}", text=a.texto, url=d["fuente"],
                       metadata={k: d[k] for k in ("epigrafe", "ubicacion", "estado", "vigente_desde", "modificado_por")})


# ================================================================ normativa

@mcp.tool(name="lexar_buscar_normativa", annotations=_anotaciones("Buscar normativa"))
@manejar_errores
async def lexar_buscar_normativa(params: BuscarNormativaInput) -> str:
    """Búsqueda léxica (BM25, insensible a tildes) sobre los artículos VIGENTES del CCyCN y el CPCCN.

    Usar cuando: se busca qué artículo regula un tema ("plazo de la locación", "daño punitivo").
    No usar cuando: ya se conoce el número de artículo (usar lexar_obtener_articulo) o se necesita
    la etapa procesal (usar lexar_obtener_etapas_proceso).

    Args:
        params: consulta (str), norma ('ccycn'|'cpccn'|None), limite (1-50, def. 10), offset (>=0), formato.

    Returns:
        markdown con resultados, o JSON:
        {"consulta": str, "total": int, "count": int, "offset": int, "has_more": bool, "next_offset": int|null,
         "resultados": [{"id": "ccycn:1198", "norma": str, "articulo": str, "epigrafe": str|null,
                         "ubicacion": str|null, "texto": str (extracto), "estado": "vigente"|"derogado",
                         "fragmento": str, "relevancia": float, "fuente": url}]}
        Sin resultados: total=0 y un mensaje con sugerencias.
    """
    s = await get_store()
    hits = s.buscar(params.consulta, norma_id=params.norma, limit=params.limite, offset=params.offset)
    total = s.contar(params.consulta, params.norma)
    data = {
        "consulta": params.consulta,
        **_paginar(hits, total, params.offset),
        "resultados": [{**_art_dict(s, h.articulo, extracto=True), "fragmento": h.snippet, "relevancia": round(h.score, 2)} for h in hits],
    }
    return formato.responder(data, params.formato, formato.md_busqueda)


@mcp.tool(name="lexar_obtener_articulo", annotations=_anotaciones("Obtener artículo"))
@manejar_errores
async def lexar_obtener_articulo(params: ObtenerArticuloInput) -> str:
    """Texto oficial de un artículo (vigente, o el vigente a una fecha), con ubicación, estado y fuente SAIJ.

    Usar cuando: se conoce la norma y el número ("art. 1198 CCyCN") o hay que transcribir el texto exacto.
    Con `fecha`, devuelve la versión aplicable a ese momento (p.ej. la fecha de firma de un contrato).

    Returns:
        markdown, o JSON {"id", "norma", "articulo", "epigrafe", "ubicacion", "texto", "estado",
        "vigente_desde", "vigente_hasta", "modificado_por", "fuente"}.
        Error si no existe: sugiere usar lexar_buscar_normativa.
    """
    s = await get_store()
    a = s.get_articulo(params.norma, params.articulo, params.fecha)
    if a is None:
        raise LexarError(
            f"No se encontró {params.norma} art. {params.articulo}"
            + (f" vigente al {params.fecha}" if params.fecha else "")
            + ". Verificá el número o usá lexar_buscar_normativa con palabras clave."
        )
    return formato.responder(_art_dict(s, a), params.formato, formato.md_articulo)


@mcp.tool(name="lexar_listar_versiones_articulo", annotations=_anotaciones("Listar versiones de un artículo"))
@manejar_errores
async def lexar_listar_versiones_articulo(params: ListarVersionesInput) -> str:
    """Todas las versiones conocidas de un artículo, con vigencia y norma modificatoria.

    Usar cuando: se pregunta si un artículo fue reformado, desde cuándo rige el texto actual o qué
    decía antes de una reforma.

    Returns:
        markdown, o JSON {"norma": str, "articulo": str, "versiones": [<artículo>...],
        "relaciones": [{"origen", "tipo", "destino", "fecha", "nota"}]}.
    """
    s = await get_store()
    vs = s.historial(params.norma, params.articulo)
    if not vs:
        raise LexarError(f"No hay registros de {params.norma} art. {params.articulo}. Usá lexar_buscar_normativa.")
    data = {"norma": params.norma, "articulo": vs[0].numero, "versiones": [_art_dict(s, v) for v in vs],
            "relaciones": s.relaciones_de(f"{params.norma}:{vs[0].numero}")}
    return formato.responder(data, params.formato, formato.md_versiones)


@mcp.tool(name="lexar_verificar_citas", annotations=_anotaciones("Verificar citas normativas"))
@manejar_errores
async def lexar_verificar_citas(params: VerificarCitasInput) -> str:
    """Detecta las citas a artículos de un texto y verifica que existan y estén vigentes (anti-alucinación).

    Reconoce "art. 1198 del CCyCN", "arts. 338 y 356 CPCCN", "arts. 59 a 61 del CPCCN",
    "CPCCN, art. 124" y citas al Código Civil / Código de Comercio derogados.
    Usar cuando: antes de entregar o presentar un escrito redactado con IA.
    No verifica jurisprudencia ni que el artículo respalde lo afirmado (leer el extracto).

    Returns:
        markdown (tabla), o JSON {"citas_detectadas": int,
        "resumen": {"OK", "NO_ENCONTRADO", "DEROGADO", "NORMA_DEROGADA"},
        "resultados": [{"cita", "norma", "articulo", "estado", "epigrafe"|"detalle", "extracto"?, "id"?}],
        "limitaciones": str}
    """
    s = await get_store()
    return formato.responder(citas.verificar(s, params.texto), params.formato, formato.md_citas)


# ================================================================ procesos

@mcp.tool(name="lexar_listar_procesos", annotations=_anotaciones("Listar tipos de proceso"))
@manejar_errores
async def lexar_listar_procesos(params: ListarProcesosInput) -> str:
    """Tipos de proceso civil y comercial modelados en una jurisdicción.

    Incluye ordinario, sumarísimo, juicio ejecutivo, ejecución de sentencia, cautelares, beneficio de litigar
    sin gastos, diligencias preliminares, prueba anticipada, desalojo, interdictos, división de condominio,
    sucesiones, concurso preventivo, quiebra y mediación prejudicial (PBA agrega 'sumario').
    Usar como primer paso para obtener el id de un proceso.

    Returns:
        markdown (tabla), o JSON {"jurisdiccion", "total", "count", "offset", "has_more", "next_offset",
        "procesos": [{"id", "nombre", "norma", "ambito", "mediacion", "fases": int}]}
    """
    todos = procesos.listar_procesos(params.jurisdiccion)
    page = todos[params.offset : params.offset + params.limite]
    data = {"jurisdiccion": params.jurisdiccion, **_paginar(page, len(todos), params.offset), "procesos": page}
    return formato.responder(data, params.formato, formato.md_procesos)


@mcp.tool(name="lexar_obtener_etapas_proceso", annotations=_anotaciones("Obtener etapas de un proceso"))
@manejar_errores
async def lexar_obtener_etapas_proceso(params: ObtenerEtapasInput) -> str:
    """Todas las fases de un proceso en orden: artículos, plazo, quién actúa, escritos típicos y ramas
    (rebeldía, allanamiento, excepciones, reconvención…).

    Usar cuando: hay que explicar cómo se tramita un proceso o ubicar en qué fase está un expediente.
    Después, con el id de la fase, usar lexar_obtener_siguiente_paso.

    Returns:
        markdown, o JSON {"jurisdiccion", "proceso", "nombre", "norma", "ambito", "mediacion", "caducidad",
        "fases": [{"id", "nombre", "articulos", "actor", "plazo": {"dias", "tipo", "desde", "norma",
        "verificar"?}, "escritos", "notas", "siguiente", "ramas": [{"si", "ir_a", "norma"}], "verificar"?}]}
    """
    p = procesos.get_proceso(params.jurisdiccion, params.proceso)
    data = {"jurisdiccion": params.jurisdiccion, "proceso": params.proceso, **p}
    return formato.responder(data, params.formato, formato.md_etapas)


@mcp.tool(name="lexar_obtener_siguiente_paso", annotations=_anotaciones("Obtener el próximo paso procesal"))
@manejar_errores
async def lexar_obtener_siguiente_paso(params: ObtenerSiguientePasoInput) -> str:
    """Dada la fase actual de un expediente: qué corresponde hacer, el plazo y su norma, los próximos pasos,
    las ramas posibles, el riesgo de caducidad y el texto oficial de los artículos citados.

    Usar cuando: "contestaron la demanda, ¿qué sigue?", "¿qué plazo tengo para…?".
    Si se conoce la fecha de notificación, completar con lexar_calcular_vencimiento.

    Returns:
        markdown, o JSON {"proceso", "fase_actual": {...fase}, "proximos_pasos": [{"id", "nombre", "plazo"?, "actor"?}],
        "ramas_posibles": [...], "caducidad": str|null, "texto_normativo": [{"id", "epigrafe", "texto"}], "nota"?}
    """
    s = await get_store()
    d = procesos.siguientes(params.jurisdiccion, params.proceso, params.fase_actual)
    d["texto_normativo"] = _fase_textos(s, params.jurisdiccion, d["fase_actual"])
    if params.jurisdiccion == "pba":
        d["nota"] = "El texto del CPCC PBA todavía no está cargado: verificar la numeración en normas.gba.gob.ar."
    return formato.responder(d, params.formato, formato.md_siguiente)


@mcp.tool(name="lexar_obtener_reglas_procesales", annotations=_anotaciones("Obtener reglas procesales generales"))
@manejar_errores
async def lexar_obtener_reglas_procesales(params: ObtenerReglasInput) -> str:
    """Reglas transversales de la jurisdicción: cómputo de plazos, plazo de gracia, notificaciones (ministerio
    legis, cédula, electrónica), caducidad de instancia, rebeldía, modos anormales de terminación y práctica
    (mesa de entradas, Lex100/MEV/Augusta, cédulas, oficios, tasas).

    Returns:
        markdown, o JSON {"jurisdiccion", "codigo", "nota", "reglas": [{"tema", "regla", "norma", "verificar"?}],
        "modos_anormales_de_terminacion": [{"id", "norma", "nota"}], "practica": {str: str}}
    """
    return formato.responder(procesos.reglas_generales(params.jurisdiccion), params.formato, formato.md_reglas)


@mcp.tool(name="lexar_calcular_vencimiento", annotations=_anotaciones("Calcular vencimiento de un plazo procesal"))
@manejar_errores
async def lexar_calcular_vencimiento(params: CalcularVencimientoInput) -> str:
    """Calcula el vencimiento de un plazo en días hábiles judiciales: perfecciona la notificación según la
    jurisdicción (electrónica, ministerio legis martes/viernes, cédula), excluye fines de semana, feriados
    y ferias, e informa el plazo de gracia (CPCCN art. 124: 2 horas; PBA: 4 horas).

    Usar cuando: hay una fecha de notificación y una cantidad de días. Obtener los días con
    lexar_obtener_siguiente_paso si no se conocen.

    Returns:
        markdown, o JSON {"jurisdiccion", "fecha_acto_o_disponibilidad", "modo_notificacion",
        "notificacion_perfeccionada", "plazo", "primer_dia_del_plazo", "vencimiento", "plazo_de_gracia",
        "dias_inhabiles_salteados": [{"fecha", "motivo", "verificar"}], "reglas_aplicadas": [str],
        "advertencias": [str]}. Mostrar SIEMPRE las advertencias al usuario.
    """
    r = plazos.calcular_vencimiento(params.jurisdiccion, params.fecha, params.dias, params.modo_notificacion, params.tipo)
    return formato.responder(r.to_dict(), params.formato, formato.md_vencimiento)


# ================================================================ recursos y prompts

@mcp.resource("lexar://articulo/{norma}/{numero}", name="articulo", mime_type="text/markdown",
              description="Texto oficial vigente de un artículo, ej. lexar://articulo/ccycn/1198")
async def recurso_articulo(norma: str, numero: str) -> str:
    s = await get_store()
    a = s.get_articulo(norma, numero)
    if a is None:
        raise ValueError(f"No existe {norma}:{numero}")
    return formato.md_articulo(_art_dict(s, a))


@mcp.resource("lexar://proceso/{jurisdiccion}/{proceso}", name="proceso", mime_type="text/markdown",
              description="Mapa de etapas de un proceso, ej. lexar://proceso/nacion/ordinario")
async def recurso_proceso(jurisdiccion: str, proceso: str) -> str:
    p = procesos.get_proceso(jurisdiccion, proceso)
    return formato.md_etapas({"jurisdiccion": jurisdiccion, "proceso": proceso, **p})


@mcp.prompt(name="analizar_expediente", title="Analizar el estado de un expediente")
def analizar_expediente(jurisdiccion: str, proceso: str, descripcion: str) -> str:
    """Guía al modelo para ubicar la etapa, el próximo acto y su vencimiento."""
    return (
        f"Jurisdicción: {jurisdiccion}. Tipo de proceso: {proceso}.\n"
        f"Situación del expediente: {descripcion}\n\n"
        "1) Con lexar_obtener_etapas_proceso identificá la fase actual. 2) Con lexar_obtener_siguiente_paso obtené "
        "el próximo acto, el plazo y la norma. 3) Si hay una fecha de notificación, calculá el vencimiento con "
        "lexar_calcular_vencimiento. 4) Respondé con: etapa actual, próximo acto, quién lo realiza, vencimiento "
        "(con días salteados y advertencias), riesgos (rebeldía, caducidad, negligencia probatoria) y artículos "
        "citados con su id."
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    try:
        return JSONResponse({"ok": True, "server": config.SERVER_NAME, **(await get_store()).stats()})
    except Exception as e:  # noqa: BLE001
        log.exception("health")
        return JSONResponse({"ok": False, "error": type(e).__name__}, status_code=503)


def main() -> None:
    mcp.run(transport=config.TRANSPORT)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()

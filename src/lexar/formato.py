"""Renderizado de respuestas: markdown (default, legible) o JSON (estructurado).

Todas las herramientas pasan por :func:`responder`, que aplica el tope
``CHARACTER_LIMIT`` para no inundar el contexto del modelo.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from lexar.config import CHARACTER_LIMIT
from lexar.schemas import FormatoRespuesta


def responder(data: Any, formato: str, a_markdown: Callable[[Any], str]) -> str:
    if formato == FormatoRespuesta.JSON.value:
        out = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    else:
        out = a_markdown(data)
    return truncar(out)


def truncar(texto: str) -> str:
    if len(texto) <= CHARACTER_LIMIT:
        return texto
    return (
        texto[:CHARACTER_LIMIT]
        + f"\n\n… [respuesta truncada a {CHARACTER_LIMIT} caracteres: usá paginación (limite/offset), "
        "un filtro más específico o pedí un recurso puntual]"
    )


def _plazo(p: dict | None) -> str:
    if not p:
        return ""
    s = f"{p.get('dias')} días {p.get('tipo', '')}".strip()
    if p.get("desde"):
        s += f" desde {p['desde']}"
    if p.get("norma"):
        s += f" ({p['norma']})"
    if p.get("verificar"):
        s += " ⚠️ verificar"
    return s


def _paginacion(d: dict) -> str:
    s = f"_Mostrando {d['count']} de {d['total']}"
    if d.get("has_more"):
        s += f" — hay más: usar offset={d['next_offset']}"
    return s + "_"


# ---------------------------------------------------------------- normativa

def md_articulo(a: dict) -> str:
    head = f"## {a['norma']} — Art. {a['articulo']}" + (f": {a['epigrafe']}" if a.get("epigrafe") else "")
    meta = [f"id `{a['id']}`", f"estado: **{a['estado']}**"]
    if a.get("vigente_desde"):
        meta.append(f"vigente desde {a['vigente_desde']}")
    if a.get("vigente_hasta"):
        meta.append(f"hasta {a['vigente_hasta']}")
    if a.get("modificado_por"):
        meta.append(f"texto según {a['modificado_por']}")
    lines = [head, " · ".join(meta)]
    if a.get("ubicacion"):
        lines.append(f"_{a['ubicacion']}_")
    lines += ["", a["texto"], "", f"Fuente: {a['fuente']}"]
    return "\n".join(lines)


def md_busqueda(d: dict) -> str:
    if not d["resultados"]:
        return f"Sin resultados para '{d['consulta']}'. Probá con sinónimos o menos palabras."
    lines = [f"# Resultados para '{d['consulta']}'", _paginacion(d), ""]
    for r in d["resultados"]:
        t = f"### `{r['id']}` — {r['norma']}, art. {r['articulo']}" + (f" ({r['epigrafe']})" if r.get("epigrafe") else "")
        lines += [t, f"_{r.get('ubicacion') or ''}_ · {r['estado']}", f"> {r['fragmento']}", ""]
    return "\n".join(lines)


def md_versiones(d: dict) -> str:
    lines = [f"# Versiones de {d['norma']} art. {d['articulo']}", ""]
    for v in d["versiones"]:
        rango = f"{v.get('vigente_desde') or '¿?'} → {v.get('vigente_hasta') or 'vigente'}"
        lines += [f"## {rango}" + (f" (según {v['modificado_por']})" if v.get("modificado_por") else ""), v["texto"], ""]
    if d["relaciones"]:
        lines.append("## Normas relacionadas")
        lines += [f"- {r['origen']} **{r['tipo']}** {r['destino']} ({r.get('fecha') or 's/f'})" for r in d["relaciones"]]
    else:
        lines.append("_Sin modificaciones registradas en la base (texto consolidado de SAIJ)._")
    return "\n".join(lines)


ICONO = {"OK": "✅", "NO_ENCONTRADO": "❌", "DEROGADO": "⛔", "NORMA_DEROGADA": "⛔"}


def md_citas(d: dict) -> str:
    if not d["citas_detectadas"]:
        return "No se detectaron citas del tipo 'art. N del CCyCN/CPCCN'. " + d["limitaciones"]
    r = d["resumen"]
    lines = [
        "# Verificación de citas",
        f"{d['citas_detectadas']} citas: ✅ {r['OK']} OK · ❌ {r['NO_ENCONTRADO']} inexistentes · "
        f"⛔ {r['DEROGADO'] + r['NORMA_DEROGADA']} derogadas",
        "",
        "| Estado | Cita | Artículo | Detalle |",
        "|---|---|---|---|",
    ]
    for x in d["resultados"]:
        art = f"`{x['id']}`" if x.get("id") else (f"{x.get('norma')}:{x.get('articulo')}" if x.get("norma") else "—")
        det = x.get("epigrafe") or x.get("detalle") or ""
        lines.append(f"| {ICONO[x['estado']]} {x['estado']} | {x['cita']} | {art} | {det[:120].replace('|', '/')} |")
    lines += ["", f"_{d['limitaciones']}_"]
    return "\n".join(lines)


# ---------------------------------------------------------------- procesos

def md_procesos(d: dict) -> str:
    lines = [f"# Procesos — {d['jurisdiccion'].upper()}", _paginacion(d), "", "| id | Proceso | Norma | Mediación | Fases |", "|---|---|---|---|---|"]
    for p in d["procesos"]:
        lines.append(f"| `{p['id']}` | {p['nombre']} | {p.get('norma') or ''} | {p.get('mediacion') or '—'} | {p['fases']} |")
    return "\n".join(lines)


def md_fase(f: dict, n: int | None = None) -> list[str]:
    pre = f"{n}. " if n is not None else ""
    lines = [f"### {pre}{f.get('nombre')} (`{f['id']}`)" + (" ⚠️ verificar" if f.get("verificar") else "")]
    if f.get("ref"):
        lines.append(f"- Ver proceso `{f['ref']}`")
    if f.get("actor"):
        lines.append(f"- **Quién**: {f['actor']}")
    if f.get("plazo"):
        lines.append(f"- **Plazo**: {_plazo(f['plazo'])}")
    if f.get("articulos"):
        lines.append(f"- **Artículos**: {f['articulos']}")
    for e in f.get("escritos", []) or []:
        lines.append(f"- Escrito: {e}")
    if f.get("notas"):
        lines.append(f"- {f['notas']}")
    for r in f.get("ramas", []) or []:
        lines.append(f"- ↳ Si {r['si']} → `{r['ir_a']}`" + (f" ({r['norma']})" if r.get("norma") else ""))
    return lines


def md_etapas(d: dict) -> str:
    lines = [f"# {d.get('nombre', d['proceso'])} — {d['jurisdiccion'].upper()}"]
    for k, lbl in (("norma", "Norma"), ("ambito", "Ámbito"), ("mediacion", "Mediación"), ("caducidad", "Caducidad")):
        if d.get(k):
            lines.append(f"**{lbl}**: {d[k]}")
    lines.append("")
    for i, f in enumerate(d.get("fases", []), 1):
        lines += md_fase(f, i) + [""]
    return "\n".join(lines)


def md_siguiente(d: dict) -> str:
    lines = [f"# {d['proceso']} — fase actual", *md_fase(d["fase_actual"]), "", "## Próximos pasos"]
    for p in d["proximos_pasos"]:
        lines.append(f"- `{p['id']}` {p.get('nombre') or p.get('nota', '')}" + (f" — {_plazo(p.get('plazo'))}" if p.get("plazo") else "") + (f" — {p['actor']}" if p.get("actor") else ""))
    if not d["proximos_pasos"]:
        lines.append("- (fase final del proceso)")
    if d.get("caducidad"):
        lines += ["", f"**Caducidad de instancia**: {d['caducidad']}"]
    for t in d.get("texto_normativo", []):
        lines += ["", f"> **{t['id']}** {t.get('epigrafe') or ''}", "> " + t["texto"].replace("\n", "\n> ")]
    if d.get("nota"):
        lines += ["", f"_{d['nota']}_"]
    return "\n".join(lines)


def md_reglas(d: dict) -> str:
    lines = [f"# Reglas procesales — {d['jurisdiccion'].upper()}", f"**Código**: {d.get('codigo')}"]
    if d.get("nota"):
        lines.append(f"_{d['nota']}_")
    lines.append("")
    for r in d["reglas"]:
        lines.append(f"- **{r['tema']}**: {r['regla']} ({r['norma']})" + (" ⚠️ verificar" if r.get("verificar") else ""))
    if d["modos_anormales_de_terminacion"]:
        lines += ["", "## Modos anormales de terminación"]
        lines += [f"- **{m['id']}** ({m['norma']}): {m['nota']}" for m in d["modos_anormales_de_terminacion"]]
    if d["practica"]:
        lines += ["", "## Práctica"]
        lines += [f"- **{k}**: {v}" for k, v in d["practica"].items()]
    return "\n".join(lines)


def md_vencimiento(d: dict) -> str:
    lines = [
        f"# Vencimiento: **{d['vencimiento']}**",
        f"- Jurisdicción: {d['jurisdiccion']} · plazo: {d['plazo']} · notificación: {d['modo_notificacion']}",
        f"- Notificación perfeccionada: {d['notificacion_perfeccionada']}",
    ]
    if d.get("primer_dia_del_plazo"):
        lines.append(f"- Primer día del plazo: {d['primer_dia_del_plazo']}")
    if d.get("plazo_de_gracia"):
        lines.append(f"- Plazo de gracia: {d['plazo_de_gracia']}")
    if d["dias_inhabiles_salteados"]:
        lines += ["", "## Días hábiles salteados (además de fines de semana)"]
        lines += [f"- {x['fecha']}: {x['motivo']}" + (" ⚠️" if x["verificar"] else "") for x in d["dias_inhabiles_salteados"]]
    lines += ["", "## Reglas aplicadas"] + [f"- {r}" for r in d["reglas_aplicadas"]]
    lines += ["", "## Advertencias"] + [f"- ⚠️ {a}" for a in d["advertencias"]]
    return "\n".join(lines)

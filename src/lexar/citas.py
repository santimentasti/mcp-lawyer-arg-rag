"""Detección y verificación de citas normativas ("art. 1198 CCyCN", "arts. 338 y 356 del CPCCN").

Es la herramienta anti-alucinación: antes de que el abogado copie un escrito
generado por un LLM, cada cita se contrasta con el texto vigente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lexar.ingest.clarius import es_derogado
from lexar.store import Store, normalizar_numero

ALIAS = {
    "ccycn": "ccycn", "cccn": "ccycn", "ccyc": "ccycn", "ccc": "ccycn",
    "codigo civil y comercial": "ccycn", "código civil y comercial": "ccycn",
    "cpccn": "cpccn", "cpcc": "cpccn", "cpcn": "cpccn",
    "codigo procesal civil y comercial de la nacion": "cpccn",
    "código procesal civil y comercial de la nación": "cpccn",
    "codigo procesal civil y comercial": "cpccn", "código procesal civil y comercial": "cpccn",
    "codigo procesal": "cpccn", "código procesal": "cpccn",
}
DEROGADAS = {
    "codigo civil": "El Código Civil de Vélez Sarsfield (Ley 340) fue derogado por la Ley 26.994 (vigencia 1/8/2015).",
    "código civil": "El Código Civil de Vélez Sarsfield (Ley 340) fue derogado por la Ley 26.994 (vigencia 1/8/2015).",
    "codigo de comercio": "El Código de Comercio fue derogado por la Ley 26.994 (vigencia 1/8/2015), salvo normas incorporadas como leyes especiales.",
    "código de comercio": "El Código de Comercio fue derogado por la Ley 26.994 (vigencia 1/8/2015), salvo normas incorporadas como leyes especiales.",
}

_NUM = r"\d{1,2}(?:\.\d{3})|\d{1,4}"
_NUMS = rf"(?:{_NUM})(?:\s*(?:bis|ter|quater))?"
_LISTA = rf"{_NUMS}(?:\s*(?:,|y|e|-|a)\s*{_NUMS})*"
_CODIGOS = "|".join(sorted((re.escape(k) for k in list(ALIAS) + list(DEROGADAS)), key=len, reverse=True))

# "art. 1198 del CCyCN", "arts. 338 y 356 CPCCN", "artículo 6° del Código Civil y Comercial"
PATRON_ART_COD = re.compile(
    rf"\bart(?:[íi]culos?|s?\.)\s*(?P<nums>{_LISTA})\s*[°º]?\s*(?:inc(?:iso)?\.?\s*\w+\s*)?,?\s*(?:del?\s+(?:la\s+)?)?(?P<cod>{_CODIGOS})\b",
    re.IGNORECASE,
)
# "CCyCN art. 1198", "CPCCN, arts. 124 y 156"
PATRON_COD_ART = re.compile(
    rf"\b(?P<cod>{_CODIGOS})\s*,?\s*art(?:[íi]culos?|s?\.)\s*(?P<nums>{_LISTA})",
    re.IGNORECASE,
)


@dataclass
class Cita:
    texto: str
    codigo: str
    numeros: list[str]


def extraer(texto: str) -> list[Cita]:
    """Detecta citas. "art. N del CÓDIGO" tiene prioridad sobre "CÓDIGO art. N":
    en "art. 9 CCyCN, arts. 59 a 61 del CPCCN" los arts. 59-61 son del CPCCN."""
    out: list[Cita] = []
    vistos: set[tuple[str, str]] = set()
    ocupados: list[tuple[int, int]] = []
    for pat in (PATRON_ART_COD, PATRON_COD_ART):
        for m in pat.finditer(texto):
            span = m.span("nums")
            if any(a < span[1] and span[0] < b for a, b in ocupados):
                continue
            ocupados.append(span)
            cod = m.group("cod").lower()
            nums = _expandir(m.group("nums"))
            key = (ALIAS.get(cod, cod), ",".join(nums))
            if key in vistos:
                continue
            vistos.add(key)
            out.append(Cita(m.group(0), cod, nums))
    return out


def _expandir(lista: str) -> list[str]:
    nums: list[str] = []
    for tok in re.split(r"\s*(?:,|\by\b|\be\b)\s*", lista):
        tok = tok.strip()
        rango = re.match(rf"^({_NUM})\s*(?:-|\ba\b)\s*({_NUM})$", tok)
        if rango:
            a, b = (int(normalizar_numero(x)) for x in rango.groups())
            if 0 < b - a <= 30:
                nums.extend(str(i) for i in range(a, b + 1))
                continue
        if tok:
            nums.append(normalizar_numero(tok))
    return nums


def verificar(store: Store, texto: str) -> dict:
    citas = extraer(texto)
    resultados = []
    for c in citas:
        if c.codigo in DEROGADAS:
            resultados.append({"cita": c.texto, "estado": "NORMA_DEROGADA", "detalle": DEROGADAS[c.codigo]})
            continue
        norma = ALIAS.get(c.codigo)
        for n in c.numeros:
            art = store.get_articulo(norma, n) if norma else None
            if art is None:
                resultados.append({
                    "cita": c.texto, "norma": norma, "articulo": n, "estado": "NO_ENCONTRADO",
                    "detalle": "El artículo no existe en el texto vigente cargado: posible cita errónea o alucinada.",
                })
            elif es_derogado(art.texto):
                resultados.append({
                    "cita": c.texto, "norma": norma, "articulo": n, "estado": "DEROGADO",
                    "detalle": art.texto[:200], "id": art.id,
                })
            else:
                resultados.append({
                    "cita": c.texto, "norma": norma, "articulo": n, "estado": "OK",
                    "epigrafe": art.epigrafe, "extracto": art.texto[:280], "id": art.id,
                })
    resumen = {e: sum(1 for r in resultados if r["estado"] == e) for e in ("OK", "NO_ENCONTRADO", "DEROGADO", "NORMA_DEROGADA")}
    return {
        "citas_detectadas": len(resultados),
        "resumen": resumen,
        "resultados": resultados,
        "limitaciones": "Sólo verifica la existencia y vigencia del artículo, no que respalde lo que se afirma: leer el extracto. "
                        "Todavía no verifica jurisprudencia (fallos) ni leyes fuera del corpus cargado.",
    }

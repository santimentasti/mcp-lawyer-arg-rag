"""Parser del formato markdown de github.com/clarius/normas (MIT, sync diario desde SAIJ).

Formato:

    ---
    Fecha: 2014-10-01
    Título: LEY 26.994
    ...
    SAIJ: https://www.saij.gob.ar/LNS0005965
    ---
    # Código Civil y Comercial de la Nación
    ## ANEXO I
    ### TITULO PRELIMINAR
    #### CAPITULO 1  Derecho
    <a id="A 0001"></a>
    ARTICULO 1°.- Fuentes y aplicación. Los casos que ...

- En leyes que aprueban un código como anexo (CCyCN), los artículos del anexo
  usan anchors ``A NNNN`` y los de la ley aprobatoria anchors numéricos.
- En el CPCCN, el epígrafe del artículo es un heading previo (``##### CARACTER. -``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from lexar.store import Articulo, Norma

RAW_URL = "https://raw.githubusercontent.com/clarius/normas/main/{tipo}/{saij_id}.md"

ANCHOR = re.compile(r'^<a id="([^"]+)"></a>\s*$')
HEADING = re.compile(r"^(#{1,9})\s+(.*?)\s*$")
ART_PREFIX = re.compile(
    r"^\s*ART[IÍ]CULO\s+((?:\d{1,3}(?:\.\d{3})+|\d+)(?:\s*(?:bis|ter|quater|quinquies))?)\s*[°º]?\s*[.:]?\s*-?\s*-?\s*",
    re.IGNORECASE,
)
STRUCTURAL = re.compile(
    r"^(PARTE|LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N|PAR[AÁ]GRAFO|ANEXO)\b", re.IGNORECASE
)


@dataclass
class Documento:
    meta: dict
    titulo: str
    articulos: list[Articulo] = field(default_factory=list)


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.index("\n---", 3)
    meta: dict = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[end + 4 :]


def parse(
    text: str,
    norma_id: str,
    solo_anexo: bool = False,
    vigente_desde: str | None = None,
    epigrafe_en_linea: bool = False,
) -> Documento:
    """Convierte el markdown en artículos.

    ``solo_anexo=True`` conserva sólo los artículos con anchor ``A NNNN``
    (el código aprobado), descartando los de la ley aprobatoria.
    ``epigrafe_en_linea=True`` toma el epígrafe de la primera oración
    ("ARTICULO 1°.- Fuentes y aplicación. ..."), como en el CCyCN.
    """
    meta, body = parse_front_matter(text)
    titulo = ""
    stack: dict[int, str] = {}  # nivel -> heading estructural
    epigrafe_pend: str | None = None
    arts: list[Articulo] = []
    cur_anchor: str | None = None
    buf: list[str] = []
    cur_ubic = ""
    cur_epi: str | None = None

    def flush() -> None:
        nonlocal cur_anchor, buf
        if cur_anchor is None:
            return
        is_annex = cur_anchor.startswith("A ")
        if solo_anexo and not is_annex:
            cur_anchor, buf = None, []
            return
        texto = "\n".join(buf).strip()
        if texto:
            numero, epi, cuerpo = _split_articulo(cur_anchor, texto, epigrafe_en_linea)
            arts.append(
                Articulo(
                    norma_id=norma_id,
                    numero=numero,
                    texto=cuerpo,
                    epigrafe=epi or cur_epi,
                    ubicacion=cur_ubic or None,
                    vigente_desde=vigente_desde,
                )
            )
        cur_anchor, buf = None, []

    for line in body.splitlines():
        m = ANCHOR.match(line)
        if m:
            flush()
            cur_anchor = m.group(1)
            cur_ubic = " > ".join(stack[k] for k in sorted(stack) if k > 1)
            cur_epi = epigrafe_pend
            epigrafe_pend = None
            continue
        h = HEADING.match(line)
        if h:
            flush()
            level, txt = len(h.group(1)), _clean_heading(h.group(2))
            if level == 1:
                titulo = txt
            elif STRUCTURAL.match(txt):
                stack = {k: v for k, v in stack.items() if k < level}
                stack[level] = txt
                epigrafe_pend = None
            else:
                epigrafe_pend = txt.rstrip(" .-").strip() or None
            continue
        if cur_anchor is not None:
            buf.append(line)
    flush()
    return Documento(meta=meta, titulo=titulo, articulos=arts)


def _clean_heading(s: str) -> str:
    return re.sub(r"\s{2,}", " — ", s.strip())


SUFIJOS = {"002": "bis", "003": "ter", "004": "quater", "005": "quinquies"}


def _numero_desde_anchor(anchor: str) -> str:
    """'A 0001' -> '1'; 'A 1221 002' -> '1221bis'; '124' -> '124'."""
    parts = anchor.split()
    if parts and parts[0] == "A":
        parts = parts[1:]
    num = parts[0].lstrip("0") or "0"
    if len(parts) > 1:
        num += SUFIJOS.get(parts[1], parts[1])
    return num


def _split_articulo(anchor: str, texto: str, en_linea: bool) -> tuple[str, str | None, str]:
    """Número (desde el anchor, que es confiable), epígrafe en línea y cuerpo."""
    numero = _numero_desde_anchor(anchor)
    m = ART_PREFIX.match(texto)
    epi = None
    if m and en_linea:
        resto = texto[m.end() :]
        # Epígrafe en línea al estilo CCyCN: "Fuentes y aplicación. Los casos..."
        e = re.match(r"^([A-ZÁÉÍÓÚÑ][^.\n]{2,90})\.\s+(?=\S)", resto)
        if e and not re.search(r"\d", e.group(1)) and len(e.group(1).split()) <= 12:
            epi = e.group(1).strip()
    return numero, epi, texto


DEROGADO = re.compile(r"\(?\s*DEROGAD[OA]\b[^)\n]*\)?", re.IGNORECASE)


def es_derogado(texto: str) -> bool:
    """True si el texto consolidado indica que el artículo fue derogado."""
    cabeza = texto[:200]
    return bool(DEROGADO.search(cabeza))


def fetch(saij_id: str, tipo: str = "ley", timeout: float = 60) -> str:
    url = RAW_URL.format(tipo=tipo, saij_id=saij_id)
    r = httpx.get(url, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text


async def afetch(saij_id: str, tipo: str = "ley", timeout: float = 60) -> str:
    """Versión async de :func:`fetch` (para el servidor)."""
    url = RAW_URL.format(tipo=tipo, saij_id=saij_id)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


def to_norma(doc: Documento, norma_id: str, tipo: str, numero: str | None, nombre: str | None, jurisdiccion: str) -> Norma:
    saij = doc.meta.get("SAIJ")
    return Norma(
        id=norma_id,
        tipo=tipo,
        numero=numero,
        nombre=nombre or doc.titulo,
        jurisdiccion=jurisdiccion,
        fuente_url=saij,
        publicada=doc.meta.get("Fecha"),
    )

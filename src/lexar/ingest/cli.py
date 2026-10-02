"""Ingesta: ``lexar-ingest [--db data/lexar.db] [--local DIR] [norma_id ...]``.

Por defecto descarga desde raw.githubusercontent.com/clarius/normas. Con
``--local`` lee desde un clon local del repo (útil sin red o en CI).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from lexar.ingest import clarius
from lexar.ingest.fuentes import FUENTES, POR_ID, Fuente
from lexar.store import Store


def _fuentes(norma_ids: list[str] | None) -> list[Fuente]:
    return [POR_ID[i] for i in norma_ids] if norma_ids else FUENTES


def _cargar(store: Store, f: Fuente, text: str) -> int:
    doc = clarius.parse(
        text, f.norma_id, solo_anexo=f.solo_anexo, vigente_desde=f.vigente_desde,
        epigrafe_en_linea=f.epigrafe_en_linea,
    )
    store.upsert_norma(clarius.to_norma(doc, f.norma_id, f.tipo, f.numero, f.nombre, f.jurisdiccion))
    return store.add_articulos(doc.articulos)


def ingest(store: Store, norma_ids: list[str] | None = None, local: Path | None = None) -> dict[str, int]:
    out = {}
    for f in _fuentes(norma_ids):
        if local:
            text = (local / f.carpeta / f"{f.saij_id}.md").read_text(encoding="utf-8")
        else:
            text = clarius.fetch(f.saij_id, f.carpeta)
        out[f.norma_id] = _cargar(store, f, text)
    return out


async def aingest(store: Store, norma_ids: list[str] | None = None) -> dict[str, int]:
    """Descarga en paralelo (async) y parsea/carga en un hilo aparte."""
    fuentes = _fuentes(norma_ids)
    textos = await asyncio.gather(*(clarius.afetch(f.saij_id, f.carpeta) for f in fuentes))
    out = {}
    for f, text in zip(fuentes, textos):
        out[f.norma_id] = await asyncio.to_thread(_cargar, store, f, text)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("normas", nargs="*", help=f"ids a ingerir (default: todas): {', '.join(POR_ID)}")
    ap.add_argument("--db", default="data/lexar.db")
    ap.add_argument("--local", type=Path, help="clon local de clarius/normas")
    a = ap.parse_args()
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    store = Store(a.db)
    res = ingest(store, a.normas or None, a.local)
    for k, v in res.items():
        print(f"{k}: {v} artículos")
    print(store.stats(), file=sys.stderr)


if __name__ == "__main__":
    main()

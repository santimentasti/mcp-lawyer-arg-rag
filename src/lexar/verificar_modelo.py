"""Contrasta los plazos del modelo procesal con el texto del CPCCN cargado.

Para cada fase cuyo plazo cita "CPCCN art. N", busca en el texto del artículo
el número de días (en letras o cifras). Uso: ``python -m lexar.verificar_modelo``.
Salida: CONFIRMADO / NO_ENCONTRADO_EN_TEXTO / SIN_ARTICULO, para priorizar la
revisión humana de los datos marcados ``verificar``.
"""

from __future__ import annotations

import re
import sys

from lexar import config, procesos
from lexar.store import Store

LETRAS = {
    1: "UN", 2: "DOS", 3: "TRES", 4: "CUATRO", 5: "CINCO", 6: "SEIS", 8: "OCHO", 10: "DIEZ",
    15: "QUINCE", 20: "VEINTE", 30: "TREINTA", 40: "CUARENTA", 60: "SESENTA", 90: "NOVENTA",
}
CITA = re.compile(r"^CPCCN art\.\s*(\d+)")


def verificar(jurisdiccion: str = "nacion", store: Store | None = None) -> list[dict]:
    store = store or Store(config.DB_PATH)
    out = []
    for pid, p in procesos.modelo(jurisdiccion)["procesos"].items():
        for f in p.get("fases", []):
            pl = f.get("plazo") or {}
            m = CITA.search(str(pl.get("norma", "")))
            if not m or not pl.get("dias"):
                continue
            art = store.get_articulo("cpccn", m.group(1))
            dias = pl["dias"]
            if art is None:
                estado = "SIN_ARTICULO"
            else:
                t = art.texto.upper()
                pal = LETRAS.get(dias)
                ordinal = {5: "QUINTO", 3: "TERCERO", 10: "D[EÉ]CIMO"}.get(dias)
                ok = (
                    (pal and re.search(rf"\b{pal}\b", t))
                    or re.search(rf"\({dias}\)|\b{dias} D[IÍ]AS", t)
                    or (ordinal and re.search(rf"\b{ordinal} D[IÍ]A", t))
                )
                estado = "CONFIRMADO" if ok else "NO_ENCONTRADO_EN_TEXTO"
            out.append({"proceso": pid, "fase": f["id"], "dias": dias, "norma": pl["norma"],
                        "marcado_verificar": bool(pl.get("verificar") or f.get("verificar")), "estado": estado})
    return out


def main() -> None:
    res = verificar(sys.argv[1] if len(sys.argv) > 1 else "nacion")
    for r in res:
        flag = " (marcado verificar)" if r["marcado_verificar"] else ""
        print(f"{r['estado']:24} {r['proceso']}.{r['fase']}: {r['dias']} días — {r['norma']}{flag}")
    tot = {e: sum(1 for r in res if r["estado"] == e) for e in ("CONFIRMADO", "NO_ENCONTRADO_EN_TEXTO", "SIN_ARTICULO")}
    print(tot)


if __name__ == "__main__":
    main()

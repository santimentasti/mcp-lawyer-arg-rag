"""Modelo de etapas procesales: tipos de proceso, fases, transiciones y plazos.

Los datos viven en ``lexar/data/procesos/<jurisdiccion>.yaml`` para que un
abogado pueda revisarlos y corregirlos sin tocar código. PBA y CABA heredan del
modelo nacional y sólo declaran diferencias (``overrides``).
"""

from __future__ import annotations

import copy
from functools import lru_cache
from importlib import resources

import yaml

JURISDICCIONES = ("nacion", "caba", "pba")


@lru_cache
def _raw(jurisdiccion: str) -> dict:
    path = resources.files("lexar.data").joinpath("procesos").joinpath(f"{jurisdiccion}.yaml")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def modelo(jurisdiccion: str) -> dict:
    if jurisdiccion not in JURISDICCIONES:
        raise ValueError(f"Jurisdicción desconocida '{jurisdiccion}'. Opciones: {', '.join(JURISDICCIONES)}")
    data = _raw(jurisdiccion)
    base_id = data.get("hereda_de")
    if not base_id:
        return data
    base = copy.deepcopy(modelo(base_id))
    for k in ("jurisdiccion", "codigo", "fuente_url", "nota_jurisdiccion"):
        if k in data:
            base[k] = data[k]
    if "reglas_generales" in data:
        base["reglas_generales"] = data["reglas_generales"] + [
            r for r in base["reglas_generales"] if r["tema"] not in {x["tema"] for x in data["reglas_generales"]}
        ]
    for pid, ov in (data.get("overrides") or {}).items():
        proc = base["procesos"].setdefault(pid, {"fases": []})
        for k, v in ov.items():
            if k == "fases":
                idx = {f["id"]: i for i, f in enumerate(proc.get("fases", []))}
                for fase in v:
                    if fase["id"] in idx:
                        proc["fases"][idx[fase["id"]]].update(fase)
                    else:
                        proc["fases"].append(fase)
            else:
                proc[k] = v
    for pid, proc in (data.get("procesos") or {}).items():
        base["procesos"][pid] = proc
    for pid in data.get("excluir", []) or []:
        base["procesos"].pop(pid, None)
    if "practica" in data:
        base["practica"] = data["practica"]
    return base


def listar_procesos(jurisdiccion: str) -> list[dict]:
    m = modelo(jurisdiccion)
    return [
        {"id": pid, "nombre": p.get("nombre", pid), "norma": p.get("norma"), "ambito": p.get("ambito"),
         "mediacion": p.get("mediacion"), "fases": len(p.get("fases", []))}
        for pid, p in m["procesos"].items()
    ]


def get_proceso(jurisdiccion: str, proceso: str) -> dict:
    m = modelo(jurisdiccion)
    if proceso not in m["procesos"]:
        raise KeyError(
            f"Proceso '{proceso}' no existe en {jurisdiccion}. Usá ar_listar_procesos. "
            f"Disponibles: {', '.join(m['procesos'])}"
        )
    return m["procesos"][proceso]


def get_fase(jurisdiccion: str, proceso: str, fase_id: str) -> dict:
    p = get_proceso(jurisdiccion, proceso)
    for f in p.get("fases", []):
        if f["id"] == fase_id:
            return f
    raise KeyError(
        f"Fase '{fase_id}' no existe en {proceso}. Fases: {', '.join(f['id'] for f in p.get('fases', []))}"
    )


def siguientes(jurisdiccion: str, proceso: str, fase_id: str) -> dict:
    """Fase actual + próximos pasos posibles (camino normal y ramas)."""
    p = get_proceso(jurisdiccion, proceso)
    actual = get_fase(jurisdiccion, proceso, fase_id)
    fases = {f["id"]: f for f in p.get("fases", [])}
    ids = [f["id"] for f in p.get("fases", [])]
    nxt_ids = actual.get("siguiente")
    if nxt_ids is None:
        i = ids.index(fase_id)
        nxt_ids = ids[i + 1 : i + 2]
    proximos = []
    for nid in nxt_ids:
        if nid in fases:
            proximos.append(_resumen(fases[nid]))
        else:  # referencia a otro proceso 'proceso.fase'
            proximos.append({"id": nid, "nota": "pasa a otro proceso"})
    return {
        "proceso": proceso,
        "fase_actual": actual,
        "proximos_pasos": proximos,
        "ramas_posibles": actual.get("ramas", []),
        "caducidad": p.get("caducidad"),
    }


def _resumen(f: dict) -> dict:
    out = {"id": f["id"], "nombre": f.get("nombre")}
    if f.get("plazo"):
        out["plazo"] = f["plazo"]
    if f.get("actor"):
        out["actor"] = f["actor"]
    return out


def reglas_generales(jurisdiccion: str) -> dict:
    m = modelo(jurisdiccion)
    return {
        "jurisdiccion": jurisdiccion,
        "codigo": m.get("codigo"),
        "nota": m.get("nota_jurisdiccion"),
        "reglas": m.get("reglas_generales", []),
        "modos_anormales_de_terminacion": m.get("modos_anormales_de_terminacion", []),
        "practica": m.get("practica", {}),
    }

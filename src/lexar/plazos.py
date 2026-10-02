"""Cómputo de plazos procesales en días hábiles judiciales.

Principio de diseño: **mostrar el trabajo**. Cada cálculo devuelve el detalle
de los días salteados y por qué (fin de semana, feriado, feria), la norma que
rige cada regla y advertencias cuando el calendario usado tiene fechas sin
verificar. Un plazo mal calculado es el peor error posible para el usuario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from importlib import resources

import yaml

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
JURISDICCIONES = ("nacion", "caba", "pba")
MODOS_NOTIFICACION = ("electronica", "ministerio_legis", "cedula", "personal")


@lru_cache
def _calendario() -> dict:
    with resources.files("lexar.data").joinpath("calendario.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class DiaInhabil:
    fecha: date
    motivo: str
    verificar: bool = False


@dataclass
class Calendario:
    jurisdiccion: str
    nombre: str
    inhabiles: dict[date, DiaInhabil]
    plazo_gracia: dict
    notificacion: dict
    anios_cubiertos: set[int]

    def motivo_inhabil(self, d: date) -> DiaInhabil | None:
        if d.weekday() >= 5:
            return DiaInhabil(d, DIAS[d.weekday()])
        return self.inhabiles.get(d)

    def es_habil(self, d: date) -> bool:
        return self.motivo_inhabil(d) is None

    def siguiente_habil(self, d: date) -> date:
        d += timedelta(days=1)
        while not self.es_habil(d):
            d += timedelta(days=1)
        return d


def calendario(jurisdiccion: str) -> Calendario:
    if jurisdiccion not in JURISDICCIONES:
        raise ValueError(f"Jurisdicción desconocida '{jurisdiccion}'. Opciones: {', '.join(JURISDICCIONES)}")
    data = _calendario()
    j = data["jurisdicciones"][jurisdiccion]
    if j.get("hereda_de"):
        j = {**data["jurisdicciones"][j["hereda_de"]], **{k: v for k, v in j.items() if k != "hereda_de"}}
    inh: dict[date, DiaInhabil] = {}
    anios: set[int] = set()
    for anio, lista in data["feriados_nacionales"].items():
        anios.add(int(anio))
        for f in lista:
            inh[f["fecha"]] = DiaInhabil(f["fecha"], f["motivo"], bool(f.get("verificar")))
    for feria in j.get("ferias", []):
        d = feria["desde"]
        while d <= feria["hasta"]:
            inh.setdefault(d, DiaInhabil(d, feria["motivo"], bool(feria.get("verificar"))))
            d += timedelta(days=1)
    for x in j.get("inhabiles_extra", []) or []:
        inh[x["fecha"]] = DiaInhabil(x["fecha"], x["motivo"], bool(x.get("verificar")))
    return Calendario(jurisdiccion, j["nombre"], inh, j["plazo_gracia"], j["notificacion"], anios)


@dataclass
class ResultadoPlazo:
    jurisdiccion: str
    fecha_acto: date
    modo_notificacion: str
    fecha_notificacion: date
    dias: int
    tipo: str
    primer_dia: date | None
    vencimiento: date
    plazo_gracia_hasta: str | None
    dias_salteados: list[dict] = field(default_factory=list)
    reglas: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "jurisdiccion": self.jurisdiccion,
            "fecha_acto_o_disponibilidad": self.fecha_acto.isoformat(),
            "modo_notificacion": self.modo_notificacion,
            "notificacion_perfeccionada": _fmt(self.fecha_notificacion),
            "plazo": f"{self.dias} días {self.tipo}",
            "primer_dia_del_plazo": _fmt(self.primer_dia) if self.primer_dia else None,
            "vencimiento": _fmt(self.vencimiento),
            "plazo_de_gracia": self.plazo_gracia_hasta,
            "dias_inhabiles_salteados": self.dias_salteados,
            "reglas_aplicadas": self.reglas,
            "advertencias": self.advertencias,
        }


def _fmt(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.isoformat()}"


def perfeccionamiento(cal: Calendario, fecha: date, modo: str, reglas: list[str]) -> date:
    """Fecha en que la notificación se tiene por cumplida."""
    if modo not in MODOS_NOTIFICACION:
        raise ValueError(f"Modo de notificación inválido '{modo}'. Opciones: {', '.join(MODOS_NOTIFICACION)}")
    if modo in ("cedula", "personal"):
        reglas.append("Notificación por cédula/personal: se tiene por notificado el día de la diligencia.")
        return fecha
    regla = cal.notificacion[modo]
    if regla["regla"] == "disponible":
        reglas.append(f"Notificación {modo}: se perfecciona el día en que queda disponible ({regla['norma']}).")
        return fecha
    # martes o viernes inmediato posterior; si es inhábil, el siguiente hábil
    d = fecha + timedelta(days=1)
    while d.weekday() not in (1, 4):
        d += timedelta(days=1)
    if not cal.es_habil(d):
        d = cal.siguiente_habil(d)
    reglas.append(f"Notificación {modo}: martes o viernes inmediato posterior, o el siguiente hábil ({regla['norma']}).")
    return d


def calcular_vencimiento(
    jurisdiccion: str,
    fecha: date,
    dias: int,
    modo_notificacion: str = "electronica",
    tipo: str = "habiles",
) -> ResultadoPlazo:
    """Calcula el vencimiento de un plazo procesal.

    ``fecha``: día en que se practicó la notificación o quedó disponible la
    cédula electrónica (para ministerio legis: fecha de la resolución).
    ``tipo``: 'habiles' (regla general, CPCCN art. 156) o 'corridos'.
    """
    if dias < 1 or dias > 365:
        raise ValueError("'dias' debe estar entre 1 y 365.")
    cal = calendario(jurisdiccion)
    reglas: list[str] = []
    adv: list[str] = []
    notif = perfeccionamiento(cal, fecha, modo_notificacion, reglas)

    salteados: list[dict] = []
    if tipo == "corridos":
        reglas.append("Plazo en días corridos: se cuentan todos los días (CCyCN art. 6).")
        primer = notif + timedelta(days=1)
        venc = notif + timedelta(days=dias)
        if not cal.es_habil(venc):
            reglas.append("Si un plazo en días corridos vence en día inhábil, el acto procesal puede cumplirse el primer día hábil siguiente (criterio usual: verificar para el caso).")
            adv.append("Vencimiento en día inhábil: confirmar el criterio aplicable al caso concreto.")
    else:
        reglas.append("Plazo en días hábiles judiciales: comienza el día hábil siguiente a la notificación (CPCCN art. 156; arts. 152 y 155).")
        d = notif
        contados = 0
        primer = None
        while contados < dias:
            d += timedelta(days=1)
            m = cal.motivo_inhabil(d)
            if m is not None:
                if d.weekday() < 5:  # no listar cada fin de semana
                    salteados.append({"fecha": d.isoformat(), "motivo": m.motivo, "verificar": m.verificar})
                if m.verificar:
                    adv.append(f"'{m.motivo}' se computó como inhábil pero la fecha NO está verificada: confirmar por acordada/decreto.")
                continue
            contados += 1
            primer = primer or d
        venc = d

    gracia = None
    if tipo != "corridos" or cal.es_habil(venc):
        g = cal.siguiente_habil(venc)
        gracia = f"hasta las primeras {cal.plazo_gracia['horas']} horas del despacho del {_fmt(g)} ({cal.plazo_gracia['norma']})"
        reglas.append(f"Plazo de gracia: {cal.plazo_gracia['horas']} primeras horas del día hábil siguiente ({cal.plazo_gracia['norma']}).")
        if cal.plazo_gracia.get("verificar"):
            adv.append("La regla del plazo de gracia de esta jurisdicción no está verificada.")

    rango = {fecha.year, venc.year}
    if not rango <= cal.anios_cubiertos:
        adv.append(f"El calendario cargado no cubre todo el año {sorted(rango - cal.anios_cubiertos)}: sólo se excluyen fines de semana y ferias cargadas.")
    adv.append("Cálculo orientativo: confirmar feriados, asuetos y ferias por acordada, y el criterio del tribunal. No reemplaza el control profesional.")

    return ResultadoPlazo(
        jurisdiccion=jurisdiccion,
        fecha_acto=fecha,
        modo_notificacion=modo_notificacion,
        fecha_notificacion=notif,
        dias=dias,
        tipo=tipo,
        primer_dia=primer,
        vencimiento=venc,
        plazo_gracia_hasta=gracia,
        dias_salteados=salteados,
        reglas=reglas,
        advertencias=list(dict.fromkeys(adv)),
    )

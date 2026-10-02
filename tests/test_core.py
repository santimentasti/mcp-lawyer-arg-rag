from datetime import date

import pytest

from lexar import citas, plazos, procesos
from lexar.ingest import clarius
from lexar.store import Articulo, Norma, Store

MD = """---
Fecha: 2014-10-01
Título: LEY 26.994
SAIJ: https://www.saij.gob.ar/LNS0005965
---
# Código Civil y Comercial de la Nación

<a id="1"></a>
ARTICULO 1° - Apruébase el Código Civil y Comercial de la Nación.

## ANEXO I

### LIBRO TERCERO  DERECHOS PERSONALES

#### CAPITULO 4  Locación

<a id="A 1198"></a>
ARTICULO 1198.- Plazo de la locación de inmueble. El plazo de las locaciones con cualquier destino será el que las partes hayan establecido.

<a id="A 1221 002"></a>
Artículo 1.221 bis: NOTA DE REDACCION: (DEROGADO POR DNU 70/23).
"""

CPCC_MD = """---
Título: Ley 17.454
---
# CODIGO PROCESAL

## LIBRO PRIMERO

##### CARGO. -

<a id="124"></a>
ARTICULO 124.- El escrito ... dentro de las DOS (2) primeras horas del despacho.
"""


@pytest.fixture
def store() -> Store:
    s = Store()
    doc = clarius.parse(MD, "ccycn", solo_anexo=True, epigrafe_en_linea=True)
    s.upsert_norma(clarius.to_norma(doc, "ccycn", "codigo", "26994", None, "nacion"))
    s.add_articulos(doc.articulos)
    doc2 = clarius.parse(CPCC_MD, "cpccn")
    s.upsert_norma(clarius.to_norma(doc2, "cpccn", "codigo", "17454", None, "nacion"))
    s.add_articulos(doc2.articulos)
    return s


def test_parser_anexo_epigrafe_y_ubicacion(store):
    a = store.get_articulo("ccycn", "1198")
    assert a.epigrafe == "Plazo de la locación de inmueble"
    assert "LIBRO TERCERO" in a.ubicacion and "Locación" in a.ubicacion
    assert store.get_articulo("ccycn", "1") is None  # artículo de la ley aprobatoria descartado
    assert store.get_articulo("ccycn", "1221 bis") is not None
    assert store.get_articulo("cpccn", "124").epigrafe == "CARGO"


def test_versionado_temporal(store):
    store.modificar_articulo("ccycn", "1198", "Texto nuevo.", desde="2023-12-29", por="dnu-70-2023")
    assert store.get_articulo("ccycn", "1198").texto == "Texto nuevo."
    assert "las partes hayan establecido" in store.get_articulo("ccycn", "1198", fecha="2020-01-01").texto
    assert len(store.historial("ccycn", "1198")) == 2
    assert store.cambios_desde("2023-01-01")[0]["origen"] == "dnu-70-2023"
    # el índice de búsqueda sólo ve la versión vigente
    assert [h.articulo.texto for h in store.buscar("establecido")] == []


def test_derogacion(store):
    store.modificar_articulo("ccycn", "1198", None, desde="2030-01-01", por="ley-x")
    assert store.get_articulo("ccycn", "1198") is None
    assert store.get_articulo("ccycn", "1198", fecha="2029-12-31") is not None


def test_busqueda_sin_tildes(store):
    assert store.buscar("locacion")[0].articulo.numero == "1198"


def test_citas(store):
    r = citas.verificar(store, "art. 1198 del CCyCN, art. 9999 CCyCN, art. 1113 del Código Civil, art. 1221 bis CCyCN")
    estados = [x["estado"] for x in r["resultados"]]
    assert estados == ["OK", "NO_ENCONTRADO", "NORMA_DEROGADA", "DEROGADO"]


def test_citas_precedencia_y_rangos():
    cs = citas.extraer("art. 9 CCyCN, arts. 59 a 61 del CPCCN")
    assert [(citas.ALIAS[c.codigo], c.numeros) for c in cs] == [("ccycn", ["9"]), ("cpccn", ["59", "60", "61"])]


def test_plazo_nacion_feria_y_feriado():
    r = plazos.calcular_vencimiento("nacion", date(2026, 7, 14), 15, "electronica")
    assert r.fecha_notificacion == date(2026, 7, 14)  # electrónica: día de disponibilidad
    assert r.primer_dia == date(2026, 7, 15)
    assert r.vencimiento == date(2026, 8, 19)  # feria de invierno + 17/8
    assert "CPCCN art. 124" in r.plazo_gracia_hasta


def test_plazo_pba_martes_viernes():
    # disponible lunes 5/10 → se perfecciona martes 6/10
    r = plazos.calcular_vencimiento("pba", date(2026, 10, 5), 5, "electronica")
    assert r.fecha_notificacion == date(2026, 10, 6)
    assert r.vencimiento == date(2026, 10, 14)  # 12/10 feriado
    assert "4 horas" in r.plazo_gracia_hasta


def test_plazo_ministerio_legis_feriado():
    # resolución jueves 24/12 → viernes 25 es feriado → lunes 28
    r = plazos.calcular_vencimiento("nacion", date(2026, 12, 24), 1, "ministerio_legis")
    assert r.fecha_notificacion == date(2026, 12, 28)


def test_caba_usa_calendario_nacional():
    a = plazos.calcular_vencimiento("caba", date(2026, 10, 5), 5)
    b = plazos.calcular_vencimiento("nacion", date(2026, 10, 5), 5)
    assert a.vencimiento == b.vencimiento


@pytest.mark.parametrize("jur", ["nacion", "caba", "pba"])
def test_modelo_procesal_consistente(jur):
    for p in procesos.listar_procesos(jur):
        proc = procesos.get_proceso(jur, p["id"])
        ids = {f["id"] for f in proc.get("fases", [])}
        for f in proc.get("fases", []):
            for nxt in f.get("siguiente", []) or []:
                assert nxt in ids or "." in nxt, f"{jur}.{p['id']}.{f['id']} → {nxt}"
            if f.get("plazo"):
                assert f["plazo"].get("norma"), f"{jur}.{p['id']}.{f['id']} sin norma"


def test_pba_hereda_y_sobrescribe():
    assert "sumario" in [p["id"] for p in procesos.listar_procesos("pba")]
    assert "sumario" not in [p["id"] for p in procesos.listar_procesos("nacion")]
    f = procesos.get_fase("pba", "ordinario", "contestacion")
    assert "PBA" in f["plazo"]["norma"]
    assert procesos.get_fase("nacion", "ordinario", "contestacion")["plazo"]["norma"] == "CPCCN art. 338"


def test_siguiente_paso_ramas():
    d = procesos.siguientes("nacion", "ordinario", "contestacion")
    assert d["proximos_pasos"][0]["id"] == "audiencia_preliminar"
    assert any("rebeld" in r["ir_a"] for r in d["ramas_posibles"])

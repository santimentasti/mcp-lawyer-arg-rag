"""Registro de normas a ingerir. Agregar una norma = agregar una entrada."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fuente:
    norma_id: str
    nombre: str
    tipo: str
    numero: str | None
    jurisdiccion: str
    saij_id: str           # id del archivo en clarius/normas (= id SAIJ)
    carpeta: str = "ley"
    solo_anexo: bool = False
    vigente_desde: str | None = None
    epigrafe_en_linea: bool = False


FUENTES: list[Fuente] = [
    Fuente("ccycn", "Código Civil y Comercial de la Nación", "codigo", "26994", "nacion",
           "LNS0005965", solo_anexo=True, vigente_desde="2015-08-01", epigrafe_en_linea=True),
    Fuente("cpccn", "Código Procesal Civil y Comercial de la Nación", "codigo", "17454", "nacion",
           "LNS0001159"),
    # Pendientes (completar el id SAIJ correspondiente):
    # Fuente("lcq", "Ley de Concursos y Quiebras", "ley", "24522", "nacion", "LNS000????"),
    # Fuente("ley-26589", "Mediación prejudicial obligatoria", "ley", "26589", "nacion", "LNS000????"),
    # CPCC PBA (Dec.-Ley 7425/68): no está en clarius/normas (sólo nacional) → ingerir
    # desde normas.gba.gob.ar con un parser propio.
]

POR_ID = {f.norma_id: f for f in FUENTES}

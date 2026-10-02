"""Modelos Pydantic de entrada/salida de las herramientas MCP.

Todas las entradas usan ``extra='forbid'`` (un parámetro desconocido es un
error explícito y no se ignora en silencio) y ``str_strip_whitespace``.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from lexar.config import LIMITE_DEFAULT, LIMITE_MAX


class FormatoRespuesta(str, Enum):
    """Formato de salida de las herramientas."""

    MARKDOWN = "markdown"
    JSON = "json"


class Jurisdiccion(str, Enum):
    NACION = "nacion"
    CABA = "caba"
    PBA = "pba"


class ModoNotificacion(str, Enum):
    ELECTRONICA = "electronica"
    MINISTERIO_LEGIS = "ministerio_legis"
    CEDULA = "cedula"
    PERSONAL = "personal"


class TipoPlazo(str, Enum):
    HABILES = "habiles"
    CORRIDOS = "corridos"


class Norma(str, Enum):
    CCYCN = "ccycn"
    CPCCN = "cpccn"


class _Entrada(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", use_enum_values=True)


_FORMATO = Field(
    default=FormatoRespuesta.MARKDOWN,
    description="'markdown' (legible, default) o 'json' (estructurado, para procesar)",
)
_JURISDICCION = Field(
    ...,
    description="'nacion' (Justicia Nacional/Federal, CPCCN), 'caba' (juicios civiles/comerciales de CABA: "
    "tramitan ante la Justicia Nacional, mismo modelo) o 'pba' (Provincia de Buenos Aires, CPCC PBA)",
)


class BuscarNormativaInput(_Entrada):
    consulta: str = Field(..., min_length=2, max_length=300,
                          description="Términos a buscar, insensible a tildes. Ej.: 'plazo locación vivienda', 'caducidad de instancia'")
    norma: Norma | None = Field(default=None, description="Filtrar por norma: 'ccycn' (Código Civil y Comercial) o 'cpccn' (Código Procesal Civil y Comercial de la Nación)")
    limite: int = Field(default=LIMITE_DEFAULT, ge=1, le=LIMITE_MAX, description="Máximo de resultados por página")
    offset: int = Field(default=0, ge=0, le=500, description="Resultados a saltear (paginación; usar next_offset de la respuesta anterior)")
    formato: FormatoRespuesta = _FORMATO


class ObtenerArticuloInput(_Entrada):
    norma: Norma = Field(..., description="'ccycn' o 'cpccn'")
    articulo: str = Field(..., min_length=1, max_length=20, pattern=r"^[\w°º.\s-]+$",
                          description="Número de artículo. Acepta '1198', '1.198', '1221 bis', 'art. 124'")
    fecha: date | None = Field(default=None, description="Opcional (YYYY-MM-DD): devuelve el texto vigente a esa fecha en lugar del actual")
    formato: FormatoRespuesta = _FORMATO


class ListarVersionesInput(_Entrada):
    norma: Norma = Field(..., description="'ccycn' o 'cpccn'")
    articulo: str = Field(..., min_length=1, max_length=20, pattern=r"^[\w°º.\s-]+$", description="Número de artículo, ej. '1198'")
    formato: FormatoRespuesta = _FORMATO


class VerificarCitasInput(_Entrada):
    texto: str = Field(..., min_length=5, max_length=60000,
                       description="Borrador de escrito o párrafo con citas. Ej.: 'conforme art. 1198 CCyCN y arts. 338 y 356 del CPCCN'")
    formato: FormatoRespuesta = _FORMATO


class ListarProcesosInput(_Entrada):
    jurisdiccion: Jurisdiccion = _JURISDICCION
    limite: int = Field(default=LIMITE_MAX, ge=1, le=LIMITE_MAX, description="Máximo de procesos por página")
    offset: int = Field(default=0, ge=0, description="Procesos a saltear (paginación)")
    formato: FormatoRespuesta = _FORMATO


class ObtenerEtapasInput(_Entrada):
    jurisdiccion: Jurisdiccion = _JURISDICCION
    proceso: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-z_]+$",
                         description="id de lexar_listar_procesos, ej. 'ordinario', 'juicio_ejecutivo', 'sucesion_ab_intestato'")
    formato: FormatoRespuesta = _FORMATO


class ObtenerSiguientePasoInput(_Entrada):
    jurisdiccion: Jurisdiccion = _JURISDICCION
    proceso: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-z_]+$", description="id del proceso, ej. 'ordinario'")
    fase_actual: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-z_]+$",
                             description="id de la fase en que está el expediente (ver lexar_obtener_etapas_proceso), ej. 'contestacion'")
    formato: FormatoRespuesta = _FORMATO


class ObtenerReglasInput(_Entrada):
    jurisdiccion: Jurisdiccion = _JURISDICCION
    formato: FormatoRespuesta = _FORMATO


class CalcularVencimientoInput(_Entrada):
    jurisdiccion: Jurisdiccion = _JURISDICCION
    fecha: date = Field(..., description="(YYYY-MM-DD) Día de la diligencia (cédula/personal), día en que la notificación electrónica quedó disponible, o fecha de la resolución si es ministerio legis")
    dias: int = Field(..., ge=1, le=365, description="Cantidad de días del plazo, ej. 15 para contestar demanda en el ordinario nacional")
    modo_notificacion: ModoNotificacion = Field(default=ModoNotificacion.ELECTRONICA, description="'electronica', 'ministerio_legis', 'cedula' o 'personal'")
    tipo: TipoPlazo = Field(default=TipoPlazo.HABILES, description="'habiles' (regla procesal, CPCCN art. 156) o 'corridos' (ej. mediación, Ley 26.589 art. 20)")
    formato: FormatoRespuesta = _FORMATO


# ---------- salidas del contrato search/fetch de ChatGPT ----------

class ResultadoBusqueda(BaseModel):
    id: str = Field(description="id para pasar a `fetch`")
    title: str
    url: str


class SearchOutput(BaseModel):
    results: list[ResultadoBusqueda]


class FetchOutput(BaseModel):
    id: str
    title: str
    text: str
    url: str
    metadata: dict | None = None

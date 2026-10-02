"""Almacén de normas con versionado temporal de artículos.

Modelo:
- ``normas``: una fila por ley/código (p.ej. CCyCN = Ley 26.994).
- ``articulos``: una fila por *versión* de artículo. Cuando una ley nueva
  modifica un artículo, no se pisa el texto: se cierra la versión anterior
  (``vigente_hasta``) y se inserta una nueva con ``modificado_por``.
- ``relaciones``: aristas de un grafo liviano entre normas/artículos
  (modifica, deroga, sustituye, incorpora, remite_a, reglamenta).
- ``articulos_fts``: índice BM25 (FTS5) insensible a tildes, sólo sobre
  versiones vigentes de cada artículo.

SQLite alcanza para el MVP y para el sandbox; la interfaz está pensada para
migrar a Postgres + pgvector sin cambiar las herramientas MCP.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS normas (
    id            TEXT PRIMARY KEY,          -- slug estable: 'ccycn', 'cpccn', 'cpcc-pba', 'ley-24522'
    tipo          TEXT NOT NULL,             -- codigo | ley | decreto | acordada | resolucion
    numero        TEXT,                      -- '26994'
    nombre        TEXT NOT NULL,
    jurisdiccion  TEXT NOT NULL,             -- nacion | pba | caba
    fuente_url    TEXT,
    publicada     TEXT,                      -- ISO date
    vigente_desde TEXT
);

CREATE TABLE IF NOT EXISTS articulos (
    pk             INTEGER PRIMARY KEY AUTOINCREMENT,
    norma_id       TEXT NOT NULL REFERENCES normas(id),
    numero         TEXT NOT NULL,            -- '1', '1bis', '765'
    epigrafe       TEXT,
    texto          TEXT NOT NULL,
    ubicacion      TEXT,                     -- 'Libro Primero > Título I > Capítulo 1'
    vigente_desde  TEXT,                     -- ISO date o NULL (desconocida)
    vigente_hasta  TEXT,                     -- NULL = vigente
    modificado_por TEXT,                     -- norma_id que introdujo esta versión
    UNIQUE (norma_id, numero, vigente_desde)
);
CREATE INDEX IF NOT EXISTS ix_art_norma_num ON articulos(norma_id, numero);

CREATE TABLE IF NOT EXISTS relaciones (
    origen  TEXT NOT NULL,                   -- 'ley-27551' o 'ccycn:1198'
    tipo    TEXT NOT NULL,                   -- modifica | deroga | sustituye | incorpora | remite_a | reglamenta
    destino TEXT NOT NULL,
    fecha   TEXT,
    nota    TEXT,
    PRIMARY KEY (origen, tipo, destino)
);

CREATE VIRTUAL TABLE IF NOT EXISTS articulos_fts USING fts5(
    norma_id UNINDEXED, numero UNINDEXED, epigrafe, texto, ubicacion,
    content='', tokenize='unicode61 remove_diacritics 2'
);
"""


@dataclass(frozen=True)
class Norma:
    id: str
    tipo: str
    numero: str | None
    nombre: str
    jurisdiccion: str
    fuente_url: str | None = None
    publicada: str | None = None
    vigente_desde: str | None = None


@dataclass(frozen=True)
class Articulo:
    norma_id: str
    numero: str
    texto: str
    epigrafe: str | None = None
    ubicacion: str | None = None
    vigente_desde: str | None = None
    vigente_hasta: str | None = None
    modificado_por: str | None = None

    @property
    def id(self) -> str:
        return f"{self.norma_id}:{self.numero}"


@dataclass(frozen=True)
class Hit:
    articulo: Articulo
    score: float
    snippet: str


def normalizar_numero(numero: str | int) -> str:
    """'Art. 1.198 bis' -> '1198bis'."""
    s = str(numero).lower()
    s = re.sub(r"^(art(\.|iculo|ículo)?\s*)", "", s.strip())
    s = s.replace(".", "").replace("°", "").replace("º", "").replace(" ", "")
    return s


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---------- escritura ----------

    def upsert_norma(self, n: Norma) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO normas VALUES (?,?,?,?,?,?,?,?)",
            (n.id, n.tipo, n.numero, n.nombre, n.jurisdiccion, n.fuente_url, n.publicada, n.vigente_desde),
        )
        self.db.commit()

    def add_articulos(self, arts: Iterable[Articulo]) -> int:
        """Carga inicial de un texto ordenado. Reemplaza versiones idénticas."""
        count = 0
        for a in arts:
            self._insert(a)
            count += 1
        self.db.commit()
        return count

    def modificar_articulo(
        self,
        norma_id: str,
        numero: str,
        nuevo_texto: str | None,
        desde: str,
        por: str,
        epigrafe: str | None = None,
    ) -> None:
        """Aplica una modificación/derogación sin perder la versión anterior.

        ``nuevo_texto=None`` significa derogación: se cierra la versión vigente
        y no se crea una nueva.
        """
        numero = normalizar_numero(numero)
        actual = self.get_articulo(norma_id, numero)
        if actual is not None:
            self.db.execute(
                "UPDATE articulos SET vigente_hasta=? WHERE norma_id=? AND numero=? AND vigente_hasta IS NULL",
                (desde, norma_id, numero),
            )
            self._fts_delete(actual)
        tipo = "deroga" if nuevo_texto is None else ("sustituye" if actual else "incorpora")
        if nuevo_texto is not None:
            self._insert(
                Articulo(
                    norma_id=norma_id,
                    numero=numero,
                    texto=nuevo_texto,
                    epigrafe=epigrafe if epigrafe is not None else (actual.epigrafe if actual else None),
                    ubicacion=actual.ubicacion if actual else None,
                    vigente_desde=desde,
                    modificado_por=por,
                )
            )
        self.add_relacion(por, tipo, f"{norma_id}:{numero}", fecha=desde)
        self.db.commit()

    def add_relacion(self, origen: str, tipo: str, destino: str, fecha: str | None = None, nota: str | None = None) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO relaciones VALUES (?,?,?,?,?)", (origen, tipo, destino, fecha, nota)
        )

    def _insert(self, a: Articulo) -> None:
        a = Articulo(**{**a.__dict__, "numero": normalizar_numero(a.numero)})
        cur = self.db.execute(
            """INSERT OR REPLACE INTO articulos
               (norma_id, numero, epigrafe, texto, ubicacion, vigente_desde, vigente_hasta, modificado_por)
               VALUES (?,?,?,?,?,?,?,?)""",
            (a.norma_id, a.numero, a.epigrafe, a.texto, a.ubicacion, a.vigente_desde, a.vigente_hasta, a.modificado_por),
        )
        if a.vigente_hasta is None:
            self.db.execute(
                "INSERT INTO articulos_fts(rowid, norma_id, numero, epigrafe, texto, ubicacion) VALUES (?,?,?,?,?,?)",
                (cur.lastrowid, a.norma_id, a.numero, a.epigrafe or "", a.texto, a.ubicacion or ""),
            )

    def _fts_delete(self, a: Articulo) -> None:
        row = self.db.execute(
            "SELECT pk FROM articulos WHERE norma_id=? AND numero=? AND texto=?", (a.norma_id, a.numero, a.texto)
        ).fetchone()
        if row:
            self.db.execute(
                "INSERT INTO articulos_fts(articulos_fts, rowid, norma_id, numero, epigrafe, texto, ubicacion) "
                "VALUES ('delete',?,?,?,?,?,?)",
                (row["pk"], a.norma_id, a.numero, a.epigrafe or "", a.texto, a.ubicacion or ""),
            )

    # ---------- lectura ----------

    def get_norma(self, norma_id: str) -> Norma | None:
        r = self.db.execute("SELECT * FROM normas WHERE id=?", (norma_id,)).fetchone()
        return Norma(**dict(r)) if r else None

    def list_normas(self) -> list[Norma]:
        return [Norma(**dict(r)) for r in self.db.execute("SELECT * FROM normas ORDER BY id")]

    def get_articulo(self, norma_id: str, numero: str | int, fecha: str | date | None = None) -> Articulo | None:
        """Versión vigente del artículo, o la vigente a ``fecha`` si se indica."""
        numero = normalizar_numero(numero)
        if fecha is None:
            r = self.db.execute(
                "SELECT * FROM articulos WHERE norma_id=? AND numero=? AND vigente_hasta IS NULL",
                (norma_id, numero),
            ).fetchone()
        else:
            f = str(fecha)
            r = self.db.execute(
                """SELECT * FROM articulos WHERE norma_id=? AND numero=?
                   AND (vigente_desde IS NULL OR vigente_desde <= ?)
                   AND (vigente_hasta IS NULL OR vigente_hasta > ?)
                   ORDER BY vigente_desde DESC LIMIT 1""",
                (norma_id, numero, f, f),
            ).fetchone()
        return _row_to_art(r) if r else None

    def historial(self, norma_id: str, numero: str | int) -> list[Articulo]:
        rows = self.db.execute(
            "SELECT * FROM articulos WHERE norma_id=? AND numero=? ORDER BY COALESCE(vigente_desde,'')",
            (norma_id, normalizar_numero(numero)),
        )
        return [_row_to_art(r) for r in rows]

    def relaciones_de(self, ref: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM relaciones WHERE origen=? OR destino=? OR destino LIKE ? ORDER BY fecha",
            (ref, ref, f"{ref}:%"),
        )
        return [dict(r) for r in rows]

    def cambios_desde(self, fecha: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM relaciones WHERE fecha >= ? AND tipo IN ('modifica','deroga','sustituye','incorpora') "
            "ORDER BY fecha DESC",
            (fecha,),
        )
        return [dict(r) for r in rows]

    def buscar(self, query: str, norma_id: str | None = None, limit: int = 10, offset: int = 0) -> list[Hit]:
        """BM25 sobre versiones vigentes, paginado con ``limit``/``offset``."""
        where, args = self._fts_where(query, norma_id)
        if where is None:
            return []
        sql = f"""SELECT a.*, bm25(articulos_fts, 0, 0, 2.0, 1.0, 0.5) AS score
                  FROM articulos_fts JOIN articulos a ON a.pk = articulos_fts.rowid
                  WHERE {where} ORDER BY score LIMIT ? OFFSET ?"""
        hits = []
        for r in self.db.execute(sql, [*args, limit, offset]):
            art = _row_to_art(r)
            # tabla FTS sin contenido (content=''): el fragmento se arma desde el texto guardado
            hits.append(Hit(art, -r["score"], _snippet(art.texto, query)))
        return hits

    def contar(self, query: str, norma_id: str | None = None) -> int:
        where, args = self._fts_where(query, norma_id)
        if where is None:
            return 0
        sql = f"SELECT count(*) FROM articulos_fts JOIN articulos a ON a.pk = articulos_fts.rowid WHERE {where}"
        return self.db.execute(sql, args).fetchone()[0]

    @staticmethod
    def _fts_where(query: str, norma_id: str | None) -> tuple[str | None, list]:
        q = _fts_query(query)
        if not q:
            return None, []
        if norma_id:
            return "articulos_fts MATCH ? AND a.norma_id = ?", [q, norma_id]
        return "articulos_fts MATCH ?", [q]

    def stats(self) -> dict:
        return {
            "normas": self.db.execute("SELECT count(*) FROM normas").fetchone()[0],
            "articulos_vigentes": self.db.execute(
                "SELECT count(*) FROM articulos WHERE vigente_hasta IS NULL"
            ).fetchone()[0],
            "versiones_historicas": self.db.execute(
                "SELECT count(*) FROM articulos WHERE vigente_hasta IS NOT NULL"
            ).fetchone()[0],
        }


def _row_to_art(r: sqlite3.Row) -> Articulo:
    keys = r.keys()
    return Articulo(
        norma_id=r["norma_id"],
        numero=r["numero"],
        texto=r["texto"],
        epigrafe=r["epigrafe"],
        ubicacion=r["ubicacion"],
        vigente_desde=r["vigente_desde"],
        vigente_hasta=r["vigente_hasta"],
        modificado_por=r["modificado_por"] if "modificado_por" in keys else None,
    )


_STOP = {
    "de", "la", "el", "los", "las", "y", "o", "en", "a", "que", "un", "una", "por", "para", "con",
    "del", "al", "se", "su", "sus", "es", "lo", "como", "cual", "cuál", "qué", "art", "articulo", "artículo",
}


def _fts_query(text: str) -> str:
    toks = [t for t in re.findall(r"\w+", text.lower()) if t not in _STOP and len(t) > 1]
    # prefix match tolera plurales/conjugaciones simples ('contrato' ~ 'contratos')
    return " OR ".join(f'"{t}"*' for t in toks[:12])


def _snippet(texto: str, query: str, width: int = 220) -> str:
    low = texto.lower()
    for t in re.findall(r"\w+", query.lower()):
        i = low.find(t[:6])
        if len(t) > 3 and i >= 0:
            start = max(0, i - width // 3)
            return ("… " if start else "") + texto[start : start + width].strip() + " …"
    return texto[:width].strip() + (" …" if len(texto) > width else "")


def iter_articulos(store: Store, norma_id: str) -> Iterator[Articulo]:
    rows = store.db.execute(
        "SELECT * FROM articulos WHERE norma_id=? AND vigente_hasta IS NULL ORDER BY pk", (norma_id,)
    )
    for r in rows:
        yield _row_to_art(r)

"""Tests a nivel protocolo MCP (cliente en memoria) contra una base de fixture."""

import json
import re

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from lexar import server
from tests.test_core import CPCC_MD, MD
from lexar.ingest import clarius
from lexar.store import Store

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def base_fixture(monkeypatch):
    s = Store()
    for md, nid, kw in ((MD, "ccycn", {"solo_anexo": True, "epigrafe_en_linea": True}), (CPCC_MD, "cpccn", {})):
        doc = clarius.parse(md, nid, **kw)
        s.upsert_norma(clarius.to_norma(doc, nid, "codigo", None, None, "nacion"))
        s.add_articulos(doc.articulos)
    monkeypatch.setattr(server, "_store", s)


async def call(session, name, args):
    r = await session.call_tool(name, args)
    return r, (r.content[0].text if r.content else "")


async def test_nombres_anotaciones_y_esquemas():
    async with connect(server.mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
    assert {"search", "fetch"} <= tools.keys()
    for name, t in tools.items():
        assert name in ("search", "fetch") or re.fullmatch(r"lexar_[a-z]+_[a-z_]+", name), name
        a = t.annotations
        assert a.title and a.readOnlyHint is True and a.destructiveHint is False and a.idempotentHint is True
        assert t.description and len(t.description) > 80, f"{name}: docstring pobre"
    # Entradas Pydantic estrictas: extra='forbid'
    p = tools["lexar_calcular_vencimiento"].inputSchema
    defs = next(iter(p["$defs"].values())) if "$defs" in p else p
    assert any(d.get("additionalProperties") is False for d in p.get("$defs", {}).values())
    # Contrato ChatGPT: search(query) / fetch(id) con salida estructurada
    assert list(tools["search"].inputSchema["properties"]) == ["query"]
    assert list(tools["fetch"].inputSchema["properties"]) == ["id"]
    assert "results" in tools["search"].outputSchema["properties"]
    assert {"id", "title", "text", "url"} <= set(tools["fetch"].outputSchema["properties"])


async def test_search_fetch_contrato_chatgpt():
    async with connect(server.mcp._mcp_server) as s:
        r, txt = await call(s, "search", {"query": "locación inmueble"})
        assert not r.isError
        ids = [x["id"] for x in r.structuredContent["results"]]
        assert "ccycn:1198" in ids
        r, _ = await call(s, "fetch", {"id": "ccycn:1198"})
        assert r.structuredContent["metadata"]["epigrafe"] == "Plazo de la locación de inmueble"
        r, _ = await call(s, "fetch", {"id": "proceso:nacion:ordinario:contestacion"})
        assert "Contestación" in r.structuredContent["title"]


async def test_formatos_markdown_y_json():
    async with connect(server.mcp._mcp_server) as s:
        _, md = await call(s, "lexar_obtener_articulo", {"params": {"norma": "ccycn", "articulo": "1.198"}})
        assert md.startswith("## ") and "ccycn:1198" in md
        _, js = await call(s, "lexar_obtener_articulo", {"params": {"norma": "ccycn", "articulo": "1198", "formato": "json"}})
        assert json.loads(js)["epigrafe"] == "Plazo de la locación de inmueble"


async def test_paginacion():
    async with connect(server.mcp._mcp_server) as s:
        _, js = await call(s, "lexar_listar_procesos", {"params": {"jurisdiccion": "nacion", "limite": 5, "formato": "json"}})
        d = json.loads(js)
        assert d["count"] == 5 and d["has_more"] and d["next_offset"] == 5 and d["total"] >= 16
        _, js = await call(s, "lexar_listar_procesos", {"params": {"jurisdiccion": "nacion", "offset": d["total"] - 1, "formato": "json"}})
        assert json.loads(js)["has_more"] is False


async def test_errores_accionables_y_validacion():
    async with connect(server.mcp._mcp_server) as s:
        r, txt = await call(s, "lexar_obtener_articulo", {"params": {"norma": "ccycn", "articulo": "99999"}})
        assert r.isError and "lexar_buscar_normativa" in txt
        r, txt = await call(s, "lexar_obtener_etapas_proceso", {"params": {"jurisdiccion": "nacion", "proceso": "inexistente"}})
        assert r.isError and "lexar_listar_procesos" in txt
        r, txt = await call(s, "lexar_calcular_vencimiento", {"params": {"jurisdiccion": "nacion", "fecha": "2026-10-05", "dias": 5, "extra": 1}})
        assert r.isError  # extra='forbid'
        r, txt = await call(s, "lexar_calcular_vencimiento", {"params": {"jurisdiccion": "marte", "fecha": "2026-10-05", "dias": 5}})
        assert r.isError
        r, txt = await call(s, "fetch", {"id": "proceso:roto"})
        assert r.isError and "Formato" in txt


async def test_vencimiento_y_citas_markdown():
    async with connect(server.mcp._mcp_server) as s:
        _, md = await call(s, "lexar_calcular_vencimiento", {"params": {"jurisdiccion": "nacion", "fecha": "2026-07-14", "dias": 15}})
        assert "2026-08-19" in md and "Advertencias" in md
        _, md = await call(s, "lexar_verificar_citas", {"params": {"texto": "art. 1198 CCyCN y art. 9999 CCyCN"}})
        assert "✅" in md and "❌" in md


async def test_recursos_y_prompt():
    async with connect(server.mcp._mcp_server) as s:
        tpls = {t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates}
        assert {"lexar://articulo/{norma}/{numero}", "lexar://proceso/{jurisdiccion}/{proceso}"} <= tpls
        r = await s.read_resource("lexar://articulo/ccycn/1198")
        assert "Plazo de la locación" in r.contents[0].text
        p = await s.get_prompt("analizar_expediente", {"jurisdiccion": "nacion", "proceso": "ordinario", "descripcion": "x"})
        assert "lexar_obtener_siguiente_paso" in p.messages[0].content.text


async def test_truncado():
    from lexar import formato
    assert "truncada" in formato.truncar("x" * 30_000)

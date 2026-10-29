"""The host loop without calling Claude: a scripted fake model drives real in-process MCP servers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from mcp import Client

from agent_cli.connections import SEPARATOR, connect_all
from agent_cli.loop import run_turn
from figures_db_mcp.backend import FiguresBackend
from figures_db_mcp.config import Settings as FiguresSettings
from figures_db_mcp.models import FigureSummary
from figures_db_mcp.server import INFO as FIGURES_INFO
from figures_db_mcp.server import register as register_figures
from mcp_kit.server import create_server
from mcp_kit.testing import acting_as

JOBS = FigureSummary(slug="steve-jobs", name="Steve Jobs", born=1955, died=2011, known_for="Apple")


class FakeFigures(FiguresBackend):
    def __init__(self) -> None:
        super().__init__(dsn="unused", statement_timeout_ms=1)

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def search_figures(self, query: str, limit: int) -> list[FigureSummary]:
        return [JOBS]


def tool_use(id_: str, name: str, args: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=args)


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


class ScriptedLlm:
    """Plays back responses in order and records what the host sent each time."""

    def __init__(self, *responses: SimpleNamespace) -> None:
        self._responses = list(responses)
        self.seen: list[list[dict[str, Any]]] = []

    async def create(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> Any:
        self.seen.append(list(messages))
        return self._responses.pop(0)


def figures_client() -> Client:
    return Client(
        create_server(FIGURES_INFO, FiguresSettings(), FakeFigures(), register_figures, with_auth=False)
    )


async def test_run_turn_when_model_calls_tools_then_routes_and_answers() -> None:
    name = f"figures-db{SEPARATOR}search_figures"
    llm = ScriptedLlm(
        SimpleNamespace(
            stop_reason="tool_use",
            content=[tool_use("a", name, {"query": "jobs"}), tool_use("b", name, {"query": "jobs"})],
        ),
        SimpleNamespace(stop_reason="end_turn", content=[text("Steve Jobs co-founded Apple.")]),
    )
    with acting_as(["figures:read"]):
        async with connect_all({"figures-db": figures_client()}) as registry:
            assert name in {t["name"] for t in registry.definitions}
            result = await run_turn(llm, registry, [], "Who founded Apple?", max_rounds=5)
    assert result.answer == "Steve Jobs co-founded Apple."
    assert result.tool_calls == [name, name]
    results_message = llm.seen[1][-1]["content"]  # both results, in ONE user message
    assert [r["tool_use_id"] for r in results_message] == ["a", "b"]
    assert all(not r["is_error"] and "steve-jobs" in r["content"] for r in results_message)


async def test_run_turn_when_tool_denied_then_error_result_goes_back_to_model() -> None:
    name = f"figures-db{SEPARATOR}search_figures"
    llm = ScriptedLlm(
        SimpleNamespace(stop_reason="tool_use", content=[tool_use("a", name, {"query": "jobs"})]),
        SimpleNamespace(stop_reason="end_turn", content=[text("I am not allowed to look that up.")]),
    )
    with acting_as(["wiki:read"]):  # no figures:read
        async with connect_all({"figures-db": figures_client()}) as registry:
            await run_turn(llm, registry, [], "Who founded Apple?", max_rounds=5)
    denied = llm.seen[1][-1]["content"][0]
    assert denied["is_error"] and "figures:read" in denied["content"]


async def test_run_turn_when_model_never_stops_then_round_limit() -> None:
    name = f"figures-db{SEPARATOR}search_figures"
    loop_forever = SimpleNamespace(stop_reason="tool_use", content=[tool_use("a", name, {"query": "jobs"})])
    llm = ScriptedLlm(*[loop_forever] * 3)
    with acting_as(["figures:read"]):
        async with connect_all({"figures-db": figures_client()}) as registry:
            result = await run_turn(llm, registry, [], "loop", max_rounds=3)
    assert "Stopped after 3" in result.answer


async def test_run_turn_when_refused_then_no_tools_run() -> None:
    llm = ScriptedLlm(SimpleNamespace(stop_reason="refusal", content=[]))
    async with connect_all({}) as registry:
        result = await run_turn(llm, registry, [], "something unsafe", max_rounds=3)
    assert result.stop_reason == "refusal" and result.tool_calls == []

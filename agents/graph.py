import asyncio
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from agents.analyst import Diagnosis, run_analyst
from agents.rag.query import build_rag_query, build_theory_rag_query, retrieve_doc_chunks
from agents.router import run_router
from agents.strategist import run_strategist
from agents.tutor import run_communicator


class TutorState(TypedDict):
    code: str
    errors: list[str]
    history: list[dict]
    active_tutor_decorations: int
    include_documentation: bool
    diagnosis: dict
    documentation_context: list[str]
    strategist_plan: str
    tutor_response: str
    actions: list[dict]
    intent: str


async def router_node(state: TutorState) -> dict:
    return await run_router(dict(state))


async def analyst_node(state: TutorState) -> dict:
    diagnosis = await run_analyst(state["code"], state["errors"])
    return {"diagnosis": diagnosis}


async def rag_retrieve_node(state: TutorState) -> dict:
    """Recupera trechos: THEORY sempre (query teórica); DEBUG se ``include_documentation``."""
    intent = state.get("intent") or ""
    if intent == "CASUAL":
        return {"documentation_context": []}
    if intent == "THEORY":
        query = build_theory_rag_query(state["history"], state["code"])
        chunks = await asyncio.to_thread(retrieve_doc_chunks, query)
        return {"documentation_context": chunks}
    if intent == "DEBUG":
        if not state.get("include_documentation"):
            return {"documentation_context": []}
        diagnosis = cast(Diagnosis, state["diagnosis"])
        query = build_rag_query(diagnosis, state["errors"], state["history"])
        chunks = await asyncio.to_thread(retrieve_doc_chunks, query)
        return {"documentation_context": chunks}
    return {"documentation_context": []}


async def strategist_node(state: TutorState) -> dict:
    diagnosis = cast(Diagnosis, state["diagnosis"])
    doc_ctx = state.get("documentation_context") or []
    actions, strategist_plan = await run_strategist(
        diagnosis,
        state["history"],
        state["code"],
        state["active_tutor_decorations"],
        documentation_context=doc_ctx,
    )
    return {"actions": actions, "strategist_plan": strategist_plan}


async def tutor_node(state: TutorState) -> dict:
    tutor_response = await run_communicator(
        state["strategist_plan"],
        state["history"],
        intent=state.get("intent") or "DEBUG",
        documentation_context=state.get("documentation_context") or [],
    )
    return {"tutor_response": tutor_response}


def route_after_router(state: TutorState) -> Literal["analyst", "rag_retrieve", "tutor"]:
    intent = state.get("intent") or "DEBUG"
    if intent == "CASUAL":
        return "tutor"
    if intent == "THEORY":
        return "rag_retrieve"
    return "analyst"


def route_after_rag(state: TutorState) -> Literal["strategist", "tutor"]:
    if state.get("intent") == "THEORY":
        return "tutor"
    return "strategist"


def build_graph():
    builder = StateGraph(TutorState)
    builder.add_node("router", router_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("rag_retrieve", rag_retrieve_node)
    builder.add_node("strategist", strategist_node)
    builder.add_node("tutor", tutor_node)
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        route_after_router,
        {
            "analyst": "analyst",
            "rag_retrieve": "rag_retrieve",
            "tutor": "tutor",
        },
    )
    builder.add_edge("analyst", "rag_retrieve")
    builder.add_conditional_edges(
        "rag_retrieve",
        route_after_rag,
        {
            "strategist": "strategist",
            "tutor": "tutor",
        },
    )
    builder.add_edge("strategist", "tutor")
    builder.add_edge("tutor", END)
    return builder.compile()


tutor_graph = build_graph()

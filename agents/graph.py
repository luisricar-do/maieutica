import asyncio
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph

from agents.analyst import Diagnosis, run_analyst
from agents.rag.query import build_rag_query, retrieve_doc_chunks
from agents.tutor import run_tutor


class TutorState(TypedDict):
    code: str
    errors: list[str]
    history: list[dict]
    active_tutor_decorations: int
    include_documentation: bool
    diagnosis: dict
    documentation_context: list[str]
    tutor_response: str
    actions: list[dict]


async def analyst_node(state: TutorState) -> dict:
    diagnosis = await run_analyst(state["code"], state["errors"])
    return {"diagnosis": diagnosis}


async def rag_retrieve_node(state: TutorState) -> dict:
    """Recupera trechos da documentação Portugol quando ``include_documentation`` é verdadeiro."""
    if not state.get("include_documentation"):
        return {"documentation_context": []}
    diagnosis = cast(Diagnosis, state["diagnosis"])
    query = build_rag_query(diagnosis, state["errors"], state["history"])
    chunks = await asyncio.to_thread(retrieve_doc_chunks, query)
    return {"documentation_context": chunks}


async def tutor_node(state: TutorState) -> dict:
    diagnosis = cast(Diagnosis, state["diagnosis"])
    doc_ctx = state.get("documentation_context") or []
    tutor_response = await run_tutor(
        diagnosis,
        state["history"],
        state["code"],
        state["active_tutor_decorations"],
        documentation_context=doc_ctx,
    )
    return {"tutor_response": tutor_response, "actions": []}


def build_graph():
    builder = StateGraph(TutorState)
    builder.add_node("analyst", analyst_node)
    builder.add_node("rag_retrieve", rag_retrieve_node)
    builder.add_node("tutor", tutor_node)
    builder.add_edge(START, "analyst")
    builder.add_edge("analyst", "rag_retrieve")
    builder.add_edge("rag_retrieve", "tutor")
    builder.add_edge("tutor", END)
    return builder.compile()


tutor_graph = build_graph()

from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph

from agents.analyst import Diagnosis, run_analyst
from agents.tutor import run_tutor


class TutorState(TypedDict):
    code: str
    errors: list[str]
    history: list[dict]
    diagnosis: dict
    tutor_response: str
    actions: list[dict]


async def analyst_node(state: TutorState) -> dict:
    diagnosis = await run_analyst(state["code"], state["errors"])
    return {"diagnosis": diagnosis}


async def tutor_node(state: TutorState) -> dict:
    diagnosis = cast(Diagnosis, state["diagnosis"])
    tutor_response = await run_tutor(diagnosis, state["history"], state["code"])
    return {"tutor_response": tutor_response, "actions": []}


def build_graph():
    builder = StateGraph(TutorState)
    builder.add_node("analyst", analyst_node)
    builder.add_node("tutor", tutor_node)
    builder.add_edge(START, "analyst")
    builder.add_edge("analyst", "tutor")
    builder.add_edge("tutor", END)
    return builder.compile()


tutor_graph = build_graph()

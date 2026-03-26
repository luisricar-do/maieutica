"""Grafo LangGraph: recuperação + geração com Azure OpenAI."""

from __future__ import annotations

import os
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, START, StateGraph

from agents.rag.azure import azure_openai_api_key
from agents.rag.indexer import get_retriever


class RagState(TypedDict):
    question: str
    context: list[str]
    answer: str


def _chat_llm() -> AzureChatOpenAI:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "") or None
    api_key = azure_openai_api_key()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        azure_deployment=deployment,
        api_version=api_version,
        temperature=0,
    )


def build_graph():
    retriever = get_retriever(k=4)
    llm = _chat_llm()

    def retrieve(state: RagState) -> dict:
        docs = retriever.invoke(state["question"])
        return {"context": [d.page_content for d in docs]}

    def generate(state: RagState) -> dict:
        ctx = state.get("context") or []
        context_str = "\n\n---\n\n".join(ctx) if ctx else "(sem trechos recuperados)"
        system = (
            "És um especialista em Portugol. Respondes apenas com base no contexto "
            "fornecido abaixo. Se não encontrares a resposta no contexto, diz "
            "explicitamente que não encontraste informação suficiente na documentação "
            "fornecida e não inventes."
        )
        user = (
            f"Contexto (documentação Portugol):\n\n{context_str}\n\n"
            f"Pergunta: {state['question']}"
        )
        resp = llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return {"answer": resp.content}

    builder = StateGraph(RagState)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()


COMPILED_RAG_GRAPH = build_graph()

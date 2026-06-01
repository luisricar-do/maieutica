import json
import logging
import re
from typing import Literal, NotRequired, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

ANALYST_SYSTEM_PROMPT = """You are a technical analyzer for Portugol (Brazilian pseudocode) programs.
Your ONLY job is to return a structured JSON diagnosis. You NEVER speak to the learner directly.

Given the code and compiler error messages, output ONLY a JSON object with this shape:
{
  "errorType": "syntax" | "type_mismatch" | "undeclared_identifier" | "logic" | "infinite_loop" | "none",
  "errorLine": number or null,
  "affectedVariable": string or null,
  "errorDescription": "short technical description",
  "hintAngle": "a question that could help the learner discover the issue",
  "severity": "low" | "medium" | "high",
  "dataFlowHint": "optional one line in Portuguese about data flow (e.g. variable used before init, read/write path)"
}

Language rules for string fields:
- Write **errorDescription** and **hintAngle** in **Portuguese** (they inform a Portuguese-speaking tutor experience).

Guidelines for hintAngle and errorDescription:
- If compiler error messages or compiler error lines are provided, use them as the primary evidence.
- Prefer the first compiler error line as `errorLine` when the message points to a location.
- Use `type_mismatch` when the compiler reports incompatible types, wrong assignment types, or a value whose type does not fit the declared variable.
- Use `undeclared_identifier` when a variable/function/identifier is used before being declared. If the frontend reports a technical JavaScript error like "Cannot read properties of undefined (reading 'clone')" for a missing identifier, still classify it as `undeclared_identifier` and explain it in learner-friendly Portugol terms.
- Use `syntax` only for malformed syntax, incomplete code, delimiters, brackets, quotes, parser errors, or invalid structure.
- **hintAngle** must be an actionable angle for the tutor: one concrete discovery question in Portuguese. Prefer hints that imply **which region of the code** deserves attention (e.g. declaration vs usage, loop condition vs body, delimiter pairing) so the tutor can choose IDE tools such as `compare_lines`, `highlight_line`, or `highlight_variable` without you naming tools in the JSON.
- For **string** issues (mismatched quotes, mixing `"` and `'`, wrong delimiter such as an accent, missing quotes where needed): hintAngle should steer toward **comparing the character that opens and the one that closes** the text inside `escreva` (or the literal), without giving the exact fix.
- For **type_mismatch**: hintAngle must compare the declared type of the target variable with the type of the assigned value. Do NOT mention delimiters, brackets, "aberturas", or "fechamentos".
- For **undeclared_identifier**: hintAngle must focus on declaration before use and the exact identifier when visible. Do NOT mention delimiters, brackets, "aberturas", or "fechamentos".
- For other errors, keep a concrete question aligned with the symptom (loop, condition, variable), always discovery-oriented.
- **dataFlowHint** (optional): only when useful — a short Portuguese note on declaration vs usage, uninitialized reads, or confusing assignment order (no solution).

Return ONLY the JSON. No extra text. No markdown. No code fences."""


class Diagnosis(TypedDict):
    errorType: Literal[
        "syntax",
        "type_mismatch",
        "undeclared_identifier",
        "logic",
        "infinite_loop",
        "none",
    ]
    errorLine: int | None
    affectedVariable: str | None
    errorDescription: str
    hintAngle: str
    severity: Literal["low", "medium", "high"]
    dataFlowHint: NotRequired[str]


class DiagnosisPartial(TypedDict, total=False):
    """Campos opcionais ao validar JSON parcial do modelo."""

    errorType: str
    errorLine: NotRequired[int | None]
    affectedVariable: NotRequired[str | None]
    errorDescription: NotRequired[str]
    hintAngle: NotRequired[str]
    severity: NotRequired[str]
    dataFlowHint: NotRequired[str]


def _default_diagnosis() -> Diagnosis:
    return {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "",
        "severity": "low",
    }


def _numbered_code(code: str) -> str:
    lines = code.splitlines()
    if not lines and not code.strip():
        return "(empty code)"
    if not lines:
        return "1 | "
    width = len(str(len(lines)))
    return "\n".join(f"{i + 1:{width}} | {line}" for i, line in enumerate(lines))


def _first_positive_int(items: list[int]) -> int | None:
    for item in items:
        if isinstance(item, int) and item >= 1:
            return item
    return None


def _first_error_excerpt(errors: list[str], limit: int = 180) -> str:
    first = next((e.strip() for e in errors if e.strip()), "")
    if not first:
        return ""
    compact = re.sub(r"\s+", " ", first)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _fallback_error_kind_and_variable(first_error: str) -> tuple[str, str | None]:
    normalized = first_error.lower()

    undeclared_match = re.search(
        r"(?:vari[áa]vel|identificador|fun[çc][ãa]o)\s+n[ãa]o\s+declarad[ao]:?\s*([a-zA-Z_]\w*)?",
        normalized,
    )
    if undeclared_match:
        return "undeclared_identifier", undeclared_match.group(1)

    if "undefined" in normalized and "clone" in normalized:
        return "undeclared_identifier", None

    type_terms = (
        "tipos incompat",
        "tipo incompat",
        "não é possível atribuir",
        "nao e possivel atribuir",
        "valor do tipo",
        "compatível",
        "compativel",
    )
    if any(term in normalized for term in type_terms):
        return "type_mismatch", None

    return "syntax", None


def _fallback_diagnosis_for_errors(
    errors: list[str],
    *,
    compiler_error_lines: list[int],
    cursor_line: int | None,
) -> Diagnosis:
    line = _first_positive_int(compiler_error_lines)
    if line is None and isinstance(cursor_line, int) and cursor_line >= 1:
        line = cursor_line

    first_error = next((e.strip() for e in errors if e.strip()), "")
    if first_error:
        description = f"O compilador reportou: {first_error[:240]}"
    else:
        description = "Há um erro de compilação reportado pela IDE."

    error_type, affected_variable = _fallback_error_kind_and_variable(first_error)

    if error_type == "type_mismatch" and line is not None:
        hint = (
            f"Na linha {line}, que tipo de dado a variável deveria guardar e que tipo de valor "
            "está sendo colocado nela?"
        )
    elif error_type == "type_mismatch":
        hint = "Onde ocorre a atribuição indicada, e os dois lados usam tipos compatíveis?"
    elif error_type == "undeclared_identifier" and affected_variable:
        hint = f"Antes de usar `{affected_variable}`, em que linha ela foi declarada?"
    elif error_type == "undeclared_identifier" and line is not None:
        hint = f"Na linha {line}, quais nomes usados ali já foram declarados antes?"
    elif error_type == "undeclared_identifier":
        hint = "Qual identificador da mensagem está sendo usado antes de aparecer em uma declaração?"
    elif line is not None:
        hint = f"O que você percebe ao reler a linha {line} junto com a mensagem do compilador?"
    else:
        hint = "Que trecho do código a mensagem do compilador parece estar apontando?"

    return {
        "errorType": error_type,  # type: ignore[typeddict-item]
        "errorLine": line,
        "affectedVariable": affected_variable,
        "errorDescription": description,
        "hintAngle": hint,
        "severity": "medium",
    }


def _augment_diagnosis_with_error_context(
    diagnosis: Diagnosis,
    errors: list[str],
    *,
    compiler_error_lines: list[int],
    cursor_line: int | None,
) -> Diagnosis:
    if not errors:
        return diagnosis

    out: Diagnosis = dict(diagnosis)  # type: ignore[assignment]
    fallback = _fallback_diagnosis_for_errors(
        errors,
        compiler_error_lines=compiler_error_lines,
        cursor_line=cursor_line,
    )

    if out.get("errorType") == "none":
        out["errorType"] = fallback["errorType"]
    if not isinstance(out.get("errorLine"), int):
        out["errorLine"] = fallback["errorLine"]
    if not str(out.get("errorDescription") or "").strip():
        out["errorDescription"] = fallback["errorDescription"]
    if not str(out.get("hintAngle") or "").strip():
        out["hintAngle"] = fallback["hintAngle"]
    if out.get("severity") == "low":
        out["severity"] = fallback["severity"]
    if out.get("errorType") == "syntax":
        excerpt = _first_error_excerpt(errors)
        description = str(out.get("errorDescription") or "").strip()
        if excerpt and excerpt not in description:
            suffix = f'Trecho literal do compilador: "{excerpt}"'
            out["errorDescription"] = f"{description} {suffix}".strip()
    return out


def _parse_diagnosis(raw: str) -> Diagnosis:
    text = raw.strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Resposta do analista não é um objeto JSON")

    partial: DiagnosisPartial = data  # type: ignore[assignment]
    error_type = partial.get("errorType", "none")
    if error_type not in (
        "syntax",
        "type_mismatch",
        "undeclared_identifier",
        "logic",
        "infinite_loop",
        "none",
    ):
        error_type = "none"

    severity = partial.get("severity", "low")
    if severity not in ("low", "medium", "high"):
        severity = "low"

    raw_df = partial.get("dataFlowHint")
    data_flow_hint = raw_df.strip()[:500] if isinstance(raw_df, str) else ""

    out: Diagnosis = {
        "errorType": error_type,  # type: ignore[typeddict-item]
        "errorLine": partial.get("errorLine"),
        "affectedVariable": partial.get("affectedVariable"),
        "errorDescription": partial.get("errorDescription", ""),
        "hintAngle": partial.get("hintAngle", ""),
        "severity": severity,  # type: ignore[typeddict-item]
    }
    if data_flow_hint:
        out["dataFlowHint"] = data_flow_hint
    return out


async def run_analyst(
    code: str,
    errors: list[str],
    *,
    compiler_error_lines: list[int] | None = None,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
) -> dict:
    llm = create_chat_client(max_tokens=512, temperature=0)

    compiler_lines = compiler_error_lines or []
    errors_block = (
        "\n".join(f"- {e}" for e in errors)
        if errors
        else "(no compiler error messages)"
    )
    compiler_lines_block = (
        ", ".join(str(n) for n in compiler_lines)
        if compiler_lines
        else "(no compiler error lines)"
    )
    cursor_block = (
        f"line {cursor_line} column {cursor_column}"
        if isinstance(cursor_line, int) and cursor_line >= 1
        else "(no cursor position)"
    )
    ast_block = (
        ast_summary.strip() if ast_summary.strip() else "(no AST/editor summary)"
    )
    data_flow_block = (
        data_flow_context.strip()
        if data_flow_context.strip()
        else "(no data flow context)"
    )
    human_content = f"""Portugol code with 1-based line numbers:
```
{_numbered_code(code)}
```

Compiler error messages:
{errors_block}

Compiler error lines:
{compiler_lines_block}

Cursor:
{cursor_block}

AST/editor summary:
{ast_block}

Data flow context:
{data_flow_block}
"""

    messages = [
        SystemMessage(content=ANALYST_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]

    response = await llm.ainvoke(messages)
    content = response.content
    if isinstance(content, list):
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    else:
        text = str(content)

    try:
        diagnosis = _parse_diagnosis(text)
        return _augment_diagnosis_with_error_context(
            diagnosis,
            errors,
            compiler_error_lines=compiler_lines,
            cursor_line=cursor_line,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.exception("Falha ao interpretar JSON do analista: %s", exc)
        if errors:
            return _fallback_diagnosis_for_errors(
                errors,
                compiler_error_lines=compiler_lines,
                cursor_line=cursor_line,
            )
        return _default_diagnosis()

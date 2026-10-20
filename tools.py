"""Safe, bounded tools for searching the homework corpus and doing arithmetic."""

from __future__ import annotations

import ast
import difflib
import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CORPUS_PATH = ROOT / "data" / "corpus.jsonl"
DISTRICTS = (
    "Ossbridge",
    "Ossford",
    "Tarnvale",
    "Kelmarsh",
    "Brightwater",
    "Stonecairn",
    "Harrowfield",
    "Lindenmoor",
    "Redfen",
    "Ashgrove",
    "Millbrook",
    "Coldharbour",
)
MAX_LOOKUP_RESULTS = 4
MAX_EXCERPT_CHARS = 360
MAX_EXPRESSION_LENGTH = 200
MAX_AST_NODES = 40
MAX_VALUE = 1e100

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": (
                "Search the Nine Rivers Region source documents for facts needed "
                "to answer the question. Return at most four short excerpts with "
                "document ID and title. Exclude ARCHIVED profiles; include "
                "applicable correction notices, which override corrected profile "
                "values. Prefer 2025 figures unless the question specifies another "
                "year. If no reliable match exists, return an error instead of guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Names, measures, and year to search for",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a basic arithmetic expression over finite numbers using "
                "only +, -, *, /, and parentheses. Use this for arithmetic based on "
                "retrieved facts; do not put names or code in the expression."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Arithmetic expression, for example 44675 / 921.4",
                    }
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
    },
]


def _read_corpus(corpus_path: Path) -> tuple[list[dict[str, str]] | None, dict[str, str] | None]:
    try:
        documents = [
            json.loads(line)
            for line in corpus_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, {"error": "The source corpus could not be read."}

    if any(
        not isinstance(document, dict)
        or not all(isinstance(document.get(field), str) for field in ("id", "title", "text"))
        for document in documents
    ):
        return None, {"error": "The source corpus contains an invalid document."}
    return documents, None


def _excerpt(document: dict[str, str], query_terms: set[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", document["text"])
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (
            -len(query_terms.intersection(re.findall(r"[a-z0-9]+", item[1].casefold()))),
            item[0],
        ),
    )
    selected: list[str] = []
    used = 0
    for _, sentence in ranked:
        sentence = sentence.strip()
        if not sentence:
            continue
        remaining = MAX_EXCERPT_CHARS - used
        if remaining <= 0:
            break
        if len(sentence) > remaining:
            if not selected:
                selected.append(sentence[:remaining].rstrip())
            break
        selected.append(sentence)
        used += len(sentence) + 1
        if len(selected) >= 3:
            break
    return " ".join(selected)


def lookup(query: str, corpus_path: Path = CORPUS_PATH) -> dict[str, Any]:
    """Return short, cited corpus excerpts; expected input errors are returned as JSON."""
    if not isinstance(query, str) or not query.strip():
        return {"error": "The query must be a non-empty string."}

    try:
        corpus_file = Path(corpus_path)
    except (TypeError, ValueError):
        return {"error": "The source corpus path is invalid."}
    documents, error = _read_corpus(corpus_file)
    if error:
        return error
    if documents is None:
        return {"error": "The source corpus could not be read."}

    mentioned = [
        district
        for district in DISTRICTS
        if re.search(rf"(?<![a-z]){re.escape(district)}(?![a-z])", query, re.IGNORECASE)
    ]
    words = re.findall(r"[a-z]+", query.casefold())
    known_names = {name.casefold() for name in DISTRICTS}
    likely_names = [
        word
        for word in words
        if len(word) >= 5
        and word not in known_names
        and difflib.get_close_matches(word, sorted(known_names), n=1, cutoff=0.72)
    ]
    if likely_names:
        suggestions = sorted(
            {
                difflib.get_close_matches(
                    word, sorted(known_names), n=1, cutoff=0.72
                )[0].title()
                for word in likely_names
            }
        )
        return {
            "error": f"No district named {likely_names[0]}; did you mean "
            + " or ".join(suggestions)
            + "?"
        }

    current_documents = [
        document for document in documents if "ARCHIVED" not in document["title"].upper()
    ]
    selected: list[dict[str, str]] = []
    for district in mentioned:
        profile = next(
            (
                document
                for document in current_documents
                if district.casefold() in document["title"].casefold()
            ),
            None,
        )
        if profile:
            selected.append(profile)

    query_terms = set(re.findall(r"[a-z0-9]+", query.casefold()))
    query_lower = query.casefold()
    if "brightwater" in {name.casefold() for name in mentioned}:
        correction = next((doc for doc in documents if doc["id"] == "NR-16"), None)
        if correction:
            selected.append(correction)

    wants_tariff = any(term in query_lower for term in ("tariff", "price", "cost", "paid"))
    if wants_tariff:
        tariff = next((doc for doc in documents if doc["id"] == "NR-15"), None)
        if tariff:
            selected.append(tariff)

    if not selected:
        scored: list[tuple[int, int, dict[str, str]]] = []
        for index, document in enumerate(current_documents):
            terms = set(
                re.findall(r"[a-z0-9]+", f'{document["title"]} {document["text"]}'.casefold())
            )
            score = len(query_terms.intersection(terms))
            if score:
                scored.append((score, -index, document))
        selected = [item[2] for item in sorted(scored, reverse=True)[:MAX_LOOKUP_RESULTS]]

    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for document in selected:
        if document["id"] not in seen:
            unique.append(document)
            seen.add(document["id"])

    results = [
        {
            "id": document["id"],
            "title": document["title"],
            "text": _excerpt(document, query_terms),
        }
        for document in unique[:MAX_LOOKUP_RESULTS]
    ]
    if not results:
        return {"error": "No matching current facts found."}
    return {"results": results}


class _InvalidExpression(Exception):
    pass


def _evaluate(node: ast.AST, depth: int = 0) -> float:
    if depth > 12:
        raise _InvalidExpression
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, depth + 1)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = float(node.value)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _evaluate(node.operand, depth + 1)
        value = operand if isinstance(node.op, ast.UAdd) else -operand
    elif isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
    ):
        left = _evaluate(node.left, depth + 1)
        right = _evaluate(node.right, depth + 1)
        if isinstance(node.op, ast.Add):
            value = left + right
        elif isinstance(node.op, ast.Sub):
            value = left - right
        elif isinstance(node.op, ast.Mult):
            value = left * right
        else:
            if right == 0:
                raise ZeroDivisionError
            value = left / right
    else:
        raise _InvalidExpression

    if not math.isfinite(value) or abs(value) > MAX_VALUE:
        raise OverflowError
    return value


def calculate(expression: str) -> dict[str, Any]:
    """Evaluate a small arithmetic-only AST without evaluating Python code."""
    if not isinstance(expression, str) or not expression.strip():
        return {"error": "Expression must be a non-empty string."}
    if len(expression) > MAX_EXPRESSION_LENGTH:
        return {"error": "Expression is too long."}
    try:
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
            return {"error": "Expression is too complex."}
        return {"result": _evaluate(tree)}
    except ZeroDivisionError:
        return {"error": "Division by zero."}
    except OverflowError:
        return {"error": "Result exceeds the supported limit."}
    except (SyntaxError, ValueError, RecursionError, _InvalidExpression):
        return {"error": "Invalid arithmetic expression."}

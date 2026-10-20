"""OpenAI Chat Completions implementations for the three homework strategies."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

from tools import TOOL_DEFINITIONS, calculate, lookup


MODEL = "gpt-5.6-luna"
MAX_TOOL_ROUNDS = 5
ANSWER_RE = re.compile(
    r"ANSWER:\s*(?P<answer>[^|\r\n]+?)\s*\|\s*(?P<value>-?\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
SYSTEM_PROMPT = (
    "Answer the user's question using only the supplied source information or, "
    "when tools are available, facts returned by those tools. Check units, years, "
    "corrections, and arithmetic. End with exactly: "
    "ANSWER: <name or yes/no> | <number>. If you cannot establish the answer, "
    "say so and mark it unanswered."
)


def load_inputs() -> tuple[list[dict[str, Any]], str]:
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to a local .env file (never commit that file)."
        )
    root = Path(__file__).resolve().parent
    questions = json.loads((root / "data" / "questions.json").read_text(encoding="utf-8"))
    corpus = "\n".join(
        json.dumps(json.loads(line), ensure_ascii=False)
        for line in (root / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    return questions, corpus


def parse_answer(text: str | None) -> tuple[str, Decimal] | None:
    if not text:
        return None
    match = ANSWER_RE.search(text)
    if not match:
        return None
    try:
        value = Decimal(match.group("value").replace(",", ""))
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return match.group("answer").strip().casefold(), value


def score_answer(text: str | None, question: dict[str, Any]) -> bool:
    parsed = parse_answer(text)
    if not parsed:
        return False
    answer, value = parsed
    expected_answer = str(question["answer"]).strip().casefold()
    decimals = int(question["decimals"])
    expected_value = Decimal(str(question["value"]))
    tolerance = Decimal(1).scaleb(-decimals)
    return answer == expected_answer and abs(value - expected_value) <= tolerance


def _usage(response: Any) -> dict[str, int]:
    usage = response.usage
    return {
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }


class StrategyRunner:
    def __init__(self, client: OpenAI | None = None) -> None:
        load_dotenv()
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to a local .env file (never commit that file)."
            )
        self.client = client or OpenAI()
        self.temperature_supported: bool | None = None

    def _complete(self, messages: list[dict[str, Any]], **options: Any) -> tuple[Any, float]:
        if self.temperature_supported is False:
            options.pop("temperature", None)
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_completion_tokens=500,
                **options,
            )
        except BadRequestError as error:
            if "temperature" not in options or "temperature" not in str(error).casefold():
                raise
            self.temperature_supported = False
            options.pop("temperature")
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_completion_tokens=500,
                **options,
            )
        else:
            if "temperature" in options:
                self.temperature_supported = True
        return response, time.perf_counter() - started

    @staticmethod
    def _base_messages(question: dict[str, Any], corpus: str | None) -> list[dict[str, Any]]:
        system = SYSTEM_PROMPT
        if corpus is not None:
            system += "\n\nSource documents (JSONL):\n" + corpus
        else:
            system += (
                " The source documents are not in the prompt: call lookup for the "
                "relevant facts and calculate for arithmetic."
            )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": question["question"]},
        ]

    def direct(self, question: dict[str, Any], corpus: str) -> dict[str, Any]:
        messages = self._base_messages(question, corpus)
        response, elapsed = self._complete(messages)
        content = response.choices[0].message.content or ""
        usage = _usage(response)
        return {
            "answer_text": content,
            "unanswered": not bool(parse_answer(content)),
            "calls": [{"kind": "model", "seconds": elapsed, **usage}],
            **usage,
        }

    def think_and_vote(
        self, question: dict[str, Any], corpus: str, samples: int = 5
    ) -> dict[str, Any]:
        sample_records: list[dict[str, Any]] = []
        token_totals = {"input_tokens": 0, "output_tokens": 0}
        for sample_index in range(samples):
            messages = self._base_messages(question, corpus)
            messages[0]["content"] += (
                "\nSolve carefully and independently. Verify the facts and arithmetic; "
                "return only the required final answer line."
            )
            response, elapsed = self._complete(messages, temperature=1)
            content = response.choices[0].message.content or ""
            usage = _usage(response)
            for key in token_totals:
                token_totals[key] += usage[key]
            sample_records.append(
                {
                    "sample": sample_index + 1,
                    "answer_text": content,
                    "seconds": elapsed,
                    **usage,
                }
            )

        parsed_samples = [
            (parse_answer(sample["answer_text"]), sample) for sample in sample_records
        ]
        valid = [(parsed, sample) for parsed, sample in parsed_samples if parsed is not None]
        if valid:
            decimals = int(question["decimals"])
            keys = [
                (
                    parsed[0],
                    parsed[1].quantize(Decimal(1).scaleb(-decimals)),
                )
                for parsed, _ in valid
            ]
            counts = Counter(keys)
            winning_key = counts.most_common(1)[0][0]
            winner = next(
                sample
                for parsed, sample in valid
                if (
                    parsed[0],
                    parsed[1].quantize(Decimal(1).scaleb(-decimals)),
                )
                == winning_key
            )
            answer_text = winner["answer_text"]
        else:
            answer_text = ""

        return {
            "answer_text": answer_text,
            "unanswered": not bool(valid),
            "samples": sample_records,
            "calls": [
                {
                    "kind": "model",
                    "sample": sample["sample"],
                    "seconds": sample["seconds"],
                    "input_tokens": sample["input_tokens"],
                    "output_tokens": sample["output_tokens"],
                }
                for sample in sample_records
            ],
            **token_totals,
        }

    def with_tools(
        self, question: dict[str, Any], vague_lookup: bool = False
    ) -> dict[str, Any]:
        messages = self._base_messages(question, None)
        tools = json.loads(json.dumps(TOOL_DEFINITIONS))
        if vague_lookup:
            for tool in tools:
                if tool["function"]["name"] == "lookup":
                    tool["function"]["description"] = "Looks things up."

        calls_log: list[dict[str, Any]] = []
        token_totals = {"input_tokens": 0, "output_tokens": 0}
        model_calls: list[dict[str, Any]] = []

        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            response, elapsed = self._complete(messages, tools=tools, tool_choice="auto")
            usage = _usage(response)
            for key in token_totals:
                token_totals[key] += usage[key]
            model_calls.append(
                {
                    "round": round_number,
                    "seconds": elapsed,
                    **usage,
                }
            )
            message = response.choices[0].message
            if not message.tool_calls:
                content = message.content or ""
                return {
                    "answer_text": content,
                    "unanswered": not bool(parse_answer(content)),
                    "calls": model_calls,
                    "tool_calls": calls_log,
                    **token_totals,
                }

            # Preserve the assistant's tool-call message, including IDs and arguments.
            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                start = time.perf_counter()
                arguments: Any = None
                try:
                    if not isinstance(call.function.arguments, str):
                        raise ValueError("Tool arguments must be a JSON string.")
                    arguments = json.loads(call.function.arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be a JSON object.")
                    if call.function.name == "lookup":
                        if set(arguments) != {"query"} or not isinstance(arguments["query"], str):
                            result: dict[str, Any] = {
                                "error": "lookup requires exactly one string field: query."
                            }
                        else:
                            result = lookup(arguments["query"])
                    elif call.function.name == "calculate":
                        if set(arguments) != {"expression"} or not isinstance(
                            arguments["expression"], str
                        ):
                            result = {
                                "error": "calculate requires exactly one string field: expression."
                            }
                        else:
                            result = calculate(arguments["expression"])
                    else:
                        result = {"error": f"Unknown tool: {call.function.name}."}
                except (json.JSONDecodeError, ValueError) as error:
                    result = {"error": f"Invalid tool arguments: {error}"}
                tool_seconds = time.perf_counter() - start
                calls_log.append(
                    {
                        "round": round_number,
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                        "parsed_arguments": arguments,
                        "result": result,
                        "seconds": tool_seconds,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return {
            "answer_text": "",
            "unanswered": True,
            "round_limit_reached": True,
            "calls": model_calls,
            "tool_calls": calls_log,
            **token_totals,
        }

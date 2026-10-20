"""Run one or more homework strategies and save reproducible JSONL results."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import tiktoken

from strategies import MODEL, StrategyRunner, load_inputs, score_answer
from tools import TOOL_DEFINITIONS


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
STRATEGIES = ("S1", "S2", "S3")


def _tool_definition_tokens() -> int:
    try:
        encoding = tiktoken.encoding_for_model(MODEL)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    serialized = json.dumps(TOOL_DEFINITIONS, ensure_ascii=False, separators=(",", ":"))
    return len(encoding.encode(serialized))


def _pricing() -> tuple[float, float] | None:
    input_rate = os.environ.get("OPENAI_INPUT_PRICE_PER_MILLION")
    output_rate = os.environ.get("OPENAI_OUTPUT_PRICE_PER_MILLION")
    if input_rate is None and output_rate is None:
        return None
    if input_rate is None or output_rate is None:
        raise RuntimeError(
            "Set both OPENAI_INPUT_PRICE_PER_MILLION and "
            "OPENAI_OUTPUT_PRICE_PER_MILLION, or leave both unset."
        )
    try:
        return float(input_rate), float(output_rate)
    except ValueError as error:
        raise RuntimeError("API token prices must be numeric.") from error


def _cost(result: dict[str, Any], rates: tuple[float, float] | None) -> float | None:
    if rates is None:
        return None
    input_rate, output_rate = rates
    return (
        result["input_tokens"] * input_rate
        + result["output_tokens"] * output_rate
    ) / 1_000_000


def run(args: argparse.Namespace) -> dict[str, Any]:
    questions, corpus = load_inputs()
    if args.questions:
        requested = set(args.questions)
        questions = [question for question in questions if question["id"] in requested]
        unknown = requested - {question["id"] for question in questions}
        if unknown:
            raise ValueError("Unknown question IDs: " + ", ".join(sorted(unknown)))
    if not questions:
        raise ValueError("No questions selected.")
    if args.vague_lookup and "S3" not in args.strategies:
        raise ValueError("--vague-lookup can only be used with S3.")

    OUTPUTS.mkdir(exist_ok=True)
    output_paths = [OUTPUTS / f"{args.run_id}_{strategy}.jsonl" for strategy in args.strategies]
    summary_path = OUTPUTS / f"{args.run_id}_summary.json"
    existing = [path.name for path in [*output_paths, summary_path] if path.exists()]
    if existing:
        raise FileExistsError(
            "Output already exists; choose a new --run-id: " + ", ".join(existing)
        )

    runner = StrategyRunner()
    rates = _pricing()
    summaries: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    temperature_supported: bool | None = None

    for strategy, output_path in zip(args.strategies, output_paths):
        records: list[dict[str, Any]] = []
        with output_path.open("w", encoding="utf-8") as output:
            for question in questions:
                started = datetime.now().astimezone()
                timer_start = time.perf_counter()
                if strategy == "S1":
                    result = runner.direct(question, corpus)
                elif strategy == "S2":
                    result = runner.think_and_vote(question, corpus, samples=5)
                    temperature_supported = runner.temperature_supported
                else:
                    result = runner.with_tools(question, vague_lookup=args.vague_lookup)
                wall_seconds = time.perf_counter() - timer_start
                record = {
                    "timestamp": started.isoformat(),
                    "run_id": args.run_id,
                    "model": MODEL,
                    "strategy": strategy,
                    "question_id": question["id"],
                    "question": question["question"],
                    "answer_text": result["answer_text"],
                    "correct": score_answer(result["answer_text"], question),
                    "unanswered": result["unanswered"],
                    "wall_seconds": wall_seconds,
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "estimated_cost_usd": _cost(result, rates),
                    "calls": result["calls"],
                    "tool_calls": result.get("tool_calls", []),
                    "samples": result.get("samples", []),
                    "round_limit_reached": result.get("round_limit_reached", False),
                    "answer_key": {
                        "answer": question["answer"],
                        "value": question["value"],
                        "decimals": question["decimals"],
                    },
                }
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                records.append(record)
                all_records.append(record)
                print(
                    f"{args.run_id} {strategy} {question['id']}: "
                    f"{'correct' if record['correct'] else 'incorrect/unanswered'} "
                    f"({wall_seconds:.1f}s)"
                )

        total_seconds = sum(record["wall_seconds"] for record in records)
        summary = {
            "run_id": args.run_id,
            "strategy": strategy,
            "model": MODEL,
            "questions_run": len(records),
            "correct": sum(record["correct"] for record in records),
            "unanswered": sum(record["unanswered"] for record in records),
            "input_tokens": sum(record["input_tokens"] for record in records),
            "output_tokens": sum(record["output_tokens"] for record in records),
            "median_seconds_per_question": statistics.median(
                record["wall_seconds"] for record in records
            ),
            "total_seconds": total_seconds,
            "estimated_cost_usd": (
                sum(record["estimated_cost_usd"] for record in records)
                if rates is not None
                else None
            ),
            "token_prices_per_million": (
                {"input": rates[0], "output": rates[1]} if rates is not None else None
            ),
            "temperature_supported": temperature_supported if strategy == "S2" else None,
            "tool_definition_tokens_estimate": (
                _tool_definition_tokens() if strategy == "S3" else None
            ),
            "results_file": output_path.name,
        }
        summaries.append(summary)
        print(json.dumps(summary, indent=2))

    summary_data = {
        "run_id": args.run_id,
        "model": MODEL,
        "vague_lookup_description": args.vague_lookup,
        "summaries": summaries,
        "per_question": [
            {
                "question_id": question["id"],
                "strategies": {
                    record["strategy"]: {
                        "correct": record["correct"],
                        "unanswered": record["unanswered"],
                        "answer": record["answer_text"],
                    }
                    for record in all_records
                    if record["question_id"] == question["id"]
                },
            }
            for question in questions
        ],
    }
    summary_path.write_text(
        json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved: {summary_path}")
    return summary_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Unique output filename prefix (default: current timestamp)",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=STRATEGIES,
        default=list(STRATEGIES),
        help="Strategies to run; default runs all three",
    )
    parser.add_argument(
        "--questions",
        nargs="*",
        help="Optional question IDs for a pilot, for example --questions Q-09",
    )
    parser.add_argument(
        "--vague-lookup",
        action="store_true",
        help="Use a deliberately vague lookup description for the C1 experiment",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()

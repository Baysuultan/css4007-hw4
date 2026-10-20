import json

import pytest

from tools import calculate, lookup


def result_text(result):
    return " ".join(item["text"] for item in result.get("results", []))


def result_ids(result):
    return {item["id"] for item in result.get("results", [])}


def test_lookup_finds_2025_population_and_area():
    result = lookup("Brightwater 2025 population area")

    assert "NR-05" in result_ids(result)
    assert "44,675" in result_text(result)


def test_lookup_suggests_correct_spelling():
    result = lookup("Ossbrige 2025 population")

    assert "error" in result
    assert "Ossbridge" in result["error"]


def test_lookup_catches_a_typo_even_if_another_district_is_correct():
    result = lookup("Ossbrige or Ossford population")

    assert result == {
        "error": "No district named ossbrige; did you mean Ossbridge?"
    }


def test_lookup_distinguishes_similarly_named_districts():
    bridge = lookup("Ossbridge 2025 population")
    ford = lookup("Ossford 2025 population")

    assert result_ids(bridge) == {"NR-01"}
    assert result_ids(ford) == {"NR-02"}


def test_lookup_never_returns_archived_profiles():
    result = lookup("Tarnvale 2025 population")

    assert "NR-03" in result_ids(result)
    assert "NR-13" not in result_ids(result)
    assert "ARCHIVED" not in result_text(result)


def test_lookup_includes_correction_for_brightwater():
    result = lookup("Brightwater Millbrook 2025 population area density correction")

    assert "NR-05" in result_ids(result)
    assert "NR-11" in result_ids(result)
    assert "NR-16" in result_ids(result)
    assert "921.4" in result_text(result)


def test_lookup_reports_unreadable_corpus(tmp_path):
    result = lookup("Tarnvale population", tmp_path / "missing.jsonl")

    assert result == {"error": "The source corpus could not be read."}


def test_lookup_rejects_empty_query():
    assert lookup("   ") == {"error": "The query must be a non-empty string."}


def test_lookup_reports_invalid_corpus(tmp_path):
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text(json.dumps({"id": "NR-01"}) + "\n", encoding="utf-8")

    assert lookup("Tarnvale population", corpus) == {
        "error": "The source corpus contains an invalid document."
    }


def test_calculate_multiplies_expected_values():
    result = calculate("48317 * 1.0947")

    assert result["result"] == pytest.approx(52892.6199)


def test_calculate_respects_parentheses_and_unary_signs():
    assert calculate("-(8 + 2) * 3") == {"result": -30.0}


def test_calculate_reports_division_by_zero():
    assert calculate("10 / 0") == {"error": "Division by zero."}


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "(1).__class__",
        "9**9**9",
    ],
)
def test_calculate_rejects_code_attributes_and_power(expression):
    assert "error" in calculate(expression)


def test_calculate_rejects_oversized_results():
    assert calculate("1e101") == {"error": "Result exceeds the supported limit."}


def test_calculate_rejects_long_expressions():
    assert calculate("1" * 201) == {"error": "Expression is too long."}

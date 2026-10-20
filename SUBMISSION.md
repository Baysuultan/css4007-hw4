# HW4 — submission

**AI assistance:** Copilot helped draft the plan and implementation; all measurements must come from the submitted scripts and saved runs.

---

## Part A — Plan on paper (Easy)

> Commit this whole part before any `.py` file exists.

### A1 — The steps

| # | Step | What goes in (types) | What comes out (types) | When it goes wrong | Tool, loop, or model? |
|---|---|---|---|---|---|
| 1 | Parse the question | Question text (`str`) | Names, requested measures, years, units, and operation as a structured interpretation (`dict`) | If intent or a name is ambiguous, ask lookup for evidence and do not invent a value; final answer may be unanswered | Model |
| 2 | Retrieve current facts | Search query (`str`) | Up to four short evidence excerpts (`list[dict]`) with document IDs and titles | No match returns a clear error; ambiguous names include both candidates; archived profiles are excluded; a correction notice is included and takes precedence | `lookup` tool |
| 3 | Normalize facts | Evidence (`list[dict]`) and intended measures (`str`) | Values and units (`dict[str, float | str]`) | Missing/duplicate facts or incompatible/unknown units are reported to the model; convert megalitres to cubic metres only using NR-15's stated conversion | Model |
| 4 | Calculate requested quantities | Arithmetic expression (`str`) built from evidence | Finite numeric result (`float`) | Invalid syntax/operators, division by zero, or oversized values return an error; never execute arbitrary code | `calculate` tool |
| 5 | Compare and format | Candidate names (`list[str]`), calculated values (`list[float]`), question (`str`) | Final answer text ending `ANSWER: <name or yes/no> | <number>` | If evidence is insufficient, leave unanswered rather than guess; round only the displayed value to the question's decimals | Model |
| 6 | Orchestrate and score | Tool calls, responses, and final answer (`dict`/`str`) | Conversation with one result per tool-call ID; log and scored answer | Invalid JSON gets a tool error; round limit stops the loop and marks unanswered; scoring requires an exact name/yes-no and the specified numeric tolerance | Loop |

**How the steps connect:**

Step 1 creates the search query for step 2. Step 2's cited excerpts feed step 3; normalized values feed step 4; step 4's results and the evidence feed step 5. The loop (step 6) carries each tool result back to the model and scores/logs its final answer.

**What I am assuming:**

Use 2025 census, fiscal-year, and water-use figures unless the question explicitly names another year; school figures are 2025/26. NR-13 and NR-14 are archived and must not override current profiles. NR-16 corrects Brightwater's area to 921.4 km2; corrections take precedence. NR-15 defines 1 megalitre = 1,000 m3 and the 2025 tariff. Keep full precision through comparisons and calculations, then round the final numeric answer to the question's `decimals`. Convert units before comparing. The most sensitive assumption is retrieving the corrected, current fact rather than an archived or mistyped one.

### A2 — The two tools

#### `lookup`

```json
{
  "type": "function",
  "function": {
    "name": "lookup",
    "description": "Search the Nine Rivers Region source documents for facts needed to answer the question. Return at most four short excerpts with document ID and title. Exclude ARCHIVED profiles; include applicable correction notices, which override corrected profile values. Prefer 2025 figures unless the question specifies another year. If no reliable match exists, return an error instead of guessing.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "Names, measures, and year to search for"
        }
      },
      "required": ["query"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | JSON with up to four concise excerpts; each includes source ID, title, and relevant text |
| no match | `{"error":"No matching current facts found."}` |
| misspelled or ambiguous name | A helpful error with likely district names; do not silently choose between Ossbridge/Ossford |
| archived profile | Excluded; return the current profile and applicable notice instead |
| unreadable corpus / unexpected input | A short JSON error; no exception escapes the tool |

**Worst thing it could do with strange or dangerous input:** Return irrelevant but bounded text or disclose a small excerpt from this public corpus; it cannot access files named by the query or execute it.

#### `calculate`

```json
{
  "type": "function",
  "function": {
    "name": "calculate",
    "description": "Evaluate a basic arithmetic expression over finite numbers using only +, -, *, /, and parentheses. Use this for arithmetic based on retrieved facts; do not put names or code in the expression.",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {
          "type": "string",
          "description": "Arithmetic expression, for example 44675 / 921.4"
        }
      },
      "required": ["expression"],
      "additionalProperties": false
    }
  }
}
```

| Case | What the tool returns |
|---|---|
| success | JSON containing the finite numeric result |
| malformed expression / unsupported operator | `{"error":"Invalid arithmetic expression."}` |
| division by zero | `{"error":"Division by zero."}` |
| non-finite or excessive result | `{"error":"Result exceeds the supported limit."}` |

**Worst thing it could do with strange or dangerous input:** Return a wrong finite arithmetic result within configured limits; AST validation prevents attribute access, calls, and arbitrary code execution.

### A3 — Q-09 by hand

```json
[
  {
    "role": "user",
    "content": "Which district has the higher population density in 2025, Brightwater or Millbrook, and by how many residents per square kilometre?"
  },
  {
    "role": "assistant",
    "tool_calls": [
      {
        "id": "call_lookup_1",
        "type": "function",
        "function": {
          "name": "lookup",
          "arguments": "{\"query\":\"Brightwater Millbrook 2025 population and area; include correction notice\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_lookup_1",
    "content": "{\"results\":[{\"id\":\"NR-05\",\"title\":\"Brightwater district profile (2025)\",\"text\":\"2025 census population 44,675; profile area 912.4 km2 (corrected by NR-16).\"},{\"id\":\"NR-11\",\"title\":\"Millbrook district profile (2025)\",\"text\":\"2025 census population 37,203; area 758.6 km2.\"},{\"id\":\"NR-16\",\"title\":\"Correction notice - Brightwater\",\"text\":\"Brightwater's correct area is 921.4 km2; other profile figures are correct.\"}]}"
  },
  {
    "role": "assistant",
    "tool_calls": [
      {
        "id": "call_calculate_1",
        "type": "function",
        "function": {
          "name": "calculate",
          "arguments": "{\"expression\":\"37203 / 758.6 - 44675 / 921.4\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_calculate_1",
    "content": "{\"result\":0.572...}"
  },
  {
    "role": "assistant",
    "content": "Millbrook has the higher population density by 0.6 residents per square kilometre. ANSWER: Millbrook | 0.6"
  }
]
```

**My arithmetic:** Brightwater: 44,675 / 921.4 = about 48.486 residents/km2. Millbrook: 37,203 / 758.6 = about 49.042 residents/km2. Difference = about 0.556, which rounds to 0.6 at one decimal; Millbrook is higher.

### A4 — Why I split it this way

One alternative is a single `answer_question` tool that reads the corpus, identifies facts, performs arithmetic, and returns the final answer. I did not choose it because its responsibilities are harder to test independently and the model cannot inspect or correct a mistaken intermediate calculation. Separating retrieval from a restricted calculator makes evidence traceable and isolates arithmetic safety.

---

## Part B — Build it and run it (Medium)

### What I changed from Part A while coding

None. `lookup` returns at most four short, cited excerpts; it excludes archived profiles and includes the Brightwater correction when relevant. `calculate` accepts only finite numeric constants and `+`, `-`, `*`, `/`, and parentheses.

### B2 — Tests

```text
python -m pytest -q
...................                                                      [100%]
19 passed in 1.91s
```

### B3 — The loop

- Round limit, and why: 5 assistant/tool rounds. A question normally needs only a few fact lookups and calculations; the limit prevents an unbounded loop. If the fifth response still requests tools, the question is marked unanswered.
- Where the logs are: `outputs/<run-id>_<strategy>.jsonl` records each question, model-call usage/time, each tool call's ID, raw and parsed inputs, result and tool duration. `outputs/<run-id>_summary.json` contains aggregate metrics and per-question scores.
- Real Q-09 conversation compared with my A3 version, what is different: Not measured yet. The API key is not configured in this environment, so no real conversation has been generated; the saved A3 exchange is the planned conversation, not a claimed model trace.

### B4 — Three strategies

**What I kept the same:**

Model `gpt-5.6-luna`, Chat Completions API, the same 20 questions, base answer-format instructions, and `max_completion_tokens=500`. S1 and S2 receive all 17 source documents; S3 receives no corpus text and has only the two tools. S2 makes five independent calls (`k=5`) with `temperature=1`; the runner retries without that setting only if the API rejects it, and records whether temperature was supported. S3 uses a five-round limit. Usage sums every API response, including all five S2 samples and every S3 round. API token prices are supplied through `OPENAI_INPUT_PRICE_PER_MILLION` and `OPENAI_OUTPUT_PRICE_PER_MILLION`; cost stays blank in results unless both rates are configured.

**My rule for a correct answer** (written before the first full run):

The parsed answer label must exactly match the expected name or `yes`/`no` (case-insensitive); the numeric value must be within `10^-decimals` of the expected value. The tolerance is one unit in the last reported decimal place. An unparseable or absent `ANSWER:` line is unanswered/incorrect.

**Run status:** No paid model runs have been made: `OPENAI_API_KEY` is not set. Therefore the result and per-question tables below are intentionally unfilled; no API outputs, timings, costs, or accuracies have been fabricated. Configure a local, ignored `.env`, then run the pilot and two full runs as described in `README.md` before submitting.

Example commands after setting the key and both token-price environment variables:

```text
python run.py --run-id pilot --strategies S3 --questions Q-09 Q-01 Q-18
python run.py --run-id run1
python run.py --run-id run2
python run.py --run-id c1-clear --strategies S3 --questions Q-01 Q-02 Q-03 Q-04 Q-05
python run.py --run-id c1-vague --strategies S3 --questions Q-01 Q-02 Q-03 Q-04 Q-05 --vague-lookup
```

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | | | | | | | |
| 1 | S2 think and vote (k = ) | | | | | | | |
| 1 | S3 tools | | | | | | | |
| 2 | S1 direct | | | | | | | |
| 2 | S2 think and vote (k = ) | | | | | | | |
| 2 | S3 tools | | | | | | | |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | | | |
| Q-02 | | | |
| Q-03 | | | |
| Q-04 | | | |
| Q-05 | | | |
| Q-06 | | | |
| Q-07 | | | |
| Q-08 | | | |
| Q-09 | | | |
| Q-10 | | | |
| Q-11 | | | |
| Q-12 | | | |
| Q-13 | | | |
| Q-14 | | | |
| Q-15 | | | |
| Q-16 | | | |
| Q-17 | | | |
| Q-18 | | | |
| Q-19 | | | |
| Q-20 | | | |

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

Not run because the model API key is unavailable. To collect this evidence, select five question IDs and run S3 twice with the same run settings, adding `--vague-lookup` to the second run; the JSONL files log call counts, arguments and answers.

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| | | | | |

### C2 — Three mistakes explained

This comparison requires actual answers and logs, so I cannot select or quote three mistakes yet. The expected mechanisms to check against the logs are: S1 can miss or misread a fact in a long prompt; S2 can reduce random variation but repeated samples may share the same systematic error; S3 delegates arithmetic to a bounded calculator, while retrieval errors or a wrong expression can still produce a wrong answer. Each S3 round resends the growing conversation, so later requests can use more input tokens.

### C3 — Which strategy I would use, and what would change it

No evidence-based winner can be selected before the runs. In principle, S1 is the lowest-call baseline for a tiny corpus and simple questions; S2 trades roughly five model calls per question for a chance to reduce sampling variance; S3 is attractive when traceable retrieval and exact arithmetic matter, but its tool loop adds latency and tokens. A very small budget or tight deadline would favor S1; a corpus 1,000 times larger would favor indexed retrieval with tools; questions requiring no arithmetic reduce the calculator's value.

### C4 — How sure I can be

Not measured: there are no two full runs to compare. Twenty questions from one fictional corpus would still be a small sample; the two-run difference and the gap between the top strategies must be computed from the saved outputs before drawing a strong conclusion.

### Final questions

1. A `tool_calls` message is the model requesting that the caller run named functions with supplied arguments; it has not run those functions itself. The application validates and executes each request, then sends a tool-role message keyed by the matching call ID so the model can continue.
2. `arguments` is JSON serialized in the API message, so the program must parse it and validate the resulting object before calling a function. Passing the raw JSON string directly would make the function treat the whole serialized object as its query or expression, not as its named parameter.
3. The two serialized tool definitions tokenize to an estimated **213 tokens** using `tiktoken` (the `o200k_base` encoding when the model name is not recognized). This is a local estimate of the JSON schema, not a measured API usage delta.
4. The S2/S1 cost ratio is not measured because no model calls were made. The runner totals usage across all five S2 samples and calculates cost only when both per-million token prices are configured.
5. Not known yet: no S3 question has been run. The JSONL tool-call logs will show the maximum number of model rounds per question.
6. For 100,000 documents, I would replace a full scan with a search index or retrieval service, filter by document metadata/version, and rank a small set of relevant passages. I would retain source IDs, archived-status filtering, and correction precedence.
7. `calculate` parses an AST and permits only numeric constants, unary signs, and `+`, `-`, `*`, `/`; it rejects calls, attributes, powers, oversized expressions, division by zero, and non-finite or excessive results. The model can still select incorrect facts, units, or an incorrect expression, so safe execution does not guarantee a correct answer.
8. Tools are most useful for multi-document questions that require combining figures, unit conversion, and arithmetic. They add less value when the answer is stated directly in a small prompt and no calculation or source verification is needed.

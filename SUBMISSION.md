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
19 passed in 1.96s
```

### B3 — The loop

- Round limit, and why: 5 assistant/tool rounds. A question normally needs only a few fact lookups and calculations; the limit prevents an unbounded loop. If the fifth response still requests tools, the question is marked unanswered.
- Where the logs are: `outputs/<run-id>_<strategy>.jsonl` records each question, model-call usage/time, each tool call's ID, raw and parsed inputs, result and tool duration. `outputs/<run-id>_summary.json` contains aggregate metrics and per-question scores.
- Real Q-09 conversation compared with my A3 version, what is different: In both full runs, the model made one lookup call for Brightwater, Millbrook, and the Brightwater correction, then two separate calculate calls (`44675 / 921.4` and `37203 / 758.6`), followed by a final answer. My hand-written A3 used a single subtraction expression in one calculate call. The real model chose to calculate each density separately and subtract in its own final step. Run 1 returned `ANSWER: Millbrook | 0.56 residents per square kilometre`.

### B4 — Three strategies

**What I kept the same:**

Model `gpt-5.6-luna`, Chat Completions API, `reasoning_effort=none` (required by this model for tools on this endpoint), the same 20 questions, base answer-format instructions, and `max_completion_tokens=500`. S1 and S2 receive all 17 source documents; S3 receives no corpus text and has only the two tools. S2 makes five independent calls (`k=5`) with `temperature=1`; the API accepted this setting in both runs. S3 uses a five-round limit. Usage sums every API response, including all five S2 samples and every S3 round. API token prices can be supplied through `OPENAI_INPUT_PRICE_PER_MILLION` and `OPENAI_OUTPUT_PRICE_PER_MILLION`; they were not known for this model, so costs are unavailable.

**My rule for a correct answer** (written before the first full run):

The parsed answer label must exactly match the expected name or `yes`/`no` (case-insensitive); the numeric value must be within `10^-decimals` of the expected value. The tolerance is one unit in the last reported decimal place. An unparseable or absent `ANSWER:` line is unanswered/incorrect.

**Runs completed:** `run1` and `run2` each cover all 20 questions for S1, S2, and S3. A separate five-question S3 experiment compares the clear and vague lookup descriptions. Exact model token prices were not available, so costs in USD are reported as unavailable rather than guessed. All run logs and summaries are saved in `outputs/`.

```text
python run.py --run-id run1
python run.py --run-id run2
python run.py --run-id c1_clear --strategies S3 --questions Q-01 Q-09 Q-13 Q-18 Q-20
python run.py --run-id c1_vague --strategies S3 --questions Q-01 Q-09 Q-13 Q-18 Q-20 --vague-lookup
```

| Run | Strategy | Correct /20 | Unanswered | Input tokens | Output tokens | Median seconds per question | Total seconds | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S1 direct | 15/20 | 0 | 48,000 | 2,004 | 1.69 | 37.01 | unavailable |
| 1 | S2 think and vote (k = 5) | 4/20 | 0 | 241,900 | 1,753 | 5.50 | 113.70 | unavailable |
| 1 | S3 tools | 19/20 | 1 | 47,666 | 3,466 | 4.66 | 103.08 | unavailable |
| 2 | S1 direct | 14/20 | 0 | 48,000 | 1,876 | 1.77 | 38.08 | unavailable |
| 2 | S2 think and vote (k = 5) | 4/20 | 0 | 241,900 | 1,816 | 5.43 | 108.17 | unavailable |
| 2 | S3 tools | 17/20 | 2 | 50,017 | 3,639 | 5.33 | 107.32 | unavailable |

**Per question (run 1):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✗ | ✓ |
| Q-02 | ✓ | ✗ | ✓ |
| Q-03 | ✓ | ✗ | ✓ |
| Q-04 | ✓ | ✗ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✓ | ✓ | ✓ |
| Q-07 | ✓ | ✗ | ✓ |
| Q-08 | ✓ | ✗ | ✓ |
| Q-09 | ✓ | ✗ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✓ | ✗ | ✓ |
| Q-12 | ✓ | ✗ | ✓ |
| Q-13 | ✓ | ✓ | ✓ |
| Q-14 | ✓ | ✗ | ✓ |
| Q-15 | ✗ | ✗ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✗ | ✗ |
| Q-18 | ✗ | ✗ | ✓ |
| Q-19 | ✓ | ✗ | ✓ |
| Q-20 | ✗ | ✗ | ✓ |

**Per question (run 2):**

| Question | S1 | S2 | S3 |
|---|:---:|:---:|:---:|
| Q-01 | ✓ | ✗ | ✓ |
| Q-02 | ✓ | ✗ | ✓ |
| Q-03 | ✓ | ✗ | ✓ |
| Q-04 | ✓ | ✗ | ✓ |
| Q-05 | ✗ | ✗ | ✓ |
| Q-06 | ✓ | ✓ | ✓ |
| Q-07 | ✓ | ✗ | ✗ |
| Q-08 | ✓ | ✗ | ✓ |
| Q-09 | ✓ | ✗ | ✓ |
| Q-10 | ✓ | ✓ | ✓ |
| Q-11 | ✓ | ✗ | ✓ |
| Q-12 | ✓ | ✗ | ✓ |
| Q-13 | ✗ | ✓ | ✓ |
| Q-14 | ✗ | ✗ | ✓ |
| Q-15 | ✗ | ✗ | ✓ |
| Q-16 | ✓ | ✓ | ✓ |
| Q-17 | ✗ | ✗ | ✗ |
| Q-18 | ✓ | ✗ | ✓ |
| Q-19 | ✓ | ✗ | ✓ |
| Q-20 | ✗ | ✗ | ✗ |

`✓` means the label and number both met the scoring rule. `✗` includes incorrect and unanswered responses; JSONL logs distinguish them.

---

## Part C — Explain and choose (Hard)

### C1 — Does the tool description matter?

Five identical questions were run with each description. Call counts below are total function invocations (one model round may contain multiple calls). The clear description used 22 calls total and answered 4/5; the vague description used 23 calls and answered 5/5. The inputs changed: for Q-01, Q-09, and Q-13 the clear prompt often searched combined names together, while the vague variant issued separate per-district lookups; for Q-18, the vague variant used shorter queries. This small sample does not show that vague descriptions are better: call counts did not consistently fall, and the answer change may be sampling variation.

| Question | Calls (your description) | Calls (vague) | Inputs (example difference) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|---|
| Q-01 | 3 | 4 | Combined Ossbridge/Ossford lookup vs separate lookups | Ossbridge \| 4.57 | Ossbridge \| 4.57 |
| Q-09 | 4 | 4 | Combined Brightwater/Millbrook lookup vs separate lookups | Millbrook \| 0.56 | Millbrook \| 0.56 |
| Q-13 | 4 | 5 | Clear query combines three districts; vague query split them | Coldharbour \| 4.16 | Coldharbour \| 4.16 |
| Q-18 | 2 | 3 | Correction-aware full query vs short `Millbrook population 2020 2025` | yes \| 40,013 | yes \| 40,013 |
| Q-20 | 9 | 7 | Both looked up districts separately; clear variant repeated calls | unanswered (round limit) | Ashgrove \| 2,993 |

### C2 — Three mistakes explained

1. **S1, Q-20:** the log says `ANSWER: Ashgrove | 2,998.45 tenge per resident`, while the expected value is 2,993. The model selected the right district but its intermediate per-resident arithmetic was slightly inaccurate; a direct prompt gives it no exact arithmetic enforcement.
2. **S2, Q-04:** all five samples selected Ashgrove, for example `ANSWER: Ashgrove | 3.09 pupils per school more than Millbrook`; the correct district is Millbrook and the difference is 2.59. Voting cannot fix a systematic error shared by samples, and here sample values varied widely instead of converging on the right calculation.
3. **S3, Q-17:** the log contains `{"expression":"7146 * 1000000 * 142.35 / 90212"}`. NR-15 says 1 megalitre is 1,000 cubic metres, but the model used 1,000,000, then continued requesting calculations until the five-round cap and was marked unanswered. The calculator evaluated the supplied expression safely and exactly; it cannot correct a wrong conversion or infer the intended formula. Repeated tool turns resend the growing conversation, so later calls consume more input tokens.

### C3 — Which strategy I would use, and what would change it

For this benchmark I would use S3: it scored 19/20 and 17/20, versus S1's 15/20 and 14/20 and S2's 4/20 in both runs. S3 took about 103–107 seconds per full set, roughly 2.8 times S1's 37–38 seconds; its total input-plus-output tokens (51,132 and 53,656) were close to S1's (50,004 and 49,876). S2 used about 4.9 times S1's tokens and was less accurate here. Exact dollar costs cannot be compared without the model rates. A very small budget or strict latency target would favor S1; for 1,000 times more documents I would choose indexed retrieval with tools; for questions that merely quote a fact without arithmetic, I would compare S1 against retrieval-only tools and avoid paying for an unnecessary calculator.

### C4 — How sure I can be

Accuracy varied by one question for S1 (15 to 14), zero for S2 (4 to 4), and two for S3 (19 to 17). S3 led S1 by four questions in run 1 and three in run 2, a gap larger than the observed two-question S3 run variation, but only 20 questions and two runs are weak evidence and the questions share one fictional corpus. I would want at least 100 representative questions across several runs before trusting a small ranking difference.

### Final questions

1. A `tool_calls` message is the model requesting that the caller run named functions with supplied arguments; it has not run those functions itself. The application validates and executes each request, then sends a tool-role message keyed by the matching call ID so the model can continue.
2. `arguments` is JSON serialized in the API message, so the program must parse it and validate the resulting object before calling a function. Passing the raw JSON string directly would make the function treat the whole serialized object as its query or expression, not as its named parameter.
3. The two serialized tool definitions tokenize to an estimated **213 tokens** using `tiktoken` (the `o200k_base` encoding when the model name is not recognized). This is a local estimate of the JSON schema, not a measured API usage delta.
4. The exact S2/S1 dollar-cost ratio is unavailable because the model's input/output rates were not known. As a token-use proxy, S2 used 243,653 total tokens against S1's 50,004 in run 1 (4.87x), and 243,716 against 49,876 in run 2 (4.89x), primarily because it sends five full-document prompts per question.
5. Q-17 reached the five-round limit in run 1 while computing water cost per resident; it made repeated retrieval requests and used the wrong megalitre-to-cubic-metre multiplier. In run 2 Q-07 and Q-20 also reached the limit, so Q-17 was tied for the maximum.
6. For 100,000 documents, I would replace a full scan with a search index or retrieval service, filter by document metadata/version, and rank a small set of relevant passages. I would retain source IDs, archived-status filtering, and correction precedence.
7. `calculate` parses an AST and permits only numeric constants, unary signs, and `+`, `-`, `*`, `/`; it rejects calls, attributes, powers, oversized expressions, division by zero, and non-finite or excessive results. The model can still select incorrect facts, units, or an incorrect expression, so safe execution does not guarantee a correct answer.
8. Tools are most useful for multi-document questions that require combining figures, unit conversion, and arithmetic. They add less value when the answer is stated directly in a small prompt and no calculation or source verification is needed.

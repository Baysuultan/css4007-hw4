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

<!-- what changed in your plan, and why. "None" is an answer too. -->

### B2 — Tests

```text
<!-- pytest output -->
```

### B3 — The loop

- Round limit, and why:
- Where the logs are:
- Real Q-09 conversation compared with my A3 version, what is different:

### B4 — Three strategies

**What I kept the same:**

<!-- model, temperature, k, prompts, answer format, anything else -->

**My rule for a correct answer** (written before the first full run):

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

| Question | Calls (your description) | Calls (vague) | Answer (yours) | Answer (vague) |
|---|---:|---:|---|---|
| | | | | |

### C2 — Three mistakes explained

### C3 — Which strategy I would use, and what would change it

### C4 — How sure I can be

### Final questions

1.
2.
3.
4.
5.
6.
7.
8.

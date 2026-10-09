---
name: token-budget-advisor
description: Offers the user an informed choice about how much response depth to consume before answering. Estimates prompt input tokens, calculates multiplier ranges, and formats responses across 4 depth levels (25%, 50%, 75%, 100%).
version: 2.0.0
triggers:
  - "token budget"
  - "token count"
  - "token usage"
  - "response length"
  - "answer depth"
  - "short version"
  - "brief answer"
  - "detailed answer"
  - "exhaustive answer"
  - "al 25%"
  - "al 50%"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Token Budget Advisor (TBA)

Intercept the response flow to offer the user an explicit choice about response depth **before** answering, managing context economics and attention entropy.

## When to Use

- User wants to control how long or detailed a response is
- User mentions tokens, budget, depth, or response length
- User says "short version", "tldr", "brief", "al 25%", "exhaustive", etc.
- Any time the user asks to choose depth or detail level upfront

**Do not trigger when:**
- The user has already set a depth level in the current session (maintain it silently)
- The request is trivially a one-word or one-line answer
- "token" refers to an auth token, session token, or payment token rather than LLM token budget

---

## How It Works

### Step 1 - Estimate Input Tokens

Estimate the prompt's input token count mentally using standard context-budget heuristics:
- **Prose:** `words × 1.3`
- **Code-heavy or mixed code blocks:** `chars / 4`

For mixed content, use the dominant content type to compute the heuristic estimate.

---

### Step 2 - Estimate Response Size by Complexity

Classify prompt complexity, then apply the multiplier range to compute the response window:

| Complexity | Multiplier Range | Example Prompts |
| :--- | :--- | :--- |
| **Simple** | 3× - 8× | "What is X?", yes/no, single fact |
| **Medium** | 8× - 20× | "How does X work?", explain flow |
| **Medium-High** | 10× - 25× | Code implementation request with context |
| **Complex** | 15× - 40× | Multi-part analysis, architectural comparisons, root-cause trace |
| **Creative** | 10× - 30× | Essays, narrative writing, deep synthesis |

**Response window:** `input_tokens × mult_min` to `input_tokens × mult_max` (bounded by model output limits).

---

### Step 3 - Present Depth Options

Present this concise block **before** answering, substituting the actual estimated numbers:

```
Analyzing your prompt...

Input: ~[N] tokens  |  Type: [type]  |  Complexity: [level]  |  Language: [lang]

Choose your depth level:

[1] Essential   (25%)  ->  ~[tokens]   Direct answer only, no preamble
[2] Moderate    (50%)  ->  ~[tokens]   Answer + context + 1 example
[3] Detailed    (75%)  ->  ~[tokens]   Full answer with alternatives
[4] Exhaustive (100%)  ->  ~[tokens]   Everything, no limits

Which level? (1-4 or say "25% depth", "50% depth", "75% depth", "100% depth")

Precision: heuristic estimate ~85-90% accuracy (±15%).
```

**Level Token Formulas:**
- **25% Essential:** `min + (max - min) × 0.25`
- **50% Moderate:** `min + (max - min) × 0.50`
- **75% Detailed:** `min + (max - min) × 0.75`
- **100% Exhaustive:** `max`

---

### Step 4 - Respond at the Chosen Level

| Level | Target Length | Include | Omit |
| :--- | :--- | :--- | :--- |
| **25% Essential** | 2-4 sentences max | Direct answer, key conclusion | Context, examples, nuance, alternatives |
| **50% Moderate** | 1-3 paragraphs | Answer + necessary context + 1 example | Deep edge cases, exhaustive references |
| **75% Detailed** | Structured response | Multiple examples, pros/cons, alternatives | Extreme edge cases, verbose boilerplate |
| **100% Exhaustive** | Unrestricted | Full analysis, complete code, edge cases | Nothing |

---

## Shortcuts - Skip the Question

If the user already signals a level in their prompt, respond at that level immediately without asking:

| User Input | Level Applied |
| :--- | :--- |
| `"1"` / `"25% depth"` / `"short version"` / `"brief answer"` / `"tldr"` | 25% Essential |
| `"2"` / `"50% depth"` / `"moderate depth"` / `"balanced answer"` | 50% Moderate |
| `"3"` / `"75% depth"` / `"detailed answer"` / `"thorough answer"` | 75% Detailed |
| `"4"` / `"100% depth"` / `"exhaustive answer"` / `"full deep dive"` | 100% Exhaustive |

If the user set a level earlier in the session, **maintain it silently** for subsequent responses unless they modify it.

---

## Precision Note

This skill uses heuristic estimation - no external tokenizer is invoked. Accuracy is ~85-90% with a variance of ±15%.

---

## Examples

### Triggers
- "Give me the short version first."
- "How many tokens will your answer use?"
- "Respond at 50% depth."
- "I want the exhaustive answer, not just a summary."
- "Dame la versión corta y luego la detallada."

### Does Not Trigger
- "What is a JWT token?"
- "The checkout flow uses a Stripe payment token."
- "Is this test passing?"
- "Complete the refactor."
- Follow-up turns after a depth level was already established for the session.

---

## Integration with Kortext Context Economics

When working within long sessions:
- For high-volume tool outputs, delegate tasks to subagents (`kortext-task-runner`) to isolate token usage.
- When conversation transcripts approach the context ceiling (40,000+ tokens), invoke `memory_session_handoff` to persist task state and start with a fresh context window.

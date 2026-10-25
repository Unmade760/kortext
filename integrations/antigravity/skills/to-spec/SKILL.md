---
name: to-spec
description: Use when synthesizing ambiguous requirements into engineering specs, brainstorming design options without interview fatigue, recording Architecture Decision Records (ADRs), or generating /teamwork-preview Phase 1 prompt artifacts.
---

# To-Spec: Requirements Synthesis, ADRs & Teamwork Prompt Artifacts

Transforms conversational intent or ambiguous feature requests into AST-grounded engineering specifications, Architecture Decision Records (ADRs), and `/teamwork-preview` Phase 1 prompt artifacts without interview fatigue.

## 1. Anti-Interview Fatigue: Propose First, Inquire Sparingly

1. **Ground in Codebase First (`<10ms`)**: Before asking the user any question, run `seek_symbol` and `trace_symbol_impact` to inspect existing schemas, dataclasses, protocols, and caller patterns.
2. **Never Ask Open-Ended Blank Questions**:
   - **FAIL**: *"What database schema and error handling do you want?"*
   - **PASS**: *"I propose a frozen Pydantic model persisted in FalkorDB with a TTL index, matching `SessionRegistry`. Should we proceed with Option A (Bi-temporal supersession — recommended for zero-downtime auditability) or Option B (In-place soft delete)?"*
3. **Quarantine Questions to True Forks**: Only ask the human when a decision is **Hard to Reverse**, **Crosses Business Policy**, or **Carries Real Trade-Offs** (cap at $\le 3$ multiple-choice questions with stated recommendations).

## 2. Standard Engineering Specification Template (`docs/specs/SPEC-xxx.md`)

| Section | Required Contents | Quality Bar |
|---|---|---|
| **1. Problem & Outcome** | Context, concrete pain point, measurable definition of success | 3–5 concise bullets; zero fluff |
| **2. Design It Twice (Interface Comparison)** | Compare 2 radically different interface signatures (e.g., **Option A: Minimal Deep Module** hiding internal state vs. **Option B: Fine-Grained CRUD/Stepwise Protocol**) before locking the contract | Explicit trade-off table (caller cognitive load, token footprint, blast radius) |
| **3. Grounded Data Contracts** | Exact existing symbols (`[Symbol](file:///path#L10)`), frozen Pydantic/dataclass schemas, state transitions | Verified via `seek_symbol`; zero hallucinated types |
| **4. User Stories & Gherkin AC** | `As a <role>, I want <capability>, so that <value>` + deterministic `Given / When / Then` scenarios | Binary pass/fail criteria (exact latency, status codes, exception types) |
| **5. Edge Cases & NFRs** | Null/empty inputs, socket drop degradation, concurrency/immutability, parameterized Cypher/SQL | Explicit fallback behavior for every external dependency |
| **6. Three Testing Seams** | (1) Pure functional domain seam (`<10ms` zero-I/O unit tests), (2) Protocol/Adapter seam, (3) Exact `pytest` command | `>=80%` branch coverage target |

## 3. Architecture Decision Records (`docs/adr/NNNN-slug.md`)

Write an ADR whenever a decision is **(1) Hard to Reverse**, **(2) Surprising Without Context** (e.g., Sole Custodian lock rules), or **(3) The Result of a Real Trade-Off**. Skip ADRs for trivial implementation choices.

```markdown
# ADR-NNNN: [Decision Title]
- **Date**: YYYY-MM-DD | **Status**: proposed | accepted | superseded by ADR-XXXX
- **Domain Terms**: Canonical terms aligned with `GLOSSARY.md`
## Context
[2–4 sentences on technical forces, latency/memory bounds, and invariants]
## Decision
[1–3 sentences stating the committed approach using ubiquitous language]
## Alternatives Considered
- **Option A (Chosen)**: Pros / Cons
- **Option B (Rejected)**: Pros / Cons / **Why Not**: [Definitive rejection rationale]
## Consequences & Mitigations
- **Positive / Negative Trade-offs** and **Risk -> Guardrail** mappings
```

**Mandatory Dual Persistence for Accepted ADRs**:
```python
record_system_outcome(
    episode_name="ADR-NNNN: <Title>",
    content="<Decision summary, rejected alternative, and GLOSSARY.md terms>",
    category="decision",
)
```

## 4. Bridging into `/teamwork-preview` Phase 1 Prompt Artifacts

When a specification spans $\ge 3$ subsystems ($C \ge 7$) and is destined for multi-agent execution via `/teamwork-preview`, append a ready-to-approve **Phase 1 Prompt Artifact**:

1. **Exclusive File Ownership Matrix**: Run `manage_tasks(action="create", tasks=[...])` and `detect_file_overlaps` to assign disjoint `target_files` per worker (setting `recommended_workspace_mode="branch"` when 1-hop AST call-graph coupling exists).
2. **Integrity Mode Declaration**: Explicitly state `Integrity Mode: development | demo | benchmark` so `IntegrityModeAuditor` blocks `unittest.mock` or test-cheating in production modules.
3. **Independent Verification Gate**: Specify the exact `pytest` command and acceptance checks for the Critic, Challenger, and Success Auditor gates.

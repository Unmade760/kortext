# Security Policy

This document defines vulnerability reporting procedures, substrate security architecture, and defenses against memory injection attacks for Kortext.

---

## Supported Versions

| Version | Supported |
| :---    | :---      |
| `2.0.x` | Yes       |
| `< 2.0` | No        |

---

## Reporting a Vulnerability

Please do not disclose security vulnerabilities through public issue trackers. Report them privately to project maintainers:

1. Email the project maintainers with the subject `[SECURITY] Vulnerability in Kortext`.
2. Include:
   - A detailed description of the vulnerability and its potential security impact.
   - Minimal reproduction code, payload, or step-by-step instructions.
   - The affected subsystem (such as FastMCP transport, Cypher execution, AST parsing, or causal sanitization).
   - Any suggested remediations or mitigations.

Maintainers will acknowledge receipt within 48 hours and coordinate verification, patching, and disclosure.

---

## MINJA Causal Memory Defense

Kortext integrates dual-memory substrates (FalkorDB graph databases and Qdrant vector stores). To defend against Memory Injection Attacks (MINJA):

### 1. Causal Sanitization Pipeline
- All untrusted external text (web queries, API responses, third-party documents) must pass through the `CausalSanitizer` prior to vector embedding or graph ingestion.
- Sanitization neutralizes embedded prompt overrides, deceptive instructions, and covert system directive modifications.

### 2. Trust Level Anchoring
Memory payloads and graph nodes explicitly record cryptographic and structural trust boundaries:
- `trust_level="system"`: Immutable agent operating directives and system prompts.
- `trust_level="verified"`: Code symbols and relationships extracted deterministically via Tree-sitter AST parsers.
- `trust_level="untrusted"`: Dynamic external text, user inputs, and retrieved third-party content.

### 3. Indirect Injection Disarmament
- System prompt instructions hold absolute precedence over retrieved memory context.
- Retrieved chunks must never override core directives, escalate tool permissions, or execute unauthorized subprocess commands.

---

## FastMCP Sole Custodian Security Model

To prevent data corruption, process denial-of-service, and concurrency exploits:

- **Sole Custodianship**: The FastMCP server daemon (`kortext.server`) is the single, exclusive owner of on-disk vector stores (Qdrant) and key-value state (RocksDB).
- **Prohibition of Direct Embedded Clients**: Subagents, background sidecars, and external scripts must never instantiate `QdrantClient(path=...)` directly in embedded mode.
- **Lock Contention Defense**: Embedded Qdrant uses SQLite and RocksDB metadata stores that acquire exclusive advisory file locks (`LOCK_EX`). Direct client instantiation by secondary processes causes file lock errors (`sqlite3.OperationalError: database is locked`) and damages vector segments. All vector operations must route through FastMCP server tools.

---

## Database & Query Safety

### Mandatory Parameterized Cypher Queries
- All FalkorDB graph interactions must use parameterized Cypher queries with `$param` syntax.
- String interpolation or f-string concatenation into Cypher statements is strictly prohibited:

```python
# Secure: Parameterized query
query = "MATCH (s:Symbol {name: $name}) RETURN s"
client.query(query, {"name": symbol_name})

# Prohibited: String interpolation
query = f"MATCH (s:Symbol {{name: '{symbol_name}'}}) RETURN s"
```

---

## Local Socket & Loopback Confinement

- **IPC Confinement**: FalkorDB communicates locally over a Unix Domain Socket at `~/.kortext/run/falkordb.sock` or loopback TCP at `127.0.0.1:6379`.
- **No Unauthenticated Exposure**: Substrates bind to local interfaces only. They must never be exposed to public networks without an authenticated TLS reverse proxy.
- **FastMCP Stdio Transport Safety**: Server modules avoid raw stdout output to prevent corrupting stdio JSON-RPC protocol frames.
- **Safe Error Envelopes**: Error envelopes returned to agents must never reveal internal file paths, stack traces, or credential fragments.

---

## Secret Management

- **Zero Tolerance**: Never commit API keys, tokens, or credentials into source code or test fixtures.
- **Environment Isolation**: Load secrets exclusively via `.env` files. Ensure `.env` is listed in `.gitignore`.
- **Immediate Invalidation**: If an API credential is committed or exposed, revoke and rotate the secret immediately.

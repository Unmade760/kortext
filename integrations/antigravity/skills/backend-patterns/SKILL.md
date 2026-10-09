---
name: backend-patterns
description: Backend architecture patterns, API design, database optimization, caching, background jobs, graceful shutdown, health checks, and Kortext substrate resilience (Unix domain sockets with TCP fallback, Sole Custodian). Use when building or reviewing backend services, MCP servers, API endpoints, or database connectors.
version: 2.0.0
triggers:
  - "backend patterns"
  - "api design"
  - "repository pattern"
  - "service layer"
  - "caching strategy"
  - "substrate resilience"
  - "health probes"
  - "graceful shutdown"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Backend Development Patterns & Substrate Resilience

Backend architecture patterns, database optimizations, structured API contracts, and high-performance IPC patterns for scalable server-side applications and Kortext substrates.

## When to Activate

- Designing REST or GraphQL API endpoints or FastMCP tool interfaces
- Implementing repository, service, or controller layers
- Optimizing database queries (N+1 query prevention, indexing, connection pooling)
- Establishing IPC communication with embedded substrates (FalkorDB, Qdrant)
- Adding caching (Redis, in-memory, cache-aside)
- Setting up background jobs or async worker queues
- Structuring error handling, retries with exponential backoff, and validation
- Architecting health probes, liveness/readiness checks, or graceful shutdown hooks
- Enforcing Kortext Substrate Resilience invariants and Sole Custodian access

---

## Kortext Substrate Resilience & Invariant 3

Kortext components interact with local memory engines (FalkorDB graph database and Qdrant vector store). To guarantee maximum throughput and zero data corruption, backend components must adhere to **Invariant 3: Substrate Resilience**.

```
┌─────────────────────────────────────────────────────────────┐
│                 FastMCP Server (Sole Custodian)              │
│                     [kortext.server]                        │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
    Unix Domain Socket (IPC)        Embedded Storage Engine
  ~/.kortext/run/falkordb.sock          (Exclusive Locks)
    [Fallback: TCP 127.0.0.1:6379]             │
                │                             │
                ▼                             ▼
        ┌───────────────┐             ┌───────────────┐
        │   FalkorDB    │             │ Qdrant Vector │
        │  Graph Engine │             │  & RocksDB    │
        └───────────────┘             └───────────────┘
                ▲
                │ FastMCP Tool Protocol (NEVER direct file access)
        ┌───────┴───────────────┐
        │  Subagents & Workers  │
        │   (Leaf Executions)   │
        └───────────────────────┘
```

### 1. Unix Domain Socket with TCP Fallback (FalkorDB / Redis)

For local Redis/FalkorDB communication on Unix systems (macOS / Linux), Unix Domain Sockets bypass the OS network stack, avoiding TCP loopback overhead, packet fragmentation, and port exhaustion:

```python
# PASS: Resilient FalkorDB Connection with Socket-first & TCP Fallback
from pathlib import Path
import os
import redis

KORTEXT_HOME = Path(os.getenv("KORTEXT_HOME", Path.home() / ".kortext"))
DEFAULT_SOCKET = KORTEXT_HOME / "run" / "falkordb.sock"
FALKORDB_HOST = os.getenv("FALKORDB_HOST", "127.0.0.1")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))

class ResilientFalkorClient:
    def __init__(self, socket_path: Path = DEFAULT_SOCKET):
        self.socket_path = socket_path
        self._client: redis.Redis | None = None

    def get_connection(self) -> redis.Redis:
        """Returns active Redis client, prioritizing Unix domain socket."""
        if self._client is not None:
            return self._client

        # Attempt 1: Unix Domain Socket (Ultra-low latency IPC)
        if self.socket_path.is_socket():
            try:
                r = redis.Redis(
                    unix_socket_path=str(self.socket_path),
                    decode_responses=True,
                    socket_timeout=3.0,
                    socket_connect_timeout=2.0,
                )
                r.ping()
                self._client = r
                return self._client
            except (redis.ConnectionError, redis.TimeoutError):
                pass  # Fall through to TCP loopback

        # Attempt 2: TCP Loopback Endpoint
        self._client = redis.Redis(
            host=FALKORDB_HOST,
            port=FALKORDB_PORT,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=3.0,
        )
        self._client.ping()
        return self._client

    def execute_cypher(self, graph_name: str, query: str, attempts: int = 2) -> list:
        """Executes query with transparent reconnection on connection drop."""
        for attempt in range(attempts):
            try:
                conn = self.get_connection()
                return conn.execute_command("GRAPH.QUERY", graph_name, query)
            except (redis.ConnectionError, redis.TimeoutError):
                self._client = None  # Invalidate cached handle
                if attempt == attempts - 1:
                    raise
        return []
```

### 2. Sole Custodian Access Pattern (Qdrant & Storage)

Embedded vector engines like embedded Qdrant use SQLite and RocksDB under the hood, acquiring exclusive OS file locks on storage directories.

- **Mandate**: Only the primary FastMCP daemon (`kortext.server`) may instantiate `QdrantClient(path=...)`.
- **Anti-Pattern (FAIL)**: Subagents, test workers, or CLI hooks instantiating raw `QdrantClient(path="~/.kortext/qdrant")`. This triggers fatal `sqlite3.OperationalError: database is locked` or `RocksDB: Resource temporarily unavailable`.
- **Pattern (PASS)**: Subagents call FastMCP tools (`search_knowledge_and_memory`, `seek_symbol`, `record_system_outcome`) to delegate queries and writes through the single daemon custodian.

---

## API Design Patterns

### RESTful API Structure

```typescript
// PASS: Resource-based URLs
GET    /api/markets                 # List resources
GET    /api/markets/:id             # Get single resource
POST   /api/markets                 # Create resource
PUT    /api/markets/:id             # Replace resource
PATCH  /api/markets/:id             # Update resource
DELETE /api/markets/:id             # Delete resource

// PASS: Query parameters for filtering, sorting, pagination
GET /api/markets?status=active&sort=volume&limit=20&offset=0
```

### Repository Pattern

Abstract data access logic behind an explicit interface:

```typescript
interface MarketRepository {
  findAll(filters?: MarketFilters): Promise<Market[]>
  findById(id: string): Promise<Market | null>
  create(data: CreateMarketDto): Promise<Market>
  update(id: string, data: UpdateMarketDto): Promise<Market>
  delete(id: string): Promise<void>
}

class SupabaseMarketRepository implements MarketRepository {
  async findAll(filters?: MarketFilters): Promise<Market[]> {
    let query = supabase.from('markets').select('*')

    if (filters?.status) {
      query = query.eq('status', filters.status)
    }

    if (filters?.limit) {
      query = query.limit(filters.limit)
    }

    const { data, error } = await query

    if (error) throw new Error(error.message)
    return data
  }
}
```

### Service Layer Pattern

Keep business logic strictly separated from data access and HTTP transport:

```typescript
class MarketService {
  constructor(private marketRepo: MarketRepository) {}

  async searchMarkets(query: string, limit: number = 10): Promise<Market[]> {
    // 1. Business logic & domain computation
    const embedding = await generateEmbedding(query)
    const results = await this.vectorSearch(embedding, limit)

    // 2. Fetch full data via repository
    const markets = await this.marketRepo.findByIds(results.map(r => r.id))

    // 3. Sort by similarity score
    return markets.sort((a, b) => {
      const scoreA = results.find(r => r.id === a.id)?.score || 0
      const scoreB = results.find(r => r.id === b.id)?.score || 0
      return scoreA - scoreB
    })
  }

  private async vectorSearch(embedding: number[], limit: number) {
    // Vector search implementation
  }
}
```

### Middleware Pattern

```typescript
// Request/response processing pipeline
export function withAuth(handler: NextApiHandler): NextApiHandler {
  return async (req, res) => {
    const token = req.headers.authorization?.replace('Bearer ', '')

    if (!token) {
      return res.status(401).json({ error: 'Unauthorized' })
    }

    try {
      const user = await verifyToken(token)
      req.user = user
      return handler(req, res)
    } catch (error) {
      return res.status(401).json({ error: 'Invalid token' })
    }
  }
}
```

### Standard API Response Envelope

Every backend service or MCP tool must expose explicit, deterministic JSON envelopes.

```python
from typing import Generic, TypeVar, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable explanation")
    details: dict[str, Any] = Field(default_factory=dict)

class ApiResponse(BaseModel, Generic[T]):
    success: bool
    status: str = Field(..., description="'ok' | 'error'")
    data: T | None = None
    error: ErrorDetail | None = None

def success_response(data: T) -> str:
    return ApiResponse[T](success=True, status="ok", data=data).model_dump_json()

def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> str:
    return ApiResponse[None](
        success=False,
        status="error",
        error=ErrorDetail(code=code, message=message, details=details or {}),
    ).model_dump_json()
```

---

## Database Patterns

### Query Optimization

```typescript
// PASS: Select only needed columns
const { data } = await supabase
  .from('markets')
  .select('id, name, status, volume')
  .eq('status', 'active')
  .order('volume', { ascending: false })
  .limit(10)

// FAIL: Select everything
const { data } = await supabase
  .from('markets')
  .select('*')
```

### N+1 Query Prevention

```typescript
// FAIL: N+1 query problem
const markets = await getMarkets()
for (const market of markets) {
  market.creator = await getUser(market.creator_id)  // N queries
}

// PASS: Batch fetch (1 query)
const markets = await getMarkets()
const creatorIds = markets.map(m => m.creator_id)
const creators = await getUsers(creatorIds)
const creatorMap = new Map(creators.map(c => [c.id, c]))

markets.forEach(market => {
  market.creator = creatorMap.get(market.creator_id)
})
```

### Transaction Pattern

```typescript
async function createMarketWithPosition(
  marketData: CreateMarketDto,
  positionData: CreatePositionDto
) {
  const { data, error } = await supabase.rpc('create_market_with_position', {
    market_data: marketData,
    position_data: positionData
  })

  if (error) throw new Error('Transaction failed')
  return data
}
```

```sql
CREATE OR REPLACE FUNCTION create_market_with_position(
  market_data jsonb,
  position_data jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO markets VALUES (market_data);
  INSERT INTO positions VALUES (position_data);
  RETURN jsonb_build_object('success', true);
EXCEPTION
  WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'error', SQLERRM);
END;
$$;
```

---

## Caching Strategies

### Redis Caching Layer

```typescript
class CachedMarketRepository implements MarketRepository {
  constructor(
    private baseRepo: MarketRepository,
    private redis: RedisClient
  ) {}

  async findById(id: string): Promise<Market | null> {
    const cached = await this.redis.get(`market:${id}`)
    if (cached) {
      return JSON.parse(cached)
    }

    const market = await this.baseRepo.findById(id)
    if (market) {
      await this.redis.setex(`market:${id}`, 300, JSON.stringify(market))
    }
    return market
  }

  async invalidateCache(id: string): Promise<void> {
    await this.redis.del(`market:${id}`)
  }
}
```

### Cache-Aside Pattern

```typescript
async function getMarketWithCache(id: string): Promise<Market> {
  const cacheKey = `market:${id}`

  const cached = await redis.get(cacheKey)
  if (cached) return JSON.parse(cached)

  const market = await db.markets.findUnique({ where: { id } })
  if (!market) throw new Error('Market not found')

  await redis.setex(cacheKey, 300, JSON.stringify(market))
  return market
}
```

---

## Error Handling Patterns

### Centralized Error Handler

```typescript
class ApiError extends Error {
  constructor(
    public statusCode: number,
    public message: string,
    public isOperational = true
  ) {
    super(message)
    Object.setPrototypeOf(this, ApiError.prototype)
  }
}

export function errorHandler(error: unknown, req: Request): Response {
  if (error instanceof ApiError) {
    return NextResponse.json({
      success: false,
      error: error.message
    }, { status: error.statusCode })
  }

  if (error instanceof z.ZodError) {
    return NextResponse.json({
      success: false,
      error: 'Validation failed',
      details: error.issues
    }, { status: 400 })
  }

  console.error('Unexpected error:', error)
  return NextResponse.json({
    success: false,
    error: 'Internal server error'
  }, { status: 500 })
}
```

### Retries with Exponential Backoff & Jitter

```python
import asyncio
import random
import logging

logger = logging.getLogger("backend.retry")

async def retry_with_jitter(
    coro_fn,
    max_retries: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
):
    """Executes coroutine with truncated exponential backoff and full jitter."""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except (ConnectionError, TimeoutError) as e:
            if attempt == max_retries - 1:
                logger.error(f"Exhausted retries ({max_retries}): {e}")
                raise
            delay = random.uniform(0, min(max_delay, base_delay * (2 ** attempt)))
            logger.warning(f"Attempt {attempt + 1} failed ({e}). Retrying in {delay:.3f}s...")
            await asyncio.sleep(delay)
```

---

## Authentication & Authorization

### JWT Token Validation

```typescript
import jwt from 'jsonwebtoken'

interface JWTPayload {
  userId: string
  email: string
  role: 'admin' | 'user'
}

export function verifyToken(token: string): JWTPayload {
  try {
    return jwt.verify(token, process.env.JWT_SECRET!) as JWTPayload
  } catch (error) {
    throw new ApiError(401, 'Invalid token')
  }
}

export async function requireAuth(request: Request) {
  const token = request.headers.get('authorization')?.replace('Bearer ', '')
  if (!token) throw new ApiError(401, 'Missing authorization token')
  return verifyToken(token)
}
```

### Role-Based Access Control (RBAC)

```typescript
type Permission = 'read' | 'write' | 'delete' | 'admin'

interface User {
  id: string
  role: 'admin' | 'moderator' | 'user'
}

const rolePermissions: Record<User['role'], Permission[]> = {
  admin: ['read', 'write', 'delete', 'admin'],
  moderator: ['read', 'write', 'delete'],
  user: ['read', 'write']
}

export function hasPermission(user: User, permission: Permission): boolean {
  return rolePermissions[user.role].includes(permission)
}

export function requirePermission(permission: Permission) {
  return (handler: (request: Request, user: User) => Promise<Response>) => {
    return async (request: Request) => {
      const user = await requireAuth(request)
      if (!hasPermission(user, permission)) {
        throw new ApiError(403, 'Insufficient permissions')
      }
      return handler(request, user)
    }
  }
}
```

---

## Background Jobs & Queues

```typescript
class JobQueue<T> {
  private queue: T[] = []
  private processing = false

  async add(job: T): Promise<void> {
    this.queue.push(job)
    if (!this.processing) {
      this.process()
    }
  }

  private async process(): Promise<void> {
    this.processing = true
    while (this.queue.length > 0) {
      const job = this.queue.shift()!
      try {
        await this.execute(job)
      } catch (error) {
        console.error('Job failed:', error)
      }
    }
    this.processing = false
  }

  private async execute(job: T): Promise<void> {
    // Job execution logic
  }
}
```

---

## Health Probes & Dual-Tier Readiness

Backend daemons must provide two distinct probe endpoints:
1. **Liveness Probe**: Confirms the process is running and the event loop is cycling.
2. **Readiness Probe**: Confirms backing substrates (FalkorDB socket, Qdrant vectors, LLM runner) are responsive.

```python
from pydantic import BaseModel

class SubstrateHealth(BaseModel):
    name: str
    status: str  # "healthy" | "degraded" | "unreachable"
    latency_ms: float
    details: str | None = None

class HealthReport(BaseModel):
    status: str  # "healthy" | "unhealthy"
    substrates: list[SubstrateHealth]

async def check_kortext_health() -> HealthReport:
    results: list[SubstrateHealth] = []
    results.append(await probe_falkordb())
    results.append(await probe_qdrant())
    overall = "healthy" if all(s.status == "healthy" for s in results) else "unhealthy"
    return HealthReport(status=overall, substrates=results)
```

---

## Graceful Shutdown & Resource Cleanup

Daemons must register signal handlers to release IPC sockets, flush write-ahead logs, and finish in-flight requests:

```python
import asyncio
import signal
import sys
from pathlib import Path

class DaemonLifecycleManager:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.is_shutting_down = False

    def setup_signal_handlers(self, loop: asyncio.AbstractEventLoop):
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))

    async def shutdown(self, sig: signal.Signals):
        if self.is_shutting_down:
            return
        self.is_shutting_down = True
        logger.info(f"Received signal {sig.name}. Initiating graceful shutdown...")

        await self.drain_queues(timeout=5.0)

        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
                logger.info(f"Removed socket file: {self.socket_path}")
            except Exception as e:
                logger.warning(f"Error unlinking socket: {e}")

        logger.info("Shutdown complete.")
        sys.exit(0)

    async def drain_queues(self, timeout: float):
        await asyncio.sleep(0.1)
```

---

## Structured Logging

```typescript
interface LogContext {
  userId?: string
  requestId?: string
  method?: string
  path?: string
  [key: string]: unknown
}

class Logger {
  log(level: 'info' | 'warn' | 'error', message: string, context?: LogContext) {
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...context
    }
    console.log(JSON.stringify(entry))
  }

  info(message: string, context?: LogContext) { this.log('info', message, context) }
  warn(message: string, context?: LogContext) { this.log('warn', message, context) }
  error(message: string, error: Error, context?: LogContext) {
    this.log('error', message, { ...context, error: error.message, stack: error.stack })
  }
}
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Failure Mode | Correct Pattern |
| :--- | :--- | :--- |
| **Bypassing Sole Custodian** | `sqlite3.OperationalError: database is locked` or RocksDB conflict | Route all vector/storage writes through the primary FastMCP daemon. |
| **Hardcoding TCP Only** | Unnecessary latency; failure when port 6379 blocked | Check Unix domain socket first with TCP fallback. |
| **Silent Error Swallowing** | Failures mask bugs; caller receives corrupt state | Return explicit `ApiResponse` error structures with machine-readable codes. |
| **N+1 Query Cascades** | Multiplies database load by N | Batch fetch associated records with single query. |
| **Missing Request Timeouts** | Zombie connections hang worker pool | Wrap every remote/IPC operation in explicit timeouts. |
| **Unlinked Stale Sockets** | Daemon restart fails with `Address already in use` | Clean up socket path during graceful shutdown or verify validity on startup. |

---
name: database-migrations
description: Database migration best practices for schema changes, data migrations, rollbacks, and zero-downtime deployments across PostgreSQL, MySQL, ORMs (Prisma, Drizzle, Kysely, Django, golang-migrate), FalkorDB graph schemas, and Qdrant vector payload indexing.
version: 2.0.0
triggers:
  - "database migrations"
  - "schema change"
  - "zero downtime migration"
  - "expand and contract"
  - "falkordb schema"
  - "qdrant payload index"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Database Migration Patterns & Substrate Schema Evolution

Safe, reversible database schema changes, zero-downtime deployments, and substrate schema evolution for production systems.

## When to Activate

- Creating or altering relational database tables or graph schemas
- Adding, removing, or renaming columns, properties, or indexes
- Running data backfills or batch transformations
- Planning zero-downtime expand-and-contract migrations
- Updating FalkorDB Cypher graph property schemas or edge types
- Managing Qdrant vector payload indexes or embedding dimension upgrades
- Setting up migration tooling for a new project or service

---

## Core Principles

1. **Every change is a migration** - never alter production databases or schemas manually.
2. **Migrations are forward-only in production** - rollbacks execute new forward repair migrations.
3. **Schema and data migrations are separate** - never mix DDL (structural changes) and DML (data updates) in one transaction.
4. **Test migrations against production-sized data** - a migration that works on 100 rows can lock or OOM on 10 million rows.
5. **Migrations are immutable once deployed** - never edit a migration file that has already run in production.
6. **Zero-downtime expand-and-contract** - expand with new fields, dual-write, backfill, switchover, then contract.

---

## Migration Safety Checklist

Before applying any migration:

- [ ] Migration has both UP and DOWN (or is explicitly marked irreversible)
- [ ] No full table locks on large tables (use concurrent operations)
- [ ] New columns or graph properties have defaults or are nullable (never add `NOT NULL` without default)
- [ ] Indexes created concurrently (`CREATE INDEX CONCURRENTLY` in Postgres; idempotent in Cypher; `wait=False` in Qdrant)
- [ ] Data backfill is a separate migration from schema change
- [ ] Tested against a copy of production data
- [ ] Rollback and disaster recovery plan documented (snapshots verified)

---

## PostgreSQL & Relational Patterns

### Adding a Column Safely

```sql
-- GOOD: Nullable column, no lock
ALTER TABLE users ADD COLUMN avatar_url TEXT;

-- GOOD: Column with default (Postgres 11+ is instant, metadata-only change)
ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;

-- BAD: NOT NULL without default on existing table (requires full rewrite & lock)
ALTER TABLE users ADD COLUMN role TEXT NOT NULL;
```

### Adding an Index Without Downtime

```sql
-- BAD: Blocks writes on large tables
CREATE INDEX idx_users_email ON users (email);

-- GOOD: Non-blocking, allows concurrent writes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email ON users (email);

-- Note: CONCURRENTLY cannot run inside an explicit transaction block
```

### Renaming a Column (Zero-Downtime)

Never rename directly in production. Use the expand-contract pattern:

```sql
-- Step 1: Add new column (migration 001)
ALTER TABLE users ADD COLUMN display_name TEXT;

-- Step 2: Backfill data (migration 002, data migration)
UPDATE users SET display_name = username WHERE display_name IS NULL;

-- Step 3: Update application code to read/write both columns
-- Deploy application changes

-- Step 4: Stop writing to old column, drop it (migration 003)
ALTER TABLE users DROP COLUMN username;
```

### Removing a Column Safely

```sql
-- Step 1: Remove all application references to the column
-- Step 2: Deploy application without the column reference
-- Step 3: Drop column in next migration
ALTER TABLE orders DROP COLUMN legacy_status;
```

### Large Data Migrations (Batched Updates)

```sql
-- BAD: Updates all rows in one transaction (locks table and blows up WAL)
UPDATE users SET normalized_email = LOWER(email);

-- GOOD: Batch update with progress
DO $$
DECLARE
  batch_size INT := 10000;
  rows_updated INT;
BEGIN
  LOOP
    UPDATE users
    SET normalized_email = LOWER(email)
    WHERE id IN (
      SELECT id FROM users
      WHERE normalized_email IS NULL
      LIMIT batch_size
      FOR UPDATE SKIP LOCKED
    );
    GET DIAGNOSTICS rows_updated = ROW_COUNT;
    RAISE NOTICE 'Updated % rows', rows_updated;
    EXIT WHEN rows_updated = 0;
    COMMIT;
  END LOOP;
END $$;
```

---

## ORM-Specific Migration Patterns

### Prisma (TypeScript / Node.js)

```bash
# Create migration from schema changes
npx prisma migrate dev --name add_user_avatar

# Apply pending migrations in production
npx prisma migrate deploy

# Create empty migration for custom SQL (concurrent indexes, backfills)
npx prisma migrate dev --create-only --name add_email_index
```

```sql
-- migrations/20240115_add_email_index/migration.sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email ON users (email);
```

### Drizzle (TypeScript / Node.js)

```bash
# Generate migration from schema changes
npx drizzle-kit generate

# Apply migrations
npx drizzle-kit migrate
```

```typescript
import { pgTable, text, timestamp, uuid, boolean } from "drizzle-orm/pg-core";

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  email: text("email").notNull().unique(),
  name: text("name"),
  isActive: boolean("is_active").notNull().default(true),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});
```

### Kysely (TypeScript / Node.js)

```typescript
// migrations/2024_01_15_001_create_user_profile.ts
import { type Kysely, sql } from 'kysely'

// IMPORTANT: Always use Kysely<any>, not your typed DB interface.
// Migrations are frozen in time and must not depend on current schema types.
export async function up(db: Kysely<any>): Promise<void> {
  await db.schema
    .createTable('user_profile')
    .addColumn('id', 'serial', (col) => col.primaryKey())
    .addColumn('email', 'varchar(255)', (col) => col.notNull().unique())
    .addColumn('avatar_url', 'text')
    .addColumn('created_at', 'timestamp', (col) =>
      col.defaultTo(sql`now()`).notNull()
    )
    .execute()

  await db.schema
    .createIndex('idx_user_profile_avatar')
    .on('user_profile')
    .column('avatar_url')
    .execute()
}

export async function down(db: Kysely<any>): Promise<void> {
  await db.schema.dropTable('user_profile').execute()
}
```

### Django (Python)

```bash
# Generate migration from model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Generate empty migration for data migrations
python manage.py makemigrations --empty app_name -n backfill_display_names
```

```python
# Data migration in Django
from django.db import migrations

def backfill_display_names(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    batch_size = 5000
    users = User.objects.filter(display_name="")
    while users.exists():
        batch = list(users[:batch_size])
        for user in batch:
            user.display_name = user.username
        User.objects.bulk_update(batch, ["display_name"], batch_size=batch_size)

def reverse_backfill(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_add_display_name")]
    operations = [
        migrations.RunPython(backfill_display_names, reverse_backfill),
    ]
```

### golang-migrate (Go)

```bash
# Create migration pair
migrate create -ext sql -dir migrations -seq add_user_avatar

# Apply pending migrations
migrate -path migrations -database "$DATABASE_URL" up

# Rollback last migration
migrate -path migrations -database "$DATABASE_URL" down 1
```

---

## Kortext FalkorDB Graph Schema Evolution

FalkorDB Cypher property graphs do not require rigid table definitions, but schema indexes, relationship types, and node properties must be governed idempotently.

### 1. Idempotent B-Tree Indexing

```python
class FalkorDBSchemaManager:
    def __init__(self, client):
        self.client = client
        self.verified_indexes: set[tuple[str, str, str]] = set()

    def ensure_indexes(self, graph_name: str, indexes: list[tuple[str, str]]):
        for label, prop in indexes:
            key = (graph_name, label, prop)
            if key in self.verified_indexes:
                continue
            cypher = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
            try:
                self.client.execute_command("GRAPH.QUERY", graph_name, cypher)
            except Exception:
                pass  # Index already exists
            self.verified_indexes.add(key)
```

### 2. Backward-Compatible Cypher Queries

When reading properties undergoing migration, use Cypher's `coalesce()` function:

```cypher
MATCH (s:Symbol {name: $symbol_name})
RETURN s.name AS name,
       coalesce(s.fqn, s.name) AS fqn,
       coalesce(s.complexity, 1) AS complexity
```

### 3. Batched Graph Data Migrations

```python
def backfill_symbol_fqn(client, graph_name: str, batch_size: int = 1000):
    query = f"""
    MATCH (s:Symbol)
    WHERE s.fqn IS NULL
    WITH s LIMIT {batch_size}
    SET s.fqn = s.module + '.' + s.name
    RETURN count(s) AS updated_count
    """
    total = 0
    while True:
        res = client.execute_command("GRAPH.QUERY", graph_name, query)
        updated = int(res[1][0][0]) if res and len(res) > 1 and res[1] else 0
        total += updated
        if updated == 0:
            break
```

### 4. Edge Relationship Evolution

```cypher
// Step 1: Expand - Create new relationship type preserving existing properties
MATCH (a:Symbol)-[old:CALLS]->(b:Symbol)
WHERE NOT (a)-[:INVOKES]->(b)
WITH a, b, old LIMIT 1000
MERGE (a)-[new:INVOKES]->(b)
SET new = properties(old)
RETURN count(new);

// Step 2: Contract - Delete legacy relationships once application switchover completes
MATCH (a:Symbol)-[old:CALLS]->(b:Symbol)
WITH old LIMIT 1000
DELETE old
RETURN count(old);
```

---

## Kortext Qdrant Vector Payload Indexing & Blue-Green Migration

### 1. Non-Blocking Payload Index Creation

```python
from qdrant_client import QdrantClient
from qdrant_client.http import models

def ensure_vector_payload_indexes(client: QdrantClient, collection_name: str):
    payload_indexes = [
        ("file_path", models.PayloadSchemaType.KEYWORD),
        ("workspace", models.PayloadSchemaType.KEYWORD),
        ("line_start", models.PayloadSchemaType.INTEGER),
        ("is_active", models.PayloadSchemaType.BOOL),
    ]

    for field_name, field_type in payload_indexes:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_type,
            wait=False,  # Run in background to prevent hanging client
        )
```

### 2. Blue-Green Collection Migration (Embedding Upgrades)

When upgrading vector dimensions or embedding models, collections cannot be altered in-place:

```python
def blue_green_collection_swap(client: QdrantClient, alias_name: str, new_collection: str):
    """Atomically points production alias to the new vector collection."""
    client.update_collection_aliases(
        change_aliases_operations=[
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=new_collection,
                    alias_name=alias_name,
                )
            )
        ]
    )
```

---

## Zero-Downtime Migration Strategy

```
Phase 1: EXPAND
  - Add new column/table/property (nullable or with default)
  - Deploy: app writes to BOTH old and new
  - Backfill existing data in batches

Phase 2: MIGRATE
  - Deploy: app reads from NEW, writes to BOTH
  - Verify data consistency and query performance

Phase 3: CONTRACT
  - Deploy: app only uses NEW
  - Drop old column/table/edge in separate migration
```

---

## Anti-Patterns

| Anti-Pattern | Why It Fails | Better Approach |
| :--- | :--- | :--- |
| **Manual SQL/Cypher in prod** | No audit trail, unrepeatable | Always use versioned migration scripts |
| **Editing deployed migrations** | Causes schema drift between environments | Create new forward migration instead |
| **NOT NULL without default** | Locks table, rewrites all rows | Add nullable, backfill, then add constraint |
| **Inline index on large table** | Blocks writes during build | Use `CREATE INDEX CONCURRENTLY` |
| **Schema + data in one migration** | Long transactions, difficult rollback | Split into separate schema and data passes |
| **Unbounded Cypher Updates** | `MATCH (n) SET ...` OOMs and freezes Redis thread | Batch mutations with `LIMIT` loop |
| **In-place vector dimension change**| Vector dimensionality is immutable in Qdrant | Blue-green collection swap via aliases |

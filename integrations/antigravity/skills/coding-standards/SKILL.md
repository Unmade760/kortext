---
name: coding-standards
description: Baseline cross-project coding conventions for naming, readability, immutability, error handling, and code-quality review. Use when writing or reviewing code quality with general or cross-language scope.
version: 2.0.0
triggers:
  - "coding standards"
  - "code quality"
  - "naming conventions"
  - "clean code"
  - "code style"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Coding Standards & Best Practices

Baseline coding conventions and quality principles applicable across projects and languages.

## When to Activate

- Starting a new project, service, or module
- Reviewing code for quality, maintainability, and cognitive complexity
- Refactoring existing code to adhere to clean code standards
- Enforcing naming, formatting, or structural consistency
- Setting up linting, formatting, or type-checking rules
- Onboarding contributors to codebase conventions

---

## Scope Boundaries

Activate this skill for:
- Descriptive, unambiguous naming
- Immutability by default
- Readability, KISS, DRY, and YAGNI enforcement
- Structured error-handling expectations and code-smell elimination

For deep language/framework specifics:
- Use `python-patterns` for Python 3.10+, typing, Pydantic, and FastMCP
- Use `backend-patterns` or `api-design` for API contracts, database queries, and caching
- Use `security-review` for authorization, secrets, and injection defenses

---

## Code Quality Principles

### 1. Readability First
- Code is read far more often than it is written.
- Favor clear, descriptive variable and function names over clever abbreviations.
- Self-documenting code is preferred over explanatory comments.
- Maintain consistent indentation and formatting.

### 2. KISS (Keep It Simple, Stupid)
- Choose the simplest solution that reliably solves the problem.
- Avoid speculative generality and over-engineered abstractions.
- Easy to reason about > clever code.

### 3. DRY (Don't Repeat Yourself)
- Extract common domain logic into reusable functions or utilities.
- Avoid copy-paste programming across modules.
- Balance DRY with coupling: duplication is cheaper than the wrong abstraction.

### 4. YAGNI (You Aren't Gonna Need It)
- Do not author features, endpoints, or parameters until they are actually required.
- Refactor and generalize when the second or third use case appears, not before.

---

## Naming & Style Conventions

### Variable Naming

```typescript
// PASS: Descriptive names
const searchMarketQuery = 'election'
const isUserAuthenticated = true
const totalRevenue = 1000

// FAIL: Unclear or cryptic names
const q = 'election'
const flag = true
const x = 1000
```

### Function Naming

```typescript
// PASS: Verb-noun pattern
async function fetchMarketData(marketId: string) { }
function calculateSimilarity(a: number[], b: number[]) { }
function isValidEmail(email: string): boolean { }

// FAIL: Unclear or noun-only
async function market(id: string) { }
function similarity(a, b) { }
function email(e) { }
```

### Immutability Pattern (CRITICAL)

Avoid in-place mutations of shared state or function arguments:

```typescript
// PASS: Immutability via spread operator
const updatedUser = {
  ...user,
  name: 'New Name'
}

const updatedItems = [...items, newItem]

// FAIL: Direct mutation of state or objects
user.name = 'New Name'
items.push(newItem)
```

---

## Error Handling Standards

```typescript
// PASS: Comprehensive error handling with context
async function fetchData(url: string) {
  try {
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Fetch failed for URL:', url, error)
    throw new Error('Failed to fetch data')
  }
}

// FAIL: Silent failure or unhandled rejection
async function fetchData(url: string) {
  const response = await fetch(url)
  return response.json()
}
```

---

## Async Execution Best Practices

```typescript
// PASS: Parallel execution when tasks are independent
const [users, markets, stats] = await Promise.all([
  fetchUsers(),
  fetchMarkets(),
  fetchStats()
])

// FAIL: Sequential execution when independent
const users = await fetchUsers()
const markets = await fetchMarkets()
const stats = await fetchStats()
```

---

## Type Safety

```typescript
// PASS: Explicit, typed contracts
interface Market {
  id: string
  name: string
  status: 'active' | 'resolved' | 'closed'
  created_at: Date
}

function getMarket(id: string): Promise<Market> { ... }

// FAIL: Bypassing type safety with 'any'
function getMarket(id: any): Promise<any> { ... }
```

---

## React & Frontend Standards

### Component Structure
```typescript
interface ButtonProps {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  variant?: 'primary' | 'secondary'
}

export function Button({
  children,
  onClick,
  disabled = false,
  variant = 'primary'
}: ButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`btn btn-${variant}`}
    >
      {children}
    </button>
  )
}
```

### State Management & Functional Updates
```typescript
// PASS: Functional update prevents stale state closures
setCount(prev => prev + 1)

// FAIL: Direct state reference can be stale in async handlers
setCount(count + 1)
```

### Conditional Rendering
```typescript
// PASS: Clear conditional rendering
{isLoading && <Spinner />}
{error && <ErrorMessage error={error} />}
{data && <DataDisplay data={data} />}

// FAIL: Nested ternary soup
{isLoading ? <Spinner /> : error ? <ErrorMessage error={error} /> : data ? <DataDisplay data={data} /> : null}
```

---

## Comments & Documentation

```typescript
// PASS: Explain the WHY (rationale and non-obvious constraints)
// Exponential backoff with jitter prevents thundering herd on backend recovery
const delay = Math.min(1000 * Math.pow(2, retryCount) + Math.random() * 200, 30000)

// Deliberately using in-place buffer mutation here for performance on 10MB chunk
buffer.copy(target, targetStart)

// FAIL: Stating the obvious
// Increment count by 1
count++
```

---

## Testing Standards (AAA Pattern)

```typescript
test('calculates cosine similarity correctly', () => {
  // Arrange
  const vector1 = [1, 0, 0]
  const vector2 = [0, 1, 0]

  // Act
  const similarity = calculateCosineSimilarity(vector1, vector2)

  // Assert
  expect(similarity).toBe(0)
})
```

---

## Code Smell Detection

Watch for and eliminate these common anti-patterns:

### 1. Long Functions
- **Smell:** Functions exceeding 40-50 lines.
- **Fix:** Decompose into cohesive helper functions with single responsibilities.

### 2. Deep Nesting
- **Smell:** 4+ levels of nested `if`, `for`, or callback blocks.
- **Fix:** Use guard clauses and early returns.

```typescript
// PASS: Guard clauses and early returns
if (!user) return
if (!user.isActive) return
if (!hasPermission) return

// Execute core logic cleanly
processUser(user)
```

### 3. Magic Numbers & Strings
- **Smell:** Unexplained literal numbers or strings embedded in expressions.
- **Fix:** Extract to named constants:

```typescript
const MAX_RETRY_ATTEMPTS = 3
const DEBOUNCE_DELAY_MS = 500

if (retryCount > MAX_RETRY_ATTEMPTS) { ... }
setTimeout(callback, DEBOUNCE_DELAY_MS)
```

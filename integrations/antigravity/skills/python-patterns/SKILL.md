---
name: python-patterns
description: Pythonic idioms, PEP 8 standards, modern static typing, Protocols, dataclasses, context managers, async hygiene, exception hierarchies, and performance best practices for robust Python applications. Use when writing, reviewing, or refactoring Python code.
version: 2.0.0
triggers:
  - "python patterns"
  - "pep 8"
  - "type hints"
  - "dataclasses"
  - "context managers"
  - "async python"
  - "pythonic idioms"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Python Development Patterns & Idioms

Idiomatic Python patterns, modern type systems (Python 3.10+), concurrency architectures, and best practices for building robust, maintainable, and high-performance applications.

## When to Activate

- Writing new Python code or designing Python packages/modules
- Reviewing or refactoring existing Python code for quality and idiomatic style
- Defining interfaces with `Protocol`, `ABC`, or dataclasses
- Structuring exception handling hierarchies and context managers
- Optimizing CPU-bound or async I/O-bound concurrent operations
- Configuring linters, formatters (`ruff`, `mypy`), and packaging via `uv`

---

## Core Principles

### 1. Readability Counts

Python prioritizes human readability. Code should be explicit and easy to reason about:

```python
# PASS: Clear and readable
def get_active_users(users: list[User]) -> list[User]:
    """Return only active users from the provided list."""
    return [user for user in users if user.is_active]


# FAIL: Clever but confusing
def get_active_users(u):
    return [x for x in u if x.a]
```

### 2. Explicit is Better Than Implicit

Avoid hidden magic or surprise side effects:

```python
# PASS: Explicit configuration
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# FAIL: Hidden side effects
import some_module
some_module.setup()  # What does this do?
```

### 3. EAFP - Easier to Ask Forgiveness Than Permission

Python prefers structured exception handling over race-prone condition checks:

```python
# PASS: EAFP style
def get_value(dictionary: dict[str, Any], key: str, default_value: Any = None) -> Any:
    try:
        return dictionary[key]
    except KeyError:
        return default_value

# FAIL: LBYL (Look Before You Leap) style
def get_value(dictionary: dict[str, Any], key: str, default_value: Any = None) -> Any:
    if key in dictionary:
        return dictionary[key]
    else:
        return default_value
```

---

## Modern Type Hints (Python 3.10+)

### Built-in Generics & Union Operator

Use native built-in collections (`list`, `dict`, `set`, `tuple`) and the pipe operator `|` for optionality and unions:

```python
# PASS: Modern Python 3.10+ typing
def process_items(
    items: list[str],
    filter_prefix: str | None = None
) -> dict[str, int]:
    """Process items and return mapping of name to length."""
    results: dict[str, int] = {}
    for item in items:
        if filter_prefix is None or item.startswith(filter_prefix):
            results[item] = len(item)
    return results

# FAIL: Legacy typing imports
from typing import List, Dict, Optional, Union
def process_items_legacy(items: List[str], filter_prefix: Optional[str] = None) -> Dict[str, int]:
    ...
```

### Type Aliases, TypeVar, and Self

```python
from typing import TypeVar, Any, Self

# Type alias
JsonDict = dict[str, Any]

# Generic types
T = TypeVar('T')

def first(items: list[T]) -> T | None:
    """Return the first item or None if list is empty."""
    return items[0] if items else None

class QueryBuilder:
    def __init__(self) -> None:
        self.clauses: list[str] = []

    def match(self, pattern: str) -> Self:
        self.clauses.append(f"MATCH {pattern}")
        return self

    def where(self, condition: str) -> Self:
        self.clauses.append(f"WHERE {condition}")
        return self
```

### Protocol-Based Duck Typing

Use `typing.Protocol` for structural subtyping without rigid inheritance:

```python
from typing import Protocol

class Renderable(Protocol):
    def render(self) -> str:
        """Render the object to a string."""

def render_all(items: list[Renderable]) -> str:
    """Render all items that implement the Renderable protocol."""
    return "\n".join(item.render() for item in items)
```

---

## Error Handling Patterns

### Specific Exception Handling

```python
# PASS: Catch specific exceptions
def load_config(path: str) -> Config:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return Config.from_json(f.read())
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config: {path}") from e

# FAIL: Bare except catches SystemExit, KeyboardInterrupt, etc.
def load_config(path: str) -> Config | None:
    try:
        with open(path) as f:
            return Config.from_json(f.read())
    except:
        return None  # Silent failure!
```

### Exception Chaining

Always preserve underlying root causes using `raise ... from e`:

```python
def process_data(data: str) -> Result:
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse payload: {data}") from e
```

### Custom Exception Hierarchy

```python
class AppError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.code = code

class ValidationError(AppError):
    """Raised when input validation fails."""
    def __init__(self, message: str, details: list[dict[str, str]] | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.details = details or []

class NotFoundError(AppError):
    """Raised when a requested resource is not found."""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} not found: {resource_id}", code="NOT_FOUND")
```

---

## Context Managers

### Resource Management

```python
# PASS: Clean resource management
def process_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

# FAIL: Manual resource handling
def process_file(path: str) -> str:
    f = open(path, 'r')
    try:
        return f.read()
    finally:
        f.close()
```

### Generator Context Managers (`@contextmanager`)

```python
import time
from contextlib import contextmanager

@contextmanager
def timer(name: str):
    """Context manager to time a block of execution."""
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"{name} took {elapsed:.4f} seconds")

# Usage
with timer("embedding extraction"):
    extract_embeddings(corpus)
```

### Class-Based Context Managers

```python
class DatabaseTransaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.begin_transaction()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        return False  # Propagate exceptions
```

---

## Comprehensions and Generators

### List Comprehensions vs Expanded Loops

```python
# PASS: List comprehension for simple 1-to-1 transforms
names = [user.name for user in users if user.is_active]

# FAIL: Overly complex comprehension
result = [x * 2 for x in items if x > 0 if x % 2 == 0]

# PASS: Expand complex logic for clarity
def filter_and_transform(items: list[int]) -> list[int]:
    result = []
    for x in items:
        if x > 0 and x % 2 == 0:
            result.append(x * 2)
    return result
```

### Generator Expressions & Streaming

```python
# PASS: Generator expression avoids allocating large lists
total_squares = sum(x * x for x in range(1_000_000))

# PASS: Generator function for stream processing
from collections.abc import Iterator

def read_large_file(path: str) -> Iterator[str]:
    """Read a large file line by line without blowing up memory."""
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            yield line.strip()
```

---

## Data Classes and Named Tuples

### Data Classes

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class User:
    """User entity with automatic __init__, __repr__, and __eq__."""
    id: str
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
```

### Data Classes with Validation

```python
@dataclass
class UserSession:
    user_id: str
    ttl_seconds: int

    def __post_init__(self):
        if self.ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {self.ttl_seconds}")
        if not self.user_id:
            raise ValueError("user_id cannot be empty")
```

### Named Tuples

```python
from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float

    def distance(self, other: 'Point') -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
```

---

## Decorators

### Function Decorators with `wraps`

```python
import functools
import time
from collections.abc import Callable

def timer(func: Callable) -> Callable:
    """Decorator to time function execution."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper
```

### Parameterized Decorators

```python
def repeat(times: int):
    """Decorator to repeat a function invocation multiple times."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            results = []
            for _ in range(times):
                results.append(func(*args, **kwargs))
            return results
        return wrapper
    return decorator
```

---

## Concurrency Patterns

### Threading for I/O-Bound Tasks

```python
import concurrent.futures

def fetch_url(url: str) -> str:
    import urllib.request
    with urllib.request.urlopen(url) as response:
        return response.read().decode()

def fetch_all_urls(urls: list[str]) -> dict[str, str]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        results = {}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception as e:
                results[url] = f"Error: {e}"
    return results
```

### Multiprocessing for CPU-Bound Tasks

```python
def process_data(data: list[int]) -> int:
    return sum(x ** 2 for x in data)

def process_all(datasets: list[list[int]]) -> list[int]:
    with concurrent.futures.ProcessPoolExecutor() as executor:
        return list(executor.map(process_data, datasets))
```

### Async/Await & Event-Loop Hygiene

```python
import asyncio
import aiohttp

async def fetch_async(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as response:
        return await response.text()

async def fetch_all(urls: list[str]) -> list[str]:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_async(session, url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

**FastMCP Async Rule:** Never run blocking synchronous I/O or CPU loops directly in an async tool coroutine; offload to a thread via `asyncio.to_thread(sync_func, *args)`.

---

## Package Organization & `src/` Layout

```
myproject/
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── main.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── routes.py
│       ├── models/
│       │   ├── __init__.py
│       │   └── user.py
│       └── utils/
│           ├── __init__.py
│           └── helpers.py
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   └── test_models.py
├── pyproject.toml
└── README.md
```

### Import Conventions

```python
# Stdlib first
import os
import sys
from pathlib import Path

# Third-party packages
import pydantic
import redis

# Local package imports
from mypackage.models import User
from mypackage.utils import format_name
```

### Explicit `__all__` in `__init__.py`

```python
# mypackage/__init__.py
from mypackage.models import User, Post
from mypackage.utils import format_name

__all__ = ["User", "Post", "format_name"]
```

---

## Memory & Performance

### `__slots__` for Memory Optimization

```python
# Regular class uses __dict__ (overhead per instance)
class PointNormal:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

# PASS: __slots__ significantly reduces memory for millions of instances
class PointOptimized:
    __slots__ = ('x', 'y')

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
```

### String Concatenation in Loops

```python
# FAIL: O(n²) string allocations
result = ""
for item in items:
    result += str(item)

# PASS: O(n) join
result = "".join(str(item) for item in items)
```

---

## Tooling Integration with `uv`

```bash
# Add packages with uv
uv add pydantic>=2.0.0 redis

# Run test suite
uv run pytest -v

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src
```

---

## Quick Reference: Python Idioms

| Idiom | Description |
| :--- | :--- |
| **EAFP** | Easier to Ask Forgiveness than Permission (try/except over condition checks) |
| **Context managers** | Use `with` for guaranteed resource acquisition and release |
| **List comprehensions** | For simple, readable element transformations |
| **Generators** | Use generator expressions and `yield` for lazy, low-memory evaluation |
| **Type hints** | Annotate signatures with built-ins (`list`, `dict`) and `|` |
| **Dataclasses** | Auto-generate boilerplate `__init__`, `__repr__`, `__eq__` |
| **`__slots__`** | Suppress `__dict__` overhead in high-instance data models |
| **`pathlib.Path`** | Modern object-oriented filesystem operations |
| **`enumerate`** | Clean index-element tracking in for loops |

---

## Anti-Patterns to Avoid

```python
# FAIL: Mutable default arguments
def append_to(item, items=[]):
    items.append(item)
    return items

# PASS: None default with instantiation
def append_to(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items

# FAIL: Checking type with type()
if type(obj) == list:
    pass

# PASS: Use isinstance (handles inheritance)
if isinstance(obj, list):
    pass

# FAIL: Comparing to None with ==
if value == None:
    pass

# PASS: Use 'is None' (identity comparison)
if value is None:
    pass

# FAIL: Wildcard imports
from os.path import *

# PASS: Explicit imports
from os.path import join, exists

# FAIL: Bare except
try:
    operation()
except:
    pass

# PASS: Catch specific exception
try:
    operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
```

---
name: python-best-practices-performance
description: Use when writing, reviewing, refactoring, debugging, or optimizing Python code. Enforces modern idiomatic Python, strong typing, maintainability, testing, security, algorithmic efficiency, resource efficiency, profiling-driven optimization, and production-grade performance practices.
---

# Python Best Practices & Performance

## Purpose

Write and review Python code that is:

1. Correct
2. Readable
3. Maintainable
4. Testable
5. Type-safe
6. Efficient
7. Production-ready

Performance must be treated as an engineering trade-off, not as a reason to make code unnecessarily complex.

The default priority is:

**Correctness → Clarity → Maintainability → Measurable Performance**

Never sacrifice correctness or maintainability for speculative micro-optimizations.

---

# Core Principles

## 1. Prefer idiomatic Python

Use Python's standard language features and standard library before introducing custom abstractions or dependencies.

Prefer:

- `pathlib` over manual path string manipulation
- `dataclasses` for simple data containers
- `Enum` for finite sets of values
- `collections` utilities when appropriate
- comprehensions when they improve readability
- generators for lazy processing
- context managers for resource lifecycle
- `enumerate()` instead of manually tracking indexes
- `zip()` instead of indexing multiple collections
- `any()` / `all()` for expressive predicates
- `sorted()` / `min()` / `max()` with `key=`
- `set` for membership-heavy operations
- `dict` for key-based lookups

Avoid clever Python when a simpler implementation is easier to understand.

---

## 2. Keep functions focused

Functions should have one clear responsibility.

Avoid functions that simultaneously:

- validate input
- query databases
- transform data
- perform business logic
- write files
- send network requests

Separate these responsibilities when doing so improves clarity or testability.

Do not create abstractions merely to make functions smaller.

---

## 3. Type hints

Use type hints consistently.

Public functions, methods, classes, and non-trivial internal APIs should be typed.

Prefer modern syntax:

```python
def get_users(limit: int) -> list[User]:
    ...
```

Use `str | None` instead of `Optional[str]` when the project's Python version supports it.

Use precise types. Avoid `Any` unless genuinely required.

Use `Protocol`, generics, type aliases, `TypedDict`, dataclasses, and structural typing when they provide meaningful value.

Do not add excessive typing complexity to simple code.

---

## 4. Data structures and algorithmic complexity

Always consider algorithmic complexity when reviewing performance-sensitive code.

Identify:

- time complexity
- space complexity
- number of iterations
- repeated searches
- repeated allocations
- database/network operations

Prefer `set` / `dict` for O(1)-average membership and lookup operations when appropriate.

Use sorting, indexing, or precomputation when repeated lookups justify the cost.

Do not optimize complexity if the input is guaranteed to be tiny and the simpler implementation is clearly preferable.

---

## 5. Avoid unnecessary allocations

Be aware of memory usage.

Avoid creating unnecessary intermediate collections.

For large datasets, prefer streaming:

```python
with path.open() as file:
    for line in file:
        process(line)
```

Generators can be useful for lazy processing:

```python
result = (transform(item) for item in items)
```

Do not blindly replace lists with generators. If repeated iteration is required, materializing the collection may be the correct choice.

---

## 6. Performance optimization must be evidence-driven

Never claim that an implementation is faster without a reasonable basis.

When practical:

1. Establish the baseline.
2. Identify the bottleneck.
3. Profile or benchmark.
4. Make the smallest meaningful optimization.
5. Benchmark again.
6. Verify correctness.
7. Document important trade-offs.

Useful tools include:

- `cProfile`
- `py-spy`
- `scalene`
- `memray`
- `tracemalloc`
- `timeit`
- `pytest-benchmark`

Do not optimize code simply because it "looks slow."

---

## 7. Avoid premature micro-optimization

Focus first on:

- algorithmic complexity
- database queries
- network requests
- filesystem operations
- serialization
- unnecessary copying
- excessive object creation
- inefficient loops over large datasets
- repeated computation
- concurrency opportunities

A 100x reduction in database calls is more important than a 5% faster Python loop.

---

## 8. Database performance

Treat database operations as potentially expensive.

Avoid queries inside loops when they can be batched.

Watch for:

- N+1 queries
- missing indexes
- unnecessary columns
- excessive joins
- repeated queries
- large unbounded result sets
- inefficient pagination
- unnecessary transactions
- loading entire datasets into memory

Use:

- batching
- indexes
- appropriate pagination
- projections/selective columns
- bulk inserts/updates
- connection pooling

Do not optimize SQL blindly. Inspect the query plan when necessary.

---

## 9. I/O

I/O is frequently more expensive than Python computation.

Pay particular attention to:

- HTTP requests
- database queries
- filesystem operations
- subprocess calls
- cloud APIs

Avoid sequential I/O when independent operations can safely run concurrently.

Do not introduce async merely because async is available.

---

## 10. Async Python

Use `asyncio` for I/O-bound concurrency.

Async does not make CPU-bound code faster.

For CPU-bound workloads consider:

- multiprocessing
- process pools
- NumPy/vectorization
- specialized native libraries
- compiled implementations

Avoid blocking calls inside async functions.

When using synchronous libraries that cannot be replaced, consider appropriate thread/process offloading.

---

## 11. Concurrency

Choose the concurrency model based on workload.

### I/O-bound

Consider:

- `asyncio`
- `ThreadPoolExecutor`

### CPU-bound

Consider:

- `ProcessPoolExecutor`
- `multiprocessing`
- native/vectorized libraries

### Simple sequential workloads

Keep them sequential.

Concurrency introduces complexity.

Always consider:

- thread safety
- shared mutable state
- ordering
- cancellation
- retries
- timeouts
- rate limits
- resource limits

---

## 12. Caching

Caching can significantly improve performance but introduces invalidation complexity.

Before adding caching, identify:

- what is expensive
- how often it is requested
- how frequently it changes
- acceptable staleness
- cache size
- invalidation strategy

Do not cache everything.

Avoid caching data with unclear invalidation semantics.

---

## 13. Error handling

Do not silently swallow exceptions.

Avoid:

```python
try:
    process()
except Exception:
    pass
```

Prefer explicit handling:

```python
try:
    process()
except SpecificError as exc:
    logger.error("Processing failed: %s", exc)
    raise
```

Catch the narrowest meaningful exception.

Never hide failures merely to make a function "robust."

---

## 14. Logging

Use structured, useful logging.

Avoid excessive logging inside high-frequency loops.

Do not log:

- passwords
- tokens
- API keys
- secrets
- sensitive personal data

Use appropriate log levels and aggregate progress reporting when processing large datasets.

---

## 15. Resource management

Use context managers for resources.

Prefer:

```python
with open(path) as file:
    ...
```

Apply the same principle to:

- database connections
- transactions
- locks
- temporary resources
- HTTP clients
- sockets

Resources should have deterministic lifecycle management.

---

## 16. External API calls

External calls should normally include:

- timeout
- retry strategy when appropriate
- error handling
- rate-limit handling
- connection reuse
- response validation

Do not retry non-idempotent operations blindly.

Use exponential backoff when retries are appropriate.

---

## 17. Serialization

Serialization can become a major bottleneck.

Be conscious of:

- JSON encoding/decoding
- large payloads
- repeated serialization
- unnecessary conversions
- compression overhead

Avoid converting data through multiple representations unnecessarily.

For high-volume systems, benchmark serialization libraries rather than assuming one is faster.

---

## 18. Testing

Every meaningful change should consider tests.

Use:

- unit tests
- integration tests
- regression tests
- property-based tests where appropriate
- benchmarks for performance-sensitive code

Tests should verify behavior, not implementation details.

For performance changes, preserve a correctness test suite before optimizing.

A performance optimization that changes behavior is not an optimization.

---

## 19. Benchmarking

Use benchmarks when comparing implementations.

Example:

```python
from timeit import timeit

duration = timeit(
    "function(data)",
    globals={"function": function, "data": data},
    number=1000,
)

print(duration)
```

For project-level benchmarking, prefer `pytest-benchmark` when configured.

Benchmarks should:

- use representative data
- include realistic input sizes
- run multiple iterations
- compare equivalent behavior
- avoid measuring unrelated startup costs when inappropriate

Report meaningful differences rather than insignificant noise.

---

## 20. Memory optimization

When memory matters, investigate before optimizing.

Useful tools:

- `tracemalloc`
- `memray`
- `scalene`

Consider:

- generators
- streaming
- batching
- avoiding copies
- reducing object creation
- compact data structures
- releasing unnecessary references

Do not optimize memory usage at the expense of dramatically worse readability without evidence that memory is actually a constraint.

---

## 21. Python-specific performance

Be aware that:

- Python loops can be expensive at scale.
- Function calls have overhead.
- Object creation has cost.
- Attribute access has cost.
- Serialization can dominate runtime.
- Database/network I/O often dominates computation.
- NumPy/vectorized operations can outperform Python loops for numerical workloads.
- Generators reduce memory usage but are not automatically faster.

Do not assume that list comprehensions, generators, async, or multiprocessing are universally faster.

Benchmark when the distinction matters.

---

## 22. Imports and dependencies

Prefer the standard library when sufficient.

Avoid adding dependencies for trivial functionality.

Keep imports:

- explicit
- organized
- minimal

Avoid circular dependencies.

Do not introduce a framework or library solely to solve a small problem that Python already handles well.

---

## 23. Architecture

Use the simplest architecture that satisfies the requirements.

Do not introduce:

- unnecessary repositories
- unnecessary services
- unnecessary factories
- unnecessary interfaces
- unnecessary dependency injection
- unnecessary design patterns

Architecture should solve a real problem.

For larger applications, separate concerns such as:

```text
presentation
    ↓
application/business logic
    ↓
domain
    ↓
infrastructure
```

Do not force this structure onto small scripts or simple services.

---

## 24. Configuration

Do not hard-code:

- credentials
- API keys
- passwords
- environment-specific URLs
- secrets

Use environment variables or an appropriate configuration system.

Validate configuration at startup when practical.

Fail fast when required configuration is missing.

---

## 25. Security

Treat security as part of code quality.

Avoid:

- `eval()`
- `exec()`
- unsafe deserialization
- shell injection
- SQL injection
- path traversal
- hard-coded secrets
- insecure temporary files
- leaking sensitive information through logs

Use parameterized database queries.

Validate external input.

Prefer safe standard-library APIs.

---

## 26. Refactoring

When refactoring:

1. Understand existing behavior.
2. Identify current tests.
3. Preserve behavior unless explicitly asked to change it.
4. Make focused changes.
5. Run tests.
6. Measure performance when relevant.
7. Avoid unrelated rewrites.

Do not rewrite an entire module simply because a small improvement is needed.

---

## 27. Code review procedure

When reviewing Python code, evaluate in this order:

### Correctness

- Does it work?
- Are edge cases handled?
- Are exceptions handled correctly?

### Design

- Are responsibilities clear?
- Is the abstraction justified?
- Is the code maintainable?

### Types

- Are important APIs typed?
- Are types accurate?
- Is `Any` being overused?

### Complexity

- What is the time complexity?
- What is the memory complexity?
- Are there repeated operations?

### I/O

- Are database/network/filesystem calls efficient?
- Are there N+1 patterns?
- Can independent operations run concurrently?

### Memory

- Are large datasets unnecessarily materialized?
- Are there unnecessary copies?

### Performance

- Is there a measurable bottleneck?
- Is optimization justified?
- Can the change be benchmarked?

### Testing

- Are important behaviors covered?
- Does the change require regression tests?
- Should a benchmark be added?

### Security

- Are inputs validated?
- Are secrets protected?
- Are external resources handled safely?

---

## 28. Performance review format

When asked to optimize code, provide reasoning in this structure:

```text
Current bottleneck:
<what is expensive>

Current complexity:
Time: O(...)
Space: O(...)

Proposed change:
<what will change>

Expected impact:
<why it should improve performance>

Trade-offs:
<readability / memory / complexity / maintainability>

Validation:
<tests or benchmark needed>
```

Do not claim exact performance improvements unless measured.

---

## 29. When to use a benchmark

A benchmark is recommended when:

- comparing two implementations
- optimizing a hot path
- changing algorithms
- changing serialization
- changing data structures
- optimizing parsing
- optimizing numerical computation
- changing concurrency strategy

A benchmark is usually unnecessary for:

- obvious correctness fixes
- trivial refactors
- code that is not performance-sensitive
- architectural changes where runtime performance is not the primary concern

---

## 30. Preferred tooling

When the project already uses tooling, follow the project's configuration.

Otherwise prefer:

- Ruff → linting + formatting
- Pyright → type checking
- Pytest → testing
- Coverage → test coverage

For performance investigation:

- cProfile
- py-spy
- scalene
- tracemalloc
- memray
- pytest-benchmark
- timeit

Do not add all tools automatically.

Introduce only tools that provide meaningful value for the project.

---

## 31. Definition of Done

Python code should generally satisfy:

- [ ] Correct behavior
- [ ] Clear naming
- [ ] Focused functions
- [ ] Appropriate types
- [ ] No unnecessary abstractions
- [ ] Appropriate data structures
- [ ] Reasonable time complexity
- [ ] Reasonable memory usage
- [ ] No obvious N+1 operations
- [ ] Appropriate I/O handling
- [ ] Proper resource cleanup
- [ ] Appropriate exception handling
- [ ] No exposed secrets
- [ ] Tests for meaningful behavior
- [ ] Formatting/linting passes
- [ ] Type checking passes where configured
- [ ] Performance claims are evidence-based

---

## 32. Important Anti-Patterns

Avoid these unless there is a documented reason:

- Premature optimization
- Overengineering
- God classes
- God functions
- Deep inheritance hierarchies
- Unnecessary async
- Unnecessary multiprocessing
- Unnecessary caching
- Unnecessary abstractions
- Broad exception handling
- Silent exception swallowing
- N+1 queries
- Unbounded memory usage
- Repeated expensive computation
- Repeated network/database calls
- Hard-coded secrets
- Untyped public APIs

---

# Golden Rule

When choosing between two implementations, prefer the implementation that provides the best balance of:

**Correctness + Readability + Maintainability + Performance + Operational simplicity**

Do not optimize code simply because optimization is possible.

Optimize the bottleneck that actually matters.

# Architectural Decision Records (ADRs)

This directory contains Architectural Decision Records for Project Aegis.

## What is an ADR?

An Architectural Decision Record captures an important architectural decision made along with its context and consequences.

## ADR Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-001](001-ipc-mechanism.md) | IPC Mechanism Selection | Accepted | 2026-01-09 |
| [ADR-002](002-zkp-library-selection.md) | ZKP Library Selection | Accepted | 2026-01-09 |
| [ADR-003](003-polymorphic-build-strategy.md) | Polymorphic Build Strategy | Accepted | 2026-01-09 |
| [ADR-004](004-secrets-management.md) | Secrets Management Architecture | Accepted | 2026-01-09 |

## ADR Template

When creating a new ADR, use the following template:

```markdown
# ADR-XXX: Title

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult to do because of this change?
```

## References

- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) by Michael Nygard

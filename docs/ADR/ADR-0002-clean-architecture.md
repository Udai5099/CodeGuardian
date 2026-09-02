# ADR-0002: Use Clean Architecture Inside Each Module

## Status
Accepted

## Decision
Each module should follow the flow API -> Application -> Domain -> Infrastructure to preserve separation of concerns.

## Rationale
This makes modules easier to test, evolve, and eventually extract into services when needed.

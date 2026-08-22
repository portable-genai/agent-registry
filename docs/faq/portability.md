# Portability FAQ

## What does the executable proof establish?

`make portability-demo` checks exact profile bindings, deterministic SQLite behavior, SDK-free
managed construction, fail-fast on-prem behavior and unknown-selector rejection.

## What remains unproved?

It does not prove live AlloyDB or Firestore, a completed on-prem adapter, cross-store export and
import, tenant portability or Hrz5 audit delivery.

## Why is there no platform profile?

Hrz3 is itself the shared platform registry. Verticals delegate registry operations to Hrz3;
Hrz3 cannot delegate the same responsibility back to itself.

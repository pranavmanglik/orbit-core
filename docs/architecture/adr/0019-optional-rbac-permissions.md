# ADR 0019: Optional RBAC permission capability

- Status: Superseded by ADR 0026
- Date: 2026-10-05

> This initial dependency decision was superseded by [ADR 0023](0023-framework-independent-rbac-subject.md) and the package boundary in [ADR 0026](0026-auth-capability-boundary.md).

## Context

Core provides verified `Principal` objects and general policy hooks. Applications need a simple
way to map those trusted role claims to operation permissions without adding a database, identity
provider, or vendor SDK to Core. The requested `orbit-auth-rbac` workspace was an empty repository shell.

## Decision

Implement `orbit-auth-rbac` as an optional, provider-neutral capability that accepts a trusted
structural `RoleSubject` and an application-supplied role-to-permission map. The map is copied, bounded, and immutable after
construction. Authorization uses exact permission identifiers and denies anonymous principals,
unknown roles, unknown permissions, and wildcard grants.

This ADR's original Core-principal ownership was superseded by ADR 0022 and then refined by ADR 0026: the auth contracts now live in `orbit-auth`. `orbit-auth-rbac` does not authenticate users, assign trusted roles, persist policy, or
provide role inheritance. Applications must only place roles on a subject after trusted
authentication or authorization. Provider adapters and database-backed policy stores remain
separate packages.

## Alternatives considered

- Add permission mapping to Core: rejected because it is an optional authorization policy above
  Core's stable principal and policy contracts.
- Put role persistence or identity verification in `orbit-auth-rbac`: rejected because those capabilities
  have separate lifecycle, storage, and provider boundaries.
- Support wildcard permissions: rejected because broad implicit grants make policy errors difficult
  to review and can silently expand access.

## Consequences

- Applications can compose exact role permissions without an external dependency beyond Core.
- Policy is local to the process and configured by the application; there is no cross-worker
  synchronization or dynamic revocation store.
- The package remains pre-alpha until its public API receives the regular release review.

## Evidence

- Implementation: `../orbit-auth-rbac/src/orbit_auth_rbac/`
- [Core and plugin ownership](../core-and-plugin-ownership.md)
- [Orbit RBAC README](../../../../orbit-auth-rbac/README.md)

# ADR 0023: Framework-independent RBAC subject contract

- Status: Accepted
- Date: 2026-10-05

## Context

The `orbit-auth-rbac` package directly imported Core's `Principal` and `SecurityError`, which made an
optional policy capability depend on Core and tied its public behavior to Core's unfinished
security implementation. RBAC needs trusted role identifiers, but it does not need to authenticate
users or know the host framework's principal or HTTP error types.

## Decision

Define a structural `RoleSubject` contract in `orbit-auth-rbac`. It exposes a `frozenset[str]` of roles
that an application has already established through a trusted authentication or authorization
boundary. `orbit-auth-rbac` validates the bounded identifiers, maps them to exact permissions, and raises
its own sanitized `PermissionDenied` error. The package has no runtime dependencies and does not
import Core or a security provider.

This contract does not authenticate a subject or prove that its roles are trustworthy. Host
integration code is responsible for passing an authenticated subject and mapping `PermissionDenied`
to its transport's forbidden response. Anonymous and unknown roles remain denied.

## Alternatives considered

- Depend on Core's `Principal`: rejected because the package then requires Core and follows its
  still-transitional identity model.
- Depend on `orbit-security`'s Principal: rejected while that package still builds on Core-owned
  security models; it would preserve the framework dependency through another package.
- Accept arbitrary mappings or role collections: rejected because an explicit subject protocol
  makes the trust boundary visible at call sites and supports static checking.

## Consequences

- RBAC can be installed and used independently of Orbit Core.
- Orbit Security principals or other authenticated subjects can satisfy the structural contract
  without a runtime dependency or conversion object.
- This is a pre-alpha API change: the former Core `SecurityError` is replaced by `PermissionDenied`,
  and applications must adapt that exception at their framework boundary.
- The role set is bounded to 1,024 validated identifiers per authorization call. Grant maps remain
  copied, immutable, exact-match, and default-deny.

## Evidence

- `orbit-auth-rbac/src/orbit_auth_rbac/authorizer.py`
- `orbit-auth-rbac/tests/test_authorizer.py`
- Core-free source and installed-wheel import checks under `python -S`
- [Orbit RBAC README](../../../../orbit-auth-rbac/README.md)
- [Superseded initial RBAC decision](0019-optional-rbac-permissions.md)

# ADR 0016: Plan Orbit Security variants above the Core baseline

- Status: Superseded by [ADR 0017](0017-single-security-package.md)
- Date: 2026-10-04

## Context

Orbit Core includes opt-in static-user Basic Auth and provider-neutral identity and authorization
contracts. The current `orbit-security` workspace provides only optional, provider-neutral HTTP
rate-limit middleware. The project also calls for basic and professional `orbit-sec` variants;
describing the current workspace as a complete security suite would overstate its implementation.

## Decision

Keep Core's Basic Auth and provider-neutral security contracts in Core. Treat the requested basic and
professional `orbit-sec` variants as optional additions above that baseline: they must not
replace or duplicate Core's built-in authentication, and advanced identity providers or vendor
integrations remain separately installable.

This ADR records the ownership direction, not the variants' feature lists or distribution topology.
The current `orbit-security` workspace is not yet either complete variant. Decide whether the
variants are extras, subpackages, or separate distributions—and define their capabilities—before
implementing or moving code for them.

## Alternatives considered

- Move Core Basic Auth into an optional package: rejected because the baseline must remain useful
  without installing an add-on.
- Treat the current rate-limit middleware as a complete basic or professional security variant:
  rejected because it provides request throttling only.
- Bundle provider-specific identity integrations in Core: rejected because they are optional and
  have independent provider dependencies, credentials, transport, and failure behavior.

## Consequences

- Core continues to provide opt-in Basic Auth without another distribution or default credentials.
- Current `orbit-security` claims remain limited to its existing rate-limit middleware.
- The planned variants remain explicitly unimplemented until their scope and package boundaries are
  designed and their own code, tests, documentation, and packaging are available.
- JWT verification remains in `orbit-auth-jwt`; future OAuth/OIDC and vendor integrations remain
  optional packages.

## Evidence

- `src/orbit/security/basic.py`
- `src/orbit/security/contracts.py`
- `orbit-security` sibling workspace: `src/orbit_security/ratelimit.py`
- [Core and plugin ownership](../core-and-plugin-ownership.md)
- [Security model](../../security/overview.md)

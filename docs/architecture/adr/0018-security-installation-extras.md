# ADR 0018: Orbit Security installation extras

- Status: Superseded by [ADR 0022](0022-extract-database-and-authentication.md)
- Date: 2026-10-05

## Context

Core provides an opt-in static-user Basic Authenticator with salted password hashing and safe
defaults for simple development and administration. The optional `orbit-security` distribution
currently implements provider-neutral request-level rate limiting. Earlier decisions ruled out
separate Basic and Professional distributions, but the selected package model calls for progressive
installation options without splitting the public package identity or duplicating Core's baseline.

## Decision

Keep one separately installable `orbit-security` distribution. Organize future Basic and
Professional security capabilities as installation extras on that distribution. Core's Basic Auth
remains built in and is not moved, replaced, or enabled by an extra. Provider adapters such as
`orbit-auth-jwt` and the planned `orbit-auth-oauth2` remain independently installable and own their SDKs,
credentials, transports, and provider-specific errors.

The `basic` and `professional` extras are a packaging decision only until each has a concrete
capability set. Do not publish or document install commands for them as usable feature sets until
the corresponding implementation, optional dependencies, installation tests, and security guidance
are present. Do not install provider adapters implicitly through either extra.

## Alternatives considered

- Separate `orbit-security-basic` and `orbit-security-professional` distributions: rejected because
  they fragment one provider-neutral capability package and make Core's built-in baseline harder to
  distinguish from separately installed policies.
- Put JWT/OAuth implementations inside the extras: rejected because provider SDKs, credentials,
  transports, and failure behavior belong to their separately installable adapters.
- Advertise empty extras before capabilities exist: rejected because installation would imply
  functionality and security coverage that the package does not provide.

## Consequences

- Core Basic Auth continues to work without installing `orbit-security`.
- `orbit-security` remains a single distribution; its only implemented feature is currently
  request-level rate limiting.
- Basic and Professional extras are planned packaging surfaces, not current security products.
- Each extra must be tested from a clean installation and documented with its exact scope before
  it is exposed to users.

## Evidence

- Core baseline: `src/orbit/security/`
- Optional policy package: `../orbit-security/src/orbit_security/`
- [Core and plugin ownership](../core-and-plugin-ownership.md)
- [Security model](../../security/overview.md)

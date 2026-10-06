# ADR 0017: Use one optional Orbit Security package

- Status: Superseded by [ADR 0022](0022-extract-database-and-authentication.md)
- Date: 2026-10-05

## Context

Orbit Core already provides opt-in Basic Auth, provider-neutral identity and authorization
contracts, and a bounded local rate limiter for the built-in Admin surface. The separate
`orbit-security` workspace currently provides optional request-level rate-limiting middleware.
The earlier proposal for separate Basic and Professional security variants would duplicate the
Core baseline and split a small optional policy package without an established capability boundary.

## Decision

Keep the useful built-in security baseline in Core and maintain one optional `orbit-security`
package for additional provider-neutral security policies. Do not create separate Basic or
Professional security distributions. The existing `orbit-security` package remains opt-in and its
current implemented feature remains request-level rate limiting; this decision does not claim that
it is a complete security suite.

Concrete identity providers and vendor-backed integrations, including JWT verification and future
OAuth/OIDC providers, remain separate optional packages. Core security features continue to work
without installing `orbit-security` or an identity-provider package.

This decision supersedes the proposed variant topology in ADR 0016 and confirms the Core ownership
boundary recorded in ADR 0015.

## Alternatives considered

- Split Basic and Professional security into separate distributions: rejected because the Core
  baseline already covers basic development and administration, while the current optional package
  is one cohesive provider-neutral policy package.
- Move Core Basic Auth into `orbit-security`: rejected because applications must retain the built-in
  baseline without another installation requirement.
- Put JWT or OAuth/OIDC provider implementations in Core or `orbit-security`: rejected because
  those integrations have independent dependencies, credentials, transport, and provider-specific
  lifecycle and failure behavior.

## Consequences

- Core retains opt-in Basic Auth and its existing provider-neutral security contracts and Admin
  protection.
- `orbit-security` remains a single separately installable package, currently implementing
  request-level rate limiting.
- No separate Basic/Professional security package variants are planned.
- JWT and future identity-provider integrations remain optional packages and are not installed
  implicitly.

## Evidence

- Core baseline: `src/orbit/security/`
- Optional policy package: `../orbit-security/src/orbit_security/`
- [Core and plugin ownership](../core-and-plugin-ownership.md)
- [Security model](../../security/overview.md)

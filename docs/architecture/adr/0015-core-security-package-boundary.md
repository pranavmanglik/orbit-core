# ADR 0015: Keep the Basic Auth baseline in Core and extend orbit-security optionally

- Status: Superseded by [ADR 0022](0022-extract-database-and-authentication.md)
- Date: 2026-10-04

## Context

Orbit Core must be usable for ordinary local development and simple administration without forcing
applications to install a security add-on. It already provides identity and principal models,
authentication and authorization contracts, opt-in static-user HTTP Basic authentication, and a
small process-local rate limiter for Core's Admin surface. The separate `orbit-security` package
currently provides general request-level rate-limit middleware. The project also plans concrete
JWT and OAuth/OIDC integrations in separate packages.

## Decision

Keep the opt-in Basic Auth implementation and provider-neutral security contracts in Core. Treat
`orbit-security` as the single optional package for additional provider-neutral security policies;
its current request rate-limiting middleware is such a policy. Do not create parallel
basic/professional security distributions that duplicate the Core baseline. Keep concrete identity
providers and vendor integrations in separate optional packages, including the existing
`orbit-auth-jwt` adapter and any future OAuth/OIDC integrations.

## Alternatives considered

- Move Basic Auth into an optional package: rejected because simple development and administrative
  authentication is an explicit Core baseline and should not require another distribution.
- Create separate basic and professional security packages: rejected because the basic mechanism is
  already provided by Core, while professional identity features are provider-specific and should
  be installed independently.
- Put JWT/OAuth provider implementations in `orbit-security`: rejected because provider SDKs,
  transport, credentials, and vendor failure semantics belong at the provider adapter boundary.

## Consequences

- Applications can opt into Core Basic Auth without installing `orbit-security` or a JWT package.
- Core Basic Auth remains a static configured-user mechanism with no account lifecycle, federation,
  password reset, or persistent credential store; production guidance must state those limits.
- `orbit-security` stays optional and provider-neutral; its presence does not imply distributed
  rate limiting or professional identity management.
- JWT/OAuth integrations remain independently installable and cannot become transitive Core
  dependencies.

## Evidence

- `src/orbit/security/basic.py`
- `src/orbit/security/contracts.py`
- `orbit-security` sibling workspace: `src/orbit_security/ratelimit.py`
- `orbit-auth-jwt` sibling workspace: `src/orbit_auth_jwt/verifier.py`
- `docs/security/overview.md`
- `docs/architecture/core-and-plugin-ownership.md`

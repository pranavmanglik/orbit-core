# ADR 0026: Separate the authentication capability from cross-cutting security controls

- Status: Accepted
- Date: 2026-10-06

## Context

The earlier design grouped Basic Auth, identity and token models, authorization, OAuth/OIDC contracts,
and HTTP rate limiting under `orbit-security`. Authentication has its own cohesive provider-neutral
user-facing capability, with JWT, OAuth2/OIDC, and RBAC integrations that depend on that contract.
Rate limiting is a cross-cutting HTTP control and does not need to own authentication models.

The selected package naming convention is `orbit-{parent}-{package}` for child integrations.

## Decision

Create and maintain `orbit-auth` as the provider-neutral authentication and authorization capability.
It owns Basic and bearer authenticators, identity/principal/token models, validation and revocation
contracts, JWKS and OAuth/OIDC contracts, and generic role/policy authorization.

Use the following package family:

- `orbit-auth` — capability contracts and provider-neutral behavior.
- `orbit-auth-jwt` — PyJWT verification adapter implementing `orbit-auth`'s token verifier contract.
- `orbit-auth-oauth2` — authorization-code/PKCE flow integration over `orbit-auth` contracts.
- `orbit-auth-rbac` — optional role-to-permission integration in the authentication/authorization family.
- `orbit-security` — cross-cutting security controls, currently bounded in-process HTTP rate limiting.

Core remains independent of both packages. It provides only generic request-context, route metadata,
and authorizer extension hooks. `orbit-admin` directly depends on `orbit-auth` for auth behavior and
`orbit-security` only for the rate limiter it uses.

## Consequences

- Applications can install auth without installing unrelated security controls, or rate limiting
  without installing authentication implementations.
- The three auth child packages depend on the `orbit-auth` capability package, and their names and
  Python import roots follow the parent package.
- The earlier security-package ownership decisions in ADRs 0015–0018 and 0022 are superseded. They
  remain historical records; current ownership is documented here and in the security guide.
- This package split does not imply a stable release: packages remain pre-alpha and require their own
  compatibility, security, packaging, and hosted CI gates.

## References

- [Core/plugin ownership](../core-and-plugin-ownership.md)
- [Security and authentication guide](../../security/overview.md)
- [`orbit-auth` implementation](../../../../orbit-auth/src/orbit_auth/)
- [`orbit-security` implementation](../../../../orbit-security/src/orbit_security/)

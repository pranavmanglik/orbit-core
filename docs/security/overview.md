# Security and authentication boundaries

Orbit splits authentication from cross-cutting request security so applications can install only the
capabilities they use.

## Authentication capability

Install `orbit-auth` for provider-neutral authentication and authorization contracts and implementations.
It provides explicit Basic and bearer authenticators, principal and token models, validation and
revocation interfaces, JWKS and OAuth/OIDC contracts, and role/policy authorization. Core supplies
only generic hosting hooks: request context, route requirement metadata, and the `RouteAuthorizer`
protocol. Core does not authenticate users or evaluate authorization policies.

Basic Auth is opt-in. Credentials are explicitly configured and stored as salted PBKDF2-HMAC-SHA256
hashes; no default accounts or plaintext password storage are provided. Verification is bounded and
runs outside the event loop. TLS is required by default. When TLS terminates at a proxy, trust only
known proxy hops and configure forwarded-header handling deliberately. Obtain credentials from a
secret manager rather than source control.

Basic Auth has no account lifecycle, password reset, MFA, federation, rotation workflow, or persistent
credential backend. Treat it as a simple development or administration option, not a complete
multi-user identity system. Applications are responsible for credential provisioning, rotation,
recovery, and deployment policy.

## Optional authentication integrations

- `orbit-auth-jwt` provides JWT signature verification through PyJWT and implements `orbit-auth`'s
  `TokenVerifier` contract.
- `orbit-auth-oauth2` provides the provider-neutral authorization-code and PKCE flow contract.
- `orbit-auth-rbac` provides an optional exact role-to-permission evaluator.

These packages are separately installed. Provider-specific identity integrations, key retrieval and
rotation, token persistence, sessions, and external credential stores remain separate deployment
choices. Do not treat protocol models alone as a live identity-provider integration.

## Cross-cutting security controls

`orbit-security` currently provides bounded, in-process HTTP rate limiting and its middleware. Its
quotas are process-local; each worker has independent buckets. It is not a distributed quota service
or an authentication package. Shared quotas require a separately selected backing capability and
adapter.

## Authorization behavior

Configure an `orbit-auth` `RouteAuthorizer` when an application protects routes. Protected routes
fail closed when no authorizer is configured. Unknown policies and anonymous callers are denied by
default. Keep role, permission, issuer, audience, and scope values bounded and free of control
characters. Authorization inputs must come from a trusted authenticator; a matching attribute on an
arbitrary request object is not proof of identity.

Token revocation remains process-local unless the application supplies a shared store. Provider
adapters must document clock skew, key rotation, failure behavior, credential sources, logging
redaction, and audit events. Never log authorization headers, tokens, cookies, private keys, or full
provider responses.

## Admin access

Core has no Admin HTTP surface. Install `orbit-admin` for operator routes. Its Python package depends
directly on `orbit-auth` for authentication and authorization contracts and on `orbit-security` for
cross-cutting rate limiting, alongside the required Core, data, and SQL capabilities. Database provider
packages remain explicit application choices.

## Operational scope

Local contract tests do not certify identity-provider behavior, cryptographic deployments, secret
management, proxy configuration, or production policy. Review each package's security guide and test
its integrations against the identity provider and deployment configuration actually used.

# Architecture Decision Records

Architecture Decision Records (ADRs) capture decisions that change a Core convention, dependency
direction, public contract, or extension model. They are the durable explanation for why a design
looks the way it does, especially when a future implementation could appear simpler but violate
ownership or failure guarantees.

## When to add an ADR

Write an ADR before merging a change that introduces a new public subsystem, changes lifecycle or
concurrency semantics, adds a dependency, changes the plugin boundary, or alters hosting and
deployment behavior. Small bug fixes belong in code comments and changelog entries instead.

## Required sections

Each ADR should state the status and date, the problem, the decision, alternatives considered when
they materially affect the trade-off, and consequences. Include migration or compatibility notes
when existing plugins or applications could observe the change. Link the relevant tests and guides;
an ADR explains the decision, while the guide explains how to use it.

## Current decisions

- [Core runtime contracts](0001-core-runtime-contracts.md)
- [Runtime ownership and concurrency](0002-runtime-ownership.md)
- [Unified Uvicorn and Gunicorn hosting](0003-unified-hosting.md)
- [Orbit-owned forwarded identity](0004-orbit-owned-forwarded-identity.md)
- [Native ASGI boundary](0005-native-asgi-boundary.md)
- [Capability and provider-plugin layering](0006-capability-provider-plugin-layering.md)
- [Core SQL capability and SQLite baseline (superseded)](0007-core-sqlite-capability.md)
- [Provider-neutral SQL repository conflicts](0008-sql-repository-conflicts.md)
- [Optional structured logging](0009-optional-structured-logging.md)
- [Optional development configuration watching](0010-optional-configuration-watching.md)
- [Optional HTTP gateway middleware](0011-optional-http-gateway-middleware.md)
- [Optional HTTP rate-limiting middleware](0012-optional-http-rate-limiting.md)
- [Optional ASGI test client](0013-optional-asgi-test-client.md)
- [Core-owned OpenAPI generation](0014-core-owned-openapi.md)
- [Core security baseline and optional policy package (superseded)](0015-core-security-package-boundary.md)
- [Orbit Security variants above the Core baseline (superseded)](0016-security-variants.md)
- [One optional Orbit Security package (superseded)](0017-single-security-package.md)
- [Orbit Security installation extras (superseded)](0018-security-installation-extras.md)
- [Optional RBAC permission capability](0019-optional-rbac-permissions.md)
- [Local gRPC process plugin host](0020-local-grpc-process-plugin-host.md)
- [Capability SDK and language variant policy](0021-capability-sdk-and-language-variant-policy.md)
- [Move database and authentication capabilities out of Core (authentication boundary superseded)](0022-extract-database-and-authentication.md)
- [Framework-independent RBAC subject contract](0023-framework-independent-rbac-subject.md)
- [Private ASGI harness for Core integration tests](0024-private-core-asgi-test-harness.md)
- [Admin capability boundary](0025-admin-capability-boundary.md)
- [Authentication capability and cross-cutting security boundary](0026-auth-capability-boundary.md)

ADRs describe the pre-release Core policy and do not certify a provider plugin or a deployment.

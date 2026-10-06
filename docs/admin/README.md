# Orbit Admin

Core does not implement, configure, or automatically mount Admin routes. Install the Python
package from [`orbit-admin`](../../../orbit-admin/python/README.md) to add protected operations
views and explicitly configured repository CRUD routes. The package uses Core's stable routing,
lifecycle, `AdminContribution`, authentication, and authorization contracts; `orbit-security`,
`orbit-data`, and `orbit-sql` are direct package dependencies.

`AdminPlugin(resources)` registers the operations console and CRUD routes. Operations include a
per-process bounded rate limit, role metadata (`orbit.admin.read` and `orbit.admin.write`), CSRF
checks for mutations, no-store response headers, and a bounded payload-free audit sink. Core no
longer has `admin_enabled`, an Admin route dispatcher, Admin audit history, or a rate limiter.

Use `AdminPlugin(resources, operations=False)` when only the explicit CRUD routes are needed, or
register `AdminOperationsPlugin` when the operations console is needed without resource CRUD.
Every protected route still requires a configured authenticator and `RouteAuthorizer`; routes fail
closed when either is missing. No credentials are provisioned by default. Basic Auth is opt-in,
requires TLS by default, and uses salted adaptive hashes. Do not store plaintext passwords or
commit credentials. Production use requires protected secret provisioning, trusted TLS termination,
credential rotation, and review of whether static-user Basic Auth fits the deployment.

The Python package offers payload-free in-process audit history by default or an optional
`SQLAdminAuditLog` backed by the application-owned `SQLDatabase`. SQL audit writes run in their own
transaction after resource CRUD; the repository contract cannot yet atomically commit a resource
mutation and audit entry together. Audit storage is bounded but not tamper-evident. Live MySQL and
PostgreSQL audit operation and hosted release evidence remain open.

The operations console reads Core state through `Application` and the stable Admin contribution
inspection contract. Contribution inspection is bounded by Core's configured health deadline and
cancellation-resistant work is detached under Core lifecycle ownership. HTML output escapes values;
configuration uses Core's secret-aware inspection. Mutation routes require explicit non-browser
authorization and reject requests carrying an Origin header.

Core tests verify the generic `AdminContribution` lifecycle contract. The Admin package owns the
HTTP route, auth, audit, and CRUD tests. See the Admin repository README for the current endpoint
list and limits; locally passing tests are not a production certification.

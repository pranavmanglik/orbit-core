# ADR 0021: Capability SDK and language variant policy

Status: Accepted for pre-release ecosystem development. Date: 2026-10-05.

## Context

Orbit uses Python Core and a versioned gRPC/Protocol Buffers process boundary for separately
installed non-Python implementations. A polyglot architecture does not require every capability to
ship every language, and a generated client library alone does not provide a working plugin. SDKs
and process variants add runtime dependencies, upgrade coordination, support work, serialization,
and lifecycle failure modes. They can also reduce domain-specific overhead or give package users a
native development interface.

## Decision

- Keep each capability's stable, provider-neutral user-facing contract in its Python capability
  package. Publish its `.proto` schema and Python bindings when cross-process use is supported.
- Add a language SDK in the capability's own language-specific distribution when that SDK makes
  application integration or plugin authoring materially safer or more efficient. Do not create a
  universal second-language SDK in Core and do not require SDKs for every capability.
- Add a separately named language variant only when the package has a concrete domain fit. Preserve
  the Python package, require explicit app selection, and keep provider credentials, transport,
  vendor dependencies, and vendor failure mapping in provider adapters.
- Require executable cross-language conformance tests before calling a process variant supported.
  Compare representative end-to-end workloads, including Core conversion, IPC, Protobuf, startup,
  throughput, tail latency, and memory before making performance claims or recommending the
  alternate runtime.
- Keep a package-specific cost or performance result separate from ecosystem API compatibility and
  do not claim that use of Rust, Go, or TypeScript alone improves application performance.

## First application: stream processing

The bounded `orbit.streams.v1.BatchProcessor` contract is published by `orbit-streams`. Its Python
`ProcessStreamProcessor` adapts the contract to Core's process host, and `orbit-streams-rust` supplies
a separately installable Rust SDK and example plugin. Applications explicitly choose the Python
in-process pipeline or the Rust process implementation. The Rust package's presence is not evidence
of an end-to-end speedup; representative benchmarks and broader conformance remain release gates.

## Consequences

This allows package-appropriate alternatives while avoiding a mandatory polyglot maintenance tax.
Core stays Python and capability contracts stay provider-neutral. Each SDK and adapter must still
follow its own language's version, security, packaging, documentation, and test policy.

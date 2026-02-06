<!--
Sync Impact Report:
- Version change: unspecified → 1.0.0
- Modified principles: none (initial constitution added)
- Added sections: Core Principles, Additional Constraints, Development Workflow, Governance
- Removed sections: none
- Templates requiring updates: ✅ .specify/templates/plan-template.md
	✅ .specify/templates/spec-template.md
	✅ .specify/templates/tasks-template.md
- Follow-up TODOs: none
-->

# OpenVMM Constitution

## Core Principles

### Security & Trust Boundaries (NON-NEGOTIABLE)
All code in this repository MUST uphold explicit trust boundaries. Components MUST NOT trust untrusted inputs (guests, root, or external inputs). Code MUST avoid panics across trust boundaries and MUST treat malformed input as potentially adversarial. Use of `unsafe` is PROHIBITED unless accompanied by a short, reviewed justification and auditable safety proofs in code comments and tests.

Rationale: OpenVMM and OpenHCL operate on and with untrusted inputs; preventing undefined behavior and panics is fundamental to the project's security guarantees.

### Test-First Discipline
All new features and fixes MUST include automated tests. Unit tests MUST accompany public library APIs; integration tests are REQUIRED for cross-crate contracts, platform-specific behavior, and hypervisor interactions. Use `cargo nextest` where available. Tests MUST be authored to fail before implementation (red → green → refactor).

Rationale: Fast, reliable tests prevent regressions across the large, cross-platform codebase and enforce trust boundaries via reproducible verification.

### Modular, Library-First Design
Functionality SHOULD be implemented as small, well-documented libraries/crates with clear public APIs. Crates MUST have documented purpose, public interface tests, and minimal surface area. Avoid monolithic crates where a smaller, well-scoped crate is possible.

Rationale: Modular design improves reviewability, testability, and reuse across OpenVMM and OpenHCL.

### Reproducible Builds & Cross-Platform Support
Builds MUST be reproducible and support the project's documented cross-compilation workflows. CI and developer tooling (e.g., `xtask`, `flowey`) MUST be used to restore and build artifacts. Platform-specific behavior MUST include tests or documented tolerances.

Rationale: OpenVMM targets multiple architectures; reproducible builds and explicit cross-build procedures reduce platform-specific bugs.

### Observability, Simplicity & Minimal Dependencies
Code MUST prefer simple, auditable implementations. Structured logging and diagnostic strings MUST be present for performance/security incidents. Avoid adding heavy dependencies; prefer lib-by-default solutions and document reasons for any new dependency.

Rationale: Simpler codebases are easier to audit for security and correctness; structured diagnostics accelerate incident response.

## Additional Constraints

- Follow Rust project conventions in this repository: `cargo xtask` usage for cross-workflow automation, `rustfmt` for formatting, and `clippy` for linting. Formatting checks MUST pass before merging.
- Do not add networked telemetry or external data collection without explicit governance approval.
- Respect item size limits and performance constraints for components interacting with guests; avoid embedding excessively large data structures in items passed across trust boundaries.

### Save State Guarantees

Components that implement save & restore semantics (save state) MUST follow these guarantees derived from the Developer Guide:

- **Forward & Backward Compatibility**: Save state formats MUST be designed to be readable by newer versions and not cause crashes when older versions encounter newer save state. Breaking changes are disallowed once save state reaches a released, in-use branch.
- **ProtoBuf Encoding**: All save state MUST be encoded using Protocol Buffers (`mesh`) per the repository guide.
- **Moduleization & Packages**: Save state definitions MUST live in their own module and use a unique `mesh` package per crate to simplify review and evolution.
- **Safe Field Choices**: Avoid plain arrays and enums for evolving fields; prefer `Option<T>` or `Vec<T>` to enable safe extension. Choose default values that make semantic sense; use `Option` when absence must be distinguishable.
- **Review for Changes**: Extending saved state MUST include a clear compatibility note, migration plan if needed, and tests demonstrating old->new and new->old behavior when practical.

Rationale: Save & restore primitives are critical to runtime servicing and updates; explicit guarantees prevent live-site data loss and compatibility regressions.

## Development Workflow

- Contributions MUST follow the repository `README.md` and contributing guidelines, including CLA and code of conduct.
- Pull Requests that change public behavior (APIs, contract formats, guest-visible behavior) MUST include: design rationale, compatibility notes, tests, and a migration plan if applicable.
- Reviewers MUST verify constitution compliance for security, tests, documentation, and `unsafe` usage before approval.

### Documentation & Guides

Documentation is as important as tests and MUST be delivered alongside code changes that affect APIs, behavior, tooling, or high-level design. Requirements:

- **API rustdoc**: Public APIs MUST include `rustdoc` comments with at least one minimal, copy‑pasteable example demonstrating intended use. Examples SHOULD compile as doctests when practical.
- **Module rationale**: Each crate/module with non-trivial behavior MUST include module-level `rustdoc` explaining the design rationale and high-level invariants.
- **Guide inclusion**: High-level concepts, user-facing workflows, or new developer tools MUST be reflected in the repository `Guide/` (Guide/src/) as part of the PR. New dev tools MUST include a short Guide page explaining installation, usage, and CI integration.
- **Docs parity with tests**: PRs that change behavior MUST include both tests and documentation updates; missing docs are grounds for review rejection.

Rationale: Clear documentation accelerates secure contributions, reduces onboarding friction, and ensures that design intent accompanies implementation.

Style note: Documentation MUST be concise and precise — prefer runnable code examples and clear design rationale. Let the code do the talking: keep prose minimal and focused on intent, invariants, and examples.

## Governance

- Amendment procedure: Changes to this constitution are made by PR targeting the repository. Amendments that add new principles or materially change definitions constitute a MINOR version bump; wording clarifications and typo fixes are PATCH bumps. Removing or re-defining principles in a backward-incompatible way requires a MAJOR version bump and a documented migration plan.
- Versioning policy: Semantic versioning applied to the constitution itself. The `Version` field in this document MUST be updated with every amendment. Dates MUST use ISO format `YYYY-MM-DD`.
- Compliance reviews: The repository stewards or appointed maintainers will perform periodic compliance reviews and may require follow-up tasks for non-compliant changes.

**Version**: 1.0.0 | **Ratified**: 2026-02-06 | **Last Amended**: 2026-02-06

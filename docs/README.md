# InferenceBenchRunner System Design Documentation

This folder contains the complete system design for the inference benchmarking platform.

## Quick Navigation

- **[GETTING_STARTED.md](./GETTING_STARTED.md)** — How to use this documentation and refine the design
- **[system-design.md](./system-design.md)** — Main visual-first system design (start here)

## Contents

### Design Documents

- `system-design.md` — Complete system overview with 10 sections:
  1. C4 Context Diagram (actors, external systems)
  2. Component Architecture (internal structure)
  3. Data Flow (how data moves through system)
  4. Run Execution Lifecycle (state machine)
  5. Deployment Architecture (Docker Compose)
  6. Metrics Ports by Engine (reference table)
  7. API Surface (routes, WebSocket)
  8. Key Design Decisions (links to ADRs)
  9. Build Phase Order (implementation sequence)
  10. Environment Variables

### Architecture Diagrams

All diagrams are in `architecture/` folder as Excalidraw files (`.excalidraw`):
- `c4-context.excalidraw` — High-level context
- `component-diagram.excalidraw` — Internal components
- `data-flow.excalidraw` — Data movement during execution
- `run-lifecycle.excalidraw` — State machine visualization
- `deployment-architecture.excalidraw` — Docker Compose topology

See `architecture/README.md` for editing and export instructions.

### Architecture Decision Records

All decisions documented in `adr/` folder:
- `0001-enginedriver-abstraction.md` — Why an abstraction layer for engines
- `0002-storage-split-sqlite-victoriametrics.md` — Why two databases
- `0003-otel-sidecar-per-run.md` — Why per-run OTel sidecars
- `0004-ssh-based-remote-spawning-v1.md` — Why SSH-based remote spawning

See `adr/TEMPLATE.md` for how to write new ADRs.

## Status

- **Phase:** Design (Phase 1 code hasn't started)
- **Completeness:** Complete for Phase 1
- **Last Updated:** 2026-03-31

## For Code Reviewers

When Phase 1 code is submitted:
1. Reference the relevant sections in `system-design.md`
2. Check ADRs for design rationale
3. Verify implementation matches diagrams
4. Update diagrams if implementation differs from design

## Iteration & Updates

To refine the design:
1. Edit `.excalidraw` files in Excalidraw editor (or online at excalidraw.com)
2. Export to PNG when stable
3. Update markdown docs as needed
4. Commit both source and rendered versions

See [GETTING_STARTED.md](./GETTING_STARTED.md) for detailed instructions.

---

*InferenceBenchRunner System Design — Visual-first, decision-documented approach*

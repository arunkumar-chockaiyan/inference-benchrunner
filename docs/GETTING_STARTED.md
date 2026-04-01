# Getting Started with System Design

## 📋 Structure Overview

```
docs/
├── system-design.md              # Main system design document (START HERE)
├── GETTING_STARTED.md            # This file
├── architecture/                 # Excalidraw diagrams
│   ├── README.md                 # Diagram editing guide
│   ├── c4-context.excalidraw
│   ├── component-diagram.excalidraw
│   ├── data-flow.excalidraw
│   ├── run-lifecycle.excalidraw
│   ├── deployment-architecture.excalidraw
│   └── rendered/                 # PNG exports (generate as needed)
│       └── .gitkeep
└── adr/                          # Architecture Decision Records
    ├── 0001-enginedriver-abstraction.md
    ├── 0002-storage-split-sqlite-victoriametrics.md
    ├── 0003-otel-sidecar-per-run.md
    ├── 0004-ssh-based-remote-spawning-v1.md
    └── TEMPLATE.md               # For writing new ADRs
```

## 🚀 Quick Start

### 1. Read the System Design

Start with [`system-design.md`](./system-design.md). It's a visual-first guide:
- C4 context (actors + external systems)
- Component architecture (internal structure)
- Data flow (how data moves)
- Run lifecycle (state machine)
- Deployment (Docker Compose)
- API surface
- Build phases

### 2. Explore Diagrams

Open any `.excalidraw` file:

**Online (no download):**
- Visit [excalidraw.com](https://excalidraw.com)
- File → Open → select `.excalidraw` file from `docs/architecture/`
- Edit, then File → Save (overwrites `.excalidraw`)

**Desktop (recommended):**
- Install [Excalidraw app](https://excalidraw.com/app) (also available for Mac/Linux/Windows)
- Drag `.excalidraw` file into the app
- Edit and save

**VS Code:**
- Install "Excalidraw" extension
- Open any `.excalidraw` file in the editor

### 3. Export Diagrams to PNG

Once you edit a diagram and want to share it:

1. In Excalidraw editor: File → Export → PNG
2. Save to `docs/architecture/rendered/` (e.g., `c4-context.png`)
3. Commit both the source (`.excalidraw`) and rendered (`.png`) versions

**Why both?**
- `.excalidraw` is editable source (git-friendly, diffs work)
- `.png` is for quick viewing without opening the editor

### 4. Review Architecture Decisions

Read [`adr/`](./adr/) folder. Each ADR file explains:
- **Problem:** What we're solving
- **Decision:** What we chose and why
- **Consequences:** Trade-offs
- **Alternatives:** What we rejected and why

Format: `NNNN-slug.md` (e.g., `0001-enginedriver-abstraction.md`)

## ✏️ How to Refine

### If you want to update a diagram:

1. Open `.excalidraw` file in Excalidraw
2. Edit (add boxes, arrows, labels)
3. Save the file (Ctrl+S or File → Save)
4. Export as PNG to `rendered/`
5. Commit both files

### If you want to add a new decision:

1. Copy `adr/TEMPLATE.md` → `adr/NNNN-slug.md`
2. Fill in the template
3. Reference it in `system-design.md` section 8

### If you want to update the system design doc:

1. Edit `system-design.md`
2. Update diagram references if needed
3. Add new sections as needed

## 🔄 Iteration Loop

**Refining the design before implementation:**

1. **Review diagrams** — Do they match your mental model?
2. **List open questions** — What's unclear? (add to your notes)
3. **Identify risks** — What could go wrong? (add to feedback)
4. **Check completeness** — Which areas need more detail?
5. **Update docs** — Add clarifications, fix diagrams
6. **Iterate** — Repeat until confident

**Before starting Phase 1 (coding):**
- All diagrams should be reviewed and stable
- All ADRs should be written
- Build order is confirmed
- Team alignment on architecture

## 📝 Next Steps

1. Read `system-design.md` (10 min)
2. Open each `.excalidraw` file and review (5 min each)
3. Read the 4 ADRs (10 min each)
4. Identify any gaps or questions
5. Update diagrams/docs as needed
6. Mark as ready for Phase 1 once confident

## 🎯 Success Criteria

You're ready to start Phase 1 when:
- ✅ All diagrams match your vision
- ✅ All major decisions are documented (ADRs)
- ✅ Build order is clear and sequenced
- ✅ Metrics, API routes, and data flow are well understood
- ✅ Storage/infra strategy is agreed upon

---

**Questions?** Check the referenced sections in `system-design.md` or dive into the relevant ADR.

*Generated 2026-03-31*

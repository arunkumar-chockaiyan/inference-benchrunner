# ADR-0004: SSH-Based Remote Engine Spawning (v1 Architecture)

**Date:** 2026-03-31
**Status:** Superseded by ADR-0005

This ADR described an SSH + asyncssh + nohup approach for remote engine spawning.
It was superseded before implementation. The actual architecture uses a lightweight
FastAPI agent over Tailscale — see ADR-0005.

**Why superseded:**
- asyncssh process management via nohup is fragile (no structured lifecycle, hard to clean up)
- SSH credentials on the benchmarking host are a security concern
- The "v2 upgrade path" described in this ADR (REST-based agent) proved to be the right
  first design, not a future upgrade — it was adopted immediately as Phase 1
- Tailscale provides secure network-level access control without SSH key distribution

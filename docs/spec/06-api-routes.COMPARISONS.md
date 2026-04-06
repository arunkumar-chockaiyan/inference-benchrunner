# Comparison Validation — Phase 1

## Constraint: Same Suite

When saving a comparison (`POST /api/comparisons`), all `run_ids` must use the same `PromptSuite`.

**Why:** Comparisons are meaningful only when the workload is identical (same prompts, same order). This prevents nonsensical cross-workload comparisons at save time.

**Validation logic** (in `backend/routers/comparisons.py`):
1. Fetch all Run objects for the provided `run_ids`
2. Extract the suite_id from each Run's config
3. Raise 422 if more than one suite_id is found

**Error response:**
```json
{
  "detail": "All runs must use the same PromptSuite. Found 2 different suites: {uuid1, uuid2}"
}
```

## API Design

- `/api/runs/compare` (ad-hoc) — accepts any runs for real-time stats
- `POST /api/comparisons` (saved) — enforces same-suite constraint

This keeps the ad-hoc API flexible while preserving semantics of persisted comparisons.

## Future: Cross-Suite Comparisons

See `docs/spec/12-phase3.md` for discussion on when/how to lift this constraint.

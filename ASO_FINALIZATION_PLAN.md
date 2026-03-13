# ASO Service Finalization Plan (Publish Stabilization Wave)

## Summary
This wave focuses on deterministic Google publish safety and visibility. The objective is to prevent invalid API calls, normalize failure reasons, and ensure operators can clearly see why an item was published, blocked, or failed.

## Implemented Stabilization Scope
- Added `Suggestion.extra_data` to persist review metadata (including `review_id`) for review-reply publishing.
- Added migration `008`:
  - schema: `suggestions.extra_data` (default `{}`)
  - data safety: blocks legacy `review_reply` suggestions (`pending`/`approved`) that lack `review_id`.
- Pipeline now stores review metadata in suggestions during creation.
- Review reply publish now hard-blocks missing/invalid `review_id` and never calls Google in that path.
- Listing publish now:
  - resolves default language dynamically (no hardcoded `en-US`)
  - merges required listing fields safely using current listing fallback
  - blocks commit if default-language title is still missing.
- Google publish errors are normalized for operator clarity:
  - `missing_review_id`
  - `missing_default_language_title`
  - `google_api_not_found`
  - `google_api_forbidden`
- Publish outcome propagation tightened so `blocked` remains `blocked` (not misreported as generic `failed`).
- Suggestions API now surfaces additional diagnostics:
  - `publish_error_code`
  - `review_id` (for review-reply rows)
  - parsed `extra_data` (review-reply context)

## Test Gates
- Focused tests for this wave:
  - missing `review_id` is blocked before any Google call
  - valid `review_id` path uses correct `reviewId`
  - listing publish uses resolved default language and safe title fallback
  - missing default-language title is blocked with standardized code
  - blocked provider outcomes stay blocked in suggestion state
- Mandatory before release:
  1. Full `pytest` pass
  2. Controlled smoke runs (dry-run publish flow)
  3. Optional live-safe verification only when credentials + mode allow

## Rollout Notes
- Keep `dry_run=true` during final validation unless explicitly switching to live mode.
- Keep manual approval enabled while validating publish outcomes.
- If previously blocked legacy review replies appear, regenerate via new pipeline run so valid `review_id` metadata is attached.

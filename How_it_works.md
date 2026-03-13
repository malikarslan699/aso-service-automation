# How ASO Service Works

## 1. Project ownership and access

- `admin` is the system owner and can see every project.
- Each `sub-admin` can create their own independent projects.
- `admin` can also assign any project to any sub-admin.
- Assigned visibility does not transfer ownership.

This means a sub-admin can have:
- their own projects
- admin-assigned projects

The project selector in the left sidebar is now the main place to:
- switch projects
- search visible projects
- add a new project

## 2. Main setup flow

1. Open the project selector from the left sidebar.
2. Create a project there if it does not exist yet.
3. Select the project.
4. Go to `Settings`.
5. Upload the Google Play service account JSON for that project.
6. Check provider health until Google Play and your AI provider are healthy.
7. Add verified app facts so AI only uses supported claims.
8. Use `Run now` from the Dashboard.
9. Review suggestions in `Approvals`.

## 3. Provider health and why “Connected” was not enough

The system now separates:
- API reachable
- real inference healthy
- billing blocked
- model access blocked
- provider error

This matters because an API key can still show usage or recent cost while real generation fails.

### Anthropic

- Primary AI provider.
- A green state means a real `messages` inference call worked.
- If billing or model access is blocked, the panel shows that explicitly.

### OpenAI

- Optional fallback provider.
- Used only when Claude inference fails and `openai_api_key` is configured.

### Google Play

- Uses project-level service account JSON.
- Needed for listing, reviews, and publish actions.

### Telegram and SerpAPI

- Telegram is for notifications.
- SerpAPI is optional external signal support.

## 4. Pipeline stages

Every run now stores a step-by-step trace:

1. `Queue accepted`
2. `Run started`
3. `App data fetch`
4. `Keyword discovery`
5. `Duplicate filtering`
6. `AI generation`
7. `Approval creation`
8. `Publish eligibility check`
9. `Finalization`

Each step shows:
- status
- timestamps
- short message
- provider if used
- token usage if available
- estimated cost if available

So if a run stops after keyword discovery, the Dashboard should clearly show:
- keyword discovery succeeded
- AI generation failed or returned zero
- Approvals stayed empty because no valid suggestions were created

## 5. Demo mode vs Live mode

### Demo mode

- Safe for testing.
- Pipeline, approvals, and tracking still run.
- Real publish actions should not go live.
- Approved items will finish as `Dry Run Only` when the simulated publish completes.

### Live mode

- Approved actions can move into real publish behavior.
- Listing metadata (`title`, `short_description`, `long_description`) does not send instantly on each approve.
- Instead, approved listing fields merge into one paced **listing bundle job**.
- Use only after:
  - Google Play is healthy
  - provider inference is healthy
  - manual approval flow has already been validated
- A real success is shown as `Published on Google` with timestamp.

## 6. Publish-state visibility

Every suggestion now has two operator-facing states:
- `review_status`
- `publish_status`

### Review state

- `Pending Review`
- `Approved`
- `Rejected`
- `Rolled Back`

### Publish state

- `Approved (Ready to Publish in Google)`
- `Queued in Listing Bundle`
- `Waiting Safe Window`
- `Publishing to Google`
- `Published on Google`
- `Dry Run Only`
- `Blocked`
- `Failed`
- `Superseded`

Each suggestion card also stores a six-stage timeline:
1. `Created by pipeline`
2. `Reviewed manually`
3. `Queued for publish`
4. `Waiting safe window`
5. `Publish attempted`
6. `Publish result`

This lets an operator see whether an item is:
- only approved
- still simulated in dry-run mode
- queued for a live send
- actually published on Google Play
- blocked by limits or missing credentials

## 6.1 Compliance-safe listing merge behavior

- Listing approvals are merged by field (`latest approved wins`).
- Old approved variants for the same field are marked `Superseded` (history kept).
- Bundle dispatch is policy-paced:
  - safe UTC window
  - randomized jitter
  - hard minimum gap between listing sends
  - separate listing day/week caps
- If blocked (limits, cooldown, policy/credential guard), nothing auto-bursts.
- Admin retry is explicit and re-enters the same paced queue.

## 7. Cost and value interpretation

Each pipeline run now stores:
- provider used
- fallback provider used or not
- input tokens
- output tokens
- estimated provider cost
- keywords discovered
- suggestions generated
- approvals created
- value summary

This is the right way to judge whether small spend like `$0.14` was useful.

If a run spent money but produced:
- `0 suggestions`
- `0 approvals`
- only keyword discovery

then the Dashboard should make that visible immediately.

## 8. Sub-admin management

The `Sub Admins` page is now the source of truth for team management.

It handles:
- create sub-admin
- unique username validation
- optional email
- password edit
- on/off access toggle
- delete with confirmation
- assigned project editing
- assigned project visibility

Settings should not duplicate team management.

## 9. Testing mode defaults

Until provider behavior is stable, recommended defaults are:

- `dry_run = true`
- `manual_approval_required = true`
- `publish_after_approval = true`
- `manual_trigger_cooldown_minutes = 0` while testing
- `listing_publish_min_gap_minutes >= 60`
- `listing_publish_max_per_day = 1 or 2`
- `listing_publish_max_per_week <= 5`

Before production, restore a non-zero cooldown.

## 10. Progress tracking

`PROJECT_PROGRESS.txt` is the working tracker file.

It must always contain:
- progress bar
- percentage
- completed tasks
- remaining tasks
- current blocker
- last updated time

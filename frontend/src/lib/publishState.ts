export type SuggestionRecord = {
  id: number
  status: string
  review_status?: string
  publish_status?: string | null
  publish_message?: string | null
  published_live?: boolean
  is_dry_run_result?: boolean
}

export function getReviewBadge(reviewStatus?: string) {
  switch (reviewStatus) {
    case "approved":
      return { label: "Approved", classes: "text-green-700 bg-green-50 border-green-200" }
    case "rejected":
      return { label: "Rejected", classes: "text-red-700 bg-red-50 border-red-200" }
    case "rolled_back":
      return { label: "Rolled Back", classes: "text-red-700 bg-red-50 border-red-200" }
    case "superseded":
      return { label: "Superseded", classes: "text-slate-700 bg-slate-50 border-slate-200" }
    default:
      return { label: "Pending Review", classes: "text-slate-700 bg-slate-50 border-slate-200" }
  }
}

export function getPublishBadge(suggestion: SuggestionRecord) {
  const status = suggestion.publish_status

  switch (status) {
    case "ready":
      return { label: "Approved (Ready to Publish in Google)", classes: "text-amber-700 bg-amber-50 border-amber-200" }
    case "queued":
      return { label: "Queued for Google Publish", classes: "text-blue-700 bg-blue-50 border-blue-200" }
    case "queued_bundle":
      return { label: "Queued in Listing Bundle", classes: "text-blue-700 bg-blue-50 border-blue-200" }
    case "waiting_safe_window":
      return { label: "Waiting Safe Window", classes: "text-amber-700 bg-amber-50 border-amber-200" }
    case "publishing":
      return { label: "Publishing to Google", classes: "text-blue-700 bg-blue-50 border-blue-200" }
    case "published":
      return { label: "Published on Google", classes: "text-green-700 bg-green-50 border-green-200" }
    case "dry_run_only":
      return { label: "Dry Run Only", classes: "text-amber-700 bg-amber-50 border-amber-200" }
    case "blocked":
      return { label: "Blocked", classes: "text-red-700 bg-red-50 border-red-200" }
    case "failed":
      return { label: "Failed", classes: "text-red-700 bg-red-50 border-red-200" }
    case "superseded":
      return { label: "Superseded", classes: "text-slate-700 bg-slate-50 border-slate-200" }
    default:
      if (suggestion.review_status === "approved") {
        return { label: "Approved", classes: "text-amber-700 bg-amber-50 border-amber-200" }
      }
      if (suggestion.review_status === "superseded") {
        return { label: "Superseded", classes: "text-slate-700 bg-slate-50 border-slate-200" }
      }
      return null
  }
}

export function getPublishCounterKey(suggestion: SuggestionRecord) {
  switch (suggestion.publish_status) {
    case "ready":
      return "approvedReady"
    case "queued":
    case "queued_bundle":
    case "publishing":
    case "waiting_safe_window":
      return "queued"
    case "published":
      return "published"
    case "dry_run_only":
      return "dryRun"
    case "blocked":
    case "failed":
      return "blocked"
    case "superseded":
      return "blocked"
    default:
      if (suggestion.review_status === "superseded") {
        return "blocked"
      }
      return suggestion.review_status === "pending" ? "pending" : "approvedReady"
  }
}

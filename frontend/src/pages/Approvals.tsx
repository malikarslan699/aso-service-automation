import { useMemo, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { CheckCircle, XCircle, ChevronDown, ChevronUp, CircleDot, Clock3, ShieldAlert, Sparkles } from "lucide-react"
import { getPublishBadge, getPublishCounterKey, getReviewBadge } from "@/lib/publishState"

const RISK_CONFIG = {
  0: { label: "Safe", color: "text-green-600 bg-green-50 border-green-200" },
  1: { label: "Low Risk", color: "text-yellow-600 bg-yellow-50 border-yellow-200" },
  2: { label: "Medium Risk", color: "text-orange-600 bg-orange-50 border-orange-200" },
  3: { label: "High Risk", color: "text-red-600 bg-red-50 border-red-200" },
}

function RiskBadge({ score }: { score: number }) {
  const config = RISK_CONFIG[score as keyof typeof RISK_CONFIG] ?? RISK_CONFIG[3]
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${config.color}`}>
      {config.label}
    </span>
  )
}

function DiffView({ oldValue, newValue }: { oldValue: string; newValue: string }) {
  const [expanded, setExpanded] = useState(false)
  const preview = (text: string, max = 120) =>
    text.length > max ? text.slice(0, max) + "..." : text

  return (
    <div className="text-sm space-y-2">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">Before</div>
          <div className="p-2 rounded bg-red-50 border border-red-200 text-red-900 text-xs leading-relaxed">
            {expanded ? oldValue || "(empty)" : preview(oldValue || "(empty)")}
          </div>
        </div>
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">After</div>
          <div className="p-2 rounded bg-green-50 border border-green-200 text-green-900 text-xs leading-relaxed">
            {expanded ? newValue : preview(newValue)}
          </div>
        </div>
      </div>
      {(oldValue?.length > 120 || newValue?.length > 120) && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {expanded ? "Show less" : "Show full text"}
        </button>
      )}
    </div>
  )
}

export function Approvals() {
  const { selectedApp, user } = useAuth()
  const qc = useQueryClient()
  const [rejectReason, setRejectReason] = useState<Record<number, string>>({})
  const [openBatches, setOpenBatches] = useState<Record<string, boolean>>({})
  const [expandedTimeline, setExpandedTimeline] = useState<Record<number, boolean>>({})

  const { data: suggestions = [], isLoading } = useQuery({
    queryKey: ["suggestions", selectedApp?.id, "all"],
    queryFn: () =>
      api.get(`/api/v1/apps/${selectedApp?.id}/suggestions`).then((r) => r.data),
    enabled: !!selectedApp,
  })

  const approve = useMutation({
    mutationFn: (id: number) =>
      api.post(`/api/v1/apps/${selectedApp?.id}/suggestions/${id}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["suggestions"] }),
  })

  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      api.post(`/api/v1/apps/${selectedApp?.id}/suggestions/${id}/reject`, { reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["suggestions"] }),
  })

  const retryPublish = useMutation({
    mutationFn: (id: number) =>
      api.post(`/api/v1/apps/${selectedApp?.id}/suggestions/${id}/retry-publish`, { reason: "Manual retry from Approvals" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["suggestions"] }),
  })

  const batches = useMemo(() => {
    const grouped = new Map<string, any[]>()
    suggestions.forEach((suggestion: any) => {
      const key = suggestion.pipeline_run_id ? String(suggestion.pipeline_run_id) : "legacy"
      grouped.set(key, [...(grouped.get(key) || []), suggestion])
    })

    return Array.from(grouped.entries())
      .map(([key, items]) => {
        const sorted = [...items].sort((a, b) => (b.id || 0) - (a.id || 0))
        const counters = {
          pending: 0,
          approvedReady: 0,
          queued: 0,
          published: 0,
          dryRun: 0,
          blocked: 0,
        }
        sorted.forEach((item) => {
          counters[getPublishCounterKey(item) as keyof typeof counters] += 1
        })
        return {
          key,
          label: key === "legacy" ? "Legacy Suggestions" : `Run #${key}`,
          createdAt: sorted[0]?.created_at || null,
          suggestions: sorted,
          counters,
        }
      })
      .sort((a, b) => {
        const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0
        const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0
        return bTime - aTime
      })
  }, [suggestions])

  const totalPending = suggestions.filter((s: any) => s.review_status === "pending").length

  if (!selectedApp) return <div className="text-muted-foreground">Select an app first</div>
  if (isLoading) return <div className="text-muted-foreground">Loading...</div>

  const renderSuggestionCard = (s: any) => {
    const reviewBadge = getReviewBadge(s.review_status)
    const publishBadge = getPublishBadge(s)
    const timeline = s.status_log || []
    const canReview = s.review_status === "pending" && (user?.role === "admin" || user?.role === "sub_admin")
    const canRetry = user?.role === "admin" && ["blocked", "failed", "superseded", "dry_run_only"].includes(s.publish_status || "")

    return (
      <div key={s.id} className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium capitalize">{s.field_name.replaceAll("_", " ")}</span>
              <span className="text-xs text-muted-foreground">•</span>
              <span className="text-xs text-muted-foreground capitalize">{s.suggestion_type}</span>
              <RiskBadge score={s.risk_score} />
            </div>
            <div className="flex flex-wrap gap-2">
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${reviewBadge.classes}`}>
                {reviewBadge.label}
              </span>
              {publishBadge && (
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${publishBadge.classes}`}>
                  {publishBadge.label}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setExpandedTimeline((prev) => ({ ...prev, [s.id]: !prev[s.id] }))}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {expandedTimeline[s.id] ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {expandedTimeline[s.id] ? "Hide timeline" : "Show timeline"}
          </button>
        </div>

        <DiffView oldValue={s.old_value} newValue={s.new_value} />

        {s.reasoning && (
          <p className="text-xs text-muted-foreground italic border-l-2 border-border pl-2">
            {s.reasoning.slice(0, 260)}
          </p>
        )}

        {s.publish_message && (
          <div className="rounded-md border border-border/70 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            {s.publish_message}
            {s.publish_block_reason && s.publish_block_reason !== s.publish_message && (
              <div className="mt-1 text-red-600">Reason: {s.publish_block_reason}</div>
            )}
            {(s.next_eligible_at || s.dispatch_window) && (
              <div className="mt-1">
                {s.next_eligible_at && <span>Next eligible: {new Date(s.next_eligible_at).toLocaleString()}</span>}
                {s.next_eligible_at && s.dispatch_window && <span> • </span>}
                {s.dispatch_window && <span>Cadence: {s.dispatch_window}</span>}
              </div>
            )}
          </div>
        )}

        {expandedTimeline[s.id] && (
          <div className="rounded-md border border-border bg-muted/20 p-3">
            <div className="mb-3 text-xs font-medium text-foreground">Publish timeline</div>
            <div className="space-y-3">
              {timeline.map((step: any) => {
                const stepTone =
                  step.status === "completed"
                    ? "border-green-200 bg-green-50 text-green-700"
                    : step.status === "running"
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : step.status === "blocked" || step.status === "failed"
                    ? "border-red-200 bg-red-50 text-red-700"
                    : step.status === "skipped"
                    ? "border-amber-200 bg-amber-50 text-amber-700"
                    : "border-slate-200 bg-slate-50 text-slate-700"
                const Icon =
                  step.status === "completed"
                    ? CheckCircle
                    : step.status === "running"
                    ? Clock3
                    : step.status === "blocked" || step.status === "failed"
                    ? ShieldAlert
                    : CircleDot
                return (
                  <div key={`${s.id}-${step.key}`} className="flex gap-3">
                    <div className={`mt-0.5 flex h-6 w-6 items-center justify-center rounded-full border ${stepTone}`}>
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-sm font-medium">{step.label}</div>
                        <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] capitalize ${stepTone}`}>
                          {step.status}
                        </span>
                      </div>
                      {step.message && <div className="mt-1 text-xs text-muted-foreground">{step.message}</div>}
                      {(step.actor || step.completed_at || step.started_at) && (
                        <div className="mt-1 text-[11px] text-muted-foreground">
                          {[step.actor ? `Actor: ${step.actor}` : null, step.completed_at || step.started_at ? new Date(step.completed_at || step.started_at).toLocaleString() : null]
                            .filter(Boolean)
                            .join(" • ")}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {canReview && (
          <div className="flex flex-col gap-2 pt-1 sm:flex-row">
            <button
              onClick={() => approve.mutate(s.id)}
              disabled={approve.isPending}
              className="flex items-center justify-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:opacity-50"
            >
              <CheckCircle className="h-4 w-4" />
              Approve
            </button>

            <div className="flex flex-1 gap-2">
              <input
                type="text"
                placeholder="Reason for rejection..."
                value={rejectReason[s.id] || ""}
                onChange={(e) => setRejectReason((prev) => ({ ...prev, [s.id]: e.target.value }))}
                className="flex-1 rounded-md border border-input px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <button
                onClick={() => reject.mutate({ id: s.id, reason: rejectReason[s.id] || "Rejected" })}
                disabled={reject.isPending}
                className="flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 disabled:opacity-50"
              >
                <XCircle className="h-4 w-4" />
                Reject
              </button>
            </div>
          </div>
        )}

        {canRetry && (
          <div className="pt-1">
            <button
              onClick={() => retryPublish.mutate(s.id)}
              disabled={retryPublish.isPending}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent disabled:opacity-50"
            >
              Retry via paced queue
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Approvals</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {totalPending} suggestion{totalPending !== 1 ? "s" : ""} pending review
        </p>
      </div>

      {suggestions.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-muted-foreground">
          <CheckCircle className="h-12 w-12 mb-3 opacity-20" />
          <p>All caught up! No pending suggestions.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {batches.map((batch, index) => {
            const isOpen = openBatches[batch.key] ?? index === 0
            const pendingItems = batch.suggestions.filter((item: any) => item.review_status === "pending")
            const queuedItems = batch.suggestions.filter((item: any) =>
              ["approved", "rolled_back"].includes(item.review_status) &&
              ["ready", "queued", "queued_bundle", "publishing", "waiting_safe_window"].includes(item.publish_status || "ready")
            )
            const outcomeItems = batch.suggestions.filter((item: any) =>
              ["published", "dry_run_only", "blocked", "failed"].includes(item.publish_status)
            )
            const rejectedItems = batch.suggestions.filter((item: any) => item.review_status === "rejected")
            const supersededItems = batch.suggestions.filter((item: any) => item.review_status === "superseded")

            return (
              <div key={batch.key} className="rounded-xl border border-border bg-card">
                <button
                  type="button"
                  onClick={() => setOpenBatches((prev) => ({ ...prev, [batch.key]: !isOpen }))}
                  className="flex w-full flex-col gap-3 px-4 py-4 text-left sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4 text-primary" />
                      <span className="text-base font-semibold">{batch.label}</span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {batch.createdAt ? new Date(batch.createdAt).toLocaleString() : "No timestamp"}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { label: "Pending", value: batch.counters.pending, tone: "text-slate-700 bg-slate-50 border-slate-200" },
                      { label: "Ready", value: batch.counters.approvedReady, tone: "text-amber-700 bg-amber-50 border-amber-200" },
                      { label: "Queued", value: batch.counters.queued, tone: "text-blue-700 bg-blue-50 border-blue-200" },
                      { label: "Published", value: batch.counters.published, tone: "text-green-700 bg-green-50 border-green-200" },
                      { label: "Dry Run", value: batch.counters.dryRun, tone: "text-amber-700 bg-amber-50 border-amber-200" },
                      { label: "Blocked", value: batch.counters.blocked, tone: "text-red-700 bg-red-50 border-red-200" },
                    ].map((counter) => (
                      <span key={`${batch.key}-${counter.label}`} className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium ${counter.tone}`}>
                        {counter.label}: {counter.value}
                      </span>
                    ))}
                  </div>
                </button>

                {isOpen && (
                  <div className="space-y-5 border-t border-border px-4 py-4">
                    {[
                      { title: "Pending Review", items: pendingItems },
                      { title: "Approved / Publish Queue", items: queuedItems },
                      { title: "Publish Results", items: outcomeItems },
                      { title: "Superseded", items: supersededItems },
                      { title: "Rejected", items: rejectedItems },
                    ]
                      .filter((section) => section.items.length > 0)
                      .map((section) => (
                        <div key={`${batch.key}-${section.title}`} className="space-y-3">
                          <div className="text-sm font-medium">{section.title}</div>
                          <div className="space-y-3">
                            {section.items.map((item: any) => renderSuggestionCard(item))}
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

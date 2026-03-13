import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle,
  CircleDot,
  Clock,
  Key,
  Loader2,
  PlayCircle,
  Receipt,
  Sparkles,
  ExternalLink,
  XCircle,
} from "lucide-react"

import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"

type ManualRunFeedback = {
  tone: "success" | "warning" | "info" | "error"
  message: string
}

type StepLogItem = {
  key: string
  label: string
  status: "pending" | "running" | "completed" | "failed" | "skipped"
  started_at?: string | null
  completed_at?: string | null
  message?: string
  provider?: string | null
  estimated_cost?: number
  input_tokens?: number
  output_tokens?: number
}

function formatTriggerLabel(trigger?: string | null) {
  if (trigger === "manual") return "Manual run"
  if (trigger === "scheduled") return "Scheduled run"
  return "Not triggered yet"
}

function formatStatus(status: string) {
  return status.replace(/_/g, " ")
}

export function Dashboard() {
  const { selectedApp, user } = useAuth()
  const qc = useQueryClient()
  const [feedback, setFeedback] = useState<ManualRunFeedback | null>(null)
  const canRunNow = user?.role === "admin" || user?.role === "sub_admin"

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", selectedApp?.id],
    queryFn: () => api.get("/api/v1/dashboard").then((response) => response.data),
    refetchInterval: (query) => {
      const apps = (query.state.data as any)?.apps || []
      const current = apps.find((item: any) => item.app_id === selectedApp?.id) ?? apps[0]
      return ["queued", "running"].includes(current?.last_pipeline?.status) ? 5000 : 30000
    },
  })

  const runNow = useMutation({
    mutationFn: () => api.post(`/api/v1/apps/${selectedApp?.id}/pipeline/trigger`).then((response) => response.data),
    onSuccess: (result) => {
      if (result.status === "queued") {
        const modeText =
          result.workflow_mode === "manual_approval"
            ? "New suggestions will stop in Approvals."
            : "Current auto rules will continue after generation."
        setFeedback({ tone: "success", message: `${result.message} ${modeText}` })
      } else if (result.status === "blocked_running") {
        setFeedback({ tone: "warning", message: result.message })
      } else if (result.status === "blocked_cooldown") {
        const nextAllowed = result.next_allowed_at ? new Date(result.next_allowed_at).toLocaleTimeString() : "later"
        setFeedback({ tone: "warning", message: `${result.message} Next try after ${nextAllowed}.` })
      } else {
        setFeedback({ tone: "info", message: result.message || "Manual run status updated." })
      }

      qc.invalidateQueries({ queryKey: ["dashboard"] })
      qc.invalidateQueries({ queryKey: ["suggestions"] })
    },
    onError: (mutationError: any) => {
      const detail = mutationError?.response?.data?.detail
      setFeedback({
        tone: "error",
        message: typeof detail === "string" && detail ? detail : "Could not queue manual run.",
      })
    },
  })

  useEffect(() => {
    setFeedback(null)
  }, [selectedApp?.id])

  const feedbackClass = useMemo(() => {
    if (!feedback) return ""
    if (feedback.tone === "success") return "border-green-200 bg-green-50 text-green-700"
    if (feedback.tone === "warning") return "border-amber-200 bg-amber-50 text-amber-700"
    if (feedback.tone === "error") return "border-red-200 bg-red-50 text-red-700"
    return "border-blue-200 bg-blue-50 text-blue-700"
  }, [feedback])

  if (isLoading) return <div className="text-muted-foreground">Loading...</div>
  if (error) return <div className="text-destructive">Failed to load dashboard</div>

  const appData = data?.apps?.find((item: any) => item.app_id === selectedApp?.id) ?? data?.apps?.[0]
  if (!appData) return <div className="text-muted-foreground">No app data available</div>

  const pipeline = appData.last_pipeline
  const pipelineStatus: string = pipeline?.status ?? "never_run"
  const isPipelineRunning = pipelineStatus === "queued" || pipelineStatus === "running"
  const totalSteps = Math.max(Number(pipeline?.total_steps || 0), 0)
  const completedSteps = Math.max(Number(pipeline?.steps_completed || 0), 0)
  const progressPercent =
    pipelineStatus === "queued"
      ? 8
      : totalSteps > 0
        ? Math.max(8, Math.min(100, Math.round((completedSteps / totalSteps) * 100)))
        : 0

  const statusIcons: Record<string, typeof CheckCircle> = {
    completed: CheckCircle,
    completed_with_warnings: AlertTriangle,
    queued: Clock,
    running: Clock,
    failed: XCircle,
    never_run: AlertTriangle,
    skipped: Clock,
    blocked: AlertTriangle,
  }

  const statusColors: Record<string, string> = {
    completed: "text-green-600",
    completed_with_warnings: "text-amber-700",
    queued: "text-blue-600",
    running: "text-blue-600",
    failed: "text-red-600",
    never_run: "text-yellow-600",
    skipped: "text-muted-foreground",
    blocked: "text-amber-700",
  }

  const stepTone: Record<StepLogItem["status"], string> = {
    pending: "bg-muted text-muted-foreground",
    running: "bg-blue-500/10 text-blue-600",
    completed: "bg-green-500/10 text-green-700",
    failed: "bg-red-500/10 text-red-600",
    skipped: "bg-amber-500/10 text-amber-700",
  }

  const StatusIcon = statusIcons[pipelineStatus] ?? AlertTriangle
  const statusColor = statusColors[pipelineStatus] ?? "text-muted-foreground"
  const stepLog: StepLogItem[] = pipeline?.step_log || []

  const mode = data?.mode
  const isDryRun = mode?.dry_run !== false
  const isManualApproval = mode?.manual_approval_required !== false
  const providerName = String(pipeline?.provider_name || "").toLowerCase()
  const providerStatus = String(pipeline?.provider_status || "").toLowerCase()
  const providerErrorClass = String(pipeline?.provider_error_class || "").toLowerCase()
  const showClaudeBilling = providerName.includes("anthropic")
  const needsBillingAttention = providerStatus.includes("billing") || providerErrorClass.includes("billing")

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">{appData.package_name}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${
            isDryRun
              ? "border-amber-300 bg-amber-50 text-amber-700"
              : "border-green-300 bg-green-50 text-green-700"
          }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${isDryRun ? "bg-amber-500" : "bg-green-500"}`} />
            {isDryRun ? "DRY RUN MODE" : "LIVE MODE"}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
            {isManualApproval ? "Manual Approval" : "Auto Rules"}
          </span>
          <span className="w-full text-[11px] text-muted-foreground">Mode status labels only (not buttons).</span>
        </div>
      </div>

      {feedback && <div className={`rounded-2xl border px-4 py-3 text-sm ${feedbackClass}`}>{feedback.message}</div>}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.3fr_0.85fr_0.85fr]">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <StatusIcon className={`h-5 w-5 ${statusColor}`} />
              <span className="text-sm font-medium">Last Pipeline</span>
            </div>
            {canRunNow && (
              <button
                type="button"
                onClick={() => runNow.mutate()}
                disabled={!selectedApp || runNow.isPending || isPipelineRunning}
                className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-xs font-medium transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
              >
                {runNow.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />}
                {pipelineStatus === "queued" ? "Queued..." : isPipelineRunning ? "Running..." : "Run now"}
              </button>
            )}
          </div>

          <div className={`text-lg font-semibold capitalize ${statusColor}`}>{formatStatus(pipelineStatus)}</div>
          <div className="mt-2 text-xs text-muted-foreground">{formatTriggerLabel(pipeline?.trigger)}</div>
          {pipeline?.current_step_label && <div className="mt-2 text-sm text-muted-foreground">{pipeline.current_step_label}</div>}

          {isPipelineRunning && (
            <div className="mt-3 space-y-2">
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${progressPercent}%` }} />
              </div>
              <div className="text-xs text-muted-foreground">
                {pipelineStatus === "queued" ? "Queued for worker pickup" : `Step ${completedSteps} of ${totalSteps}`}
              </div>
            </div>
          )}

          {pipeline?.started_at && (
            <div className="mt-3 text-xs text-muted-foreground">
              Started {new Date(pipeline.started_at).toLocaleString()}
            </div>
          )}
          {pipeline?.completed_at && (
            <div className="text-xs text-muted-foreground">Completed {new Date(pipeline.completed_at).toLocaleString()}</div>
          )}

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-muted/50 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Provider</div>
              <div className="mt-2 text-sm font-medium">{pipeline?.provider_name || "Not used yet"}</div>
              {pipeline?.fallback_provider_name && (
                <div className="mt-1 text-xs text-muted-foreground">Fallback: {pipeline.fallback_provider_name}</div>
              )}
              {pipeline?.provider_status && <div className="mt-1 text-xs text-muted-foreground">Health: {formatStatus(pipeline.provider_status)}</div>}
              {showClaudeBilling && (
                <div className="mt-2 rounded-xl border border-border bg-background/80 p-2">
                  <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Claude Billing</div>
                  <div className={`mt-1 text-xs ${needsBillingAttention ? "text-amber-700" : "text-muted-foreground"}`}>
                    {needsBillingAttention ? "Low credits or billing issue detected." : "Manage Claude credits and invoices."}
                  </div>
                  <a
                    href="https://platform.claude.com/settings/billing"
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[11px] font-medium hover:bg-accent"
                  >
                    {needsBillingAttention ? "Recharge Now" : "Open Billing"}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
            </div>

            <div className="rounded-2xl bg-muted/50 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Run value</div>
              <div className="mt-2 text-sm font-medium">${Number(pipeline?.estimated_cost || 0).toFixed(4)}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {pipeline?.suggestions_generated || 0} suggestions, {pipeline?.keywords_discovered || 0} keywords
              </div>
            </div>
          </div>

          {pipeline?.value_summary && <div className="mt-3 text-xs text-muted-foreground">{pipeline.value_summary}</div>}
          {pipeline?.error_message && (
            <div className={`mt-3 text-xs ${pipelineStatus === "failed" ? "text-red-600" : "text-amber-700"}`}>
              {pipeline.error_message}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-600" />
            <span className="text-sm font-medium">Pending Review</span>
          </div>
          <div className="text-2xl font-bold">{appData.pending_suggestions}</div>
          <div className="mt-1 text-xs text-muted-foreground">suggestions waiting</div>
          <div className="mt-3 text-xs text-muted-foreground">Approvals created in last run: {pipeline?.approvals_created || 0}</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <Key className="h-5 w-5 text-blue-600" />
            <span className="text-sm font-medium">Active Keywords</span>
          </div>
          <div className="text-2xl font-bold">{appData.active_keywords}</div>
          <div className="mt-1 text-xs text-muted-foreground">tracked keywords</div>
          <div className="mt-3 text-xs text-muted-foreground">Last run discovered: {pipeline?.keywords_discovered || 0}</div>
        </div>
      </div>

      <section className="panel p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Pipeline Trace</h2>
            <p className="text-sm text-muted-foreground">
              This shows which stages succeeded, which one failed or warned, and why Approvals may still be empty.
            </p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1.5 text-xs text-muted-foreground">
            <Receipt className="h-3.5 w-3.5" />
            Tokens: {pipeline?.input_tokens || 0} in / {pipeline?.output_tokens || 0} out
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {stepLog.map((step) => (
            <div key={step.key} className="rounded-2xl border border-border/70 p-4">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 rounded-full px-2.5 py-1 text-xs font-medium ${stepTone[step.status]}`}>
                    {formatStatus(step.status)}
                  </div>
                  <div>
                    <div className="font-medium">{step.label}</div>
                    {step.message && <div className="mt-1 text-sm text-muted-foreground">{step.message}</div>}
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                      {step.provider && (
                        <span className="inline-flex items-center gap-1">
                          <Sparkles className="h-3.5 w-3.5" />
                          {step.provider}
                        </span>
                      )}
                      {(step.estimated_cost || 0) > 0 && <span>Cost: ${Number(step.estimated_cost || 0).toFixed(4)}</span>}
                      {(step.input_tokens || 0) > 0 && <span>In: {step.input_tokens}</span>}
                      {(step.output_tokens || 0) > 0 && <span>Out: {step.output_tokens}</span>}
                    </div>
                  </div>
                </div>

                <div className="text-xs text-muted-foreground">
                  {step.started_at && <div>Started: {new Date(step.started_at).toLocaleString()}</div>}
                  {step.completed_at && <div>Finished: {new Date(step.completed_at).toLocaleString()}</div>}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

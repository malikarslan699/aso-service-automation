import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  KeyRound,
  Loader2,
  PencilLine,
  PlayCircle,
  Rocket,
  Save,
  Search,
  Send,
  Settings2,
  Upload,
} from "lucide-react"

import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"

type ConfigItem = {
  key: string
  value: string
  description: string
}

type IntegrationItem = {
  provider: string
  name: string
  endpoint: string
  configured: boolean
  app_id?: number
  last_check?: {
    connected?: boolean
    message?: string
    checked_at?: string
    status?: string
    provider_error_class?: string | null
    estimated_cost?: number
    input_tokens?: number
    output_tokens?: number
    key_suffix?: string | null
  } | null
}

type AppCredentialStatus = {
  app_id: number
  service_account_json: boolean
  anthropic_api_key: boolean
  openai_api_key: boolean
}

const INTEGRATION_FIELDS: Record<
  string,
  {
    title: string
    subtitle: string
    icon: typeof Bot
    optional?: boolean
    note: string
    fields: Array<{ key: string; label: string; placeholder: string; sensitive?: boolean }>
  }
> = {
  anthropic: {
    title: "Anthropic",
    subtitle: "Claude generation and reasoning",
    icon: Bot,
    note: "Primary AI provider. Health is only green when a real inference call succeeds, not just when the API key exists.",
    fields: [{ key: "anthropic_api_key", label: "Claude API key", placeholder: "Paste Anthropic API key", sensitive: true }],
  },
  openai: {
    title: "OpenAI",
    subtitle: "Automatic GPT fallback",
    icon: Bot,
    optional: true,
    note: "Optional fallback. Used only when Claude inference fails and this key is configured.",
    fields: [{ key: "openai_api_key", label: "OpenAI API key", placeholder: "Paste OpenAI API key", sensitive: true }],
  },
  telegram: {
    title: "Telegram",
    subtitle: "Alerts and confirmations",
    icon: Send,
    note: "Used for bot checks, alerts, and publish confirmations.",
    fields: [
      { key: "telegram_bot_token", label: "Bot token", placeholder: "Paste Telegram bot token", sensitive: true },
      { key: "telegram_chat_id", label: "Chat ID", placeholder: "Enter Telegram chat ID" },
    ],
  },
  serpapi: {
    title: "SerpAPI",
    subtitle: "Optional market signals",
    icon: Search,
    optional: true,
    note: "Optional. Core Claude/GPT workflow can still run without this.",
    fields: [{ key: "serpapi_key", label: "SerpAPI key", placeholder: "Paste SerpAPI key", sensitive: true }],
  },
  google_play: {
    title: "Google Play",
    subtitle: "Publishing and store actions",
    icon: PlayCircle,
    note: "Use the credential upload below for the selected project. Discovery URL is only for custom overrides.",
    fields: [
      { key: "google_play_package_name", label: "Default package name", placeholder: "com.company.app" },
      { key: "google_api_discovery_url", label: "Discovery host or URL", placeholder: "androidpublisher.googleapis.com" },
    ],
  },
}

const CONTROL_FIELDS: Array<{
  key: string
  title: string
  description: string
  helper: string
  icon: typeof Rocket
  type?: "boolean" | "text"
  trueLabel?: string
  falseLabel?: string
}> = [
  {
    key: "dry_run",
    title: "Execution mode",
    description: "Switch between Demo (safe simulation) and Live (real Google Play actions).",
    helper: "Use Demo mode for testing — no real changes are sent to Google Play.",
    icon: Rocket,
    type: "boolean",
    trueLabel: "Demo mode",
    falseLabel: "Live mode",
  },
  {
    key: "manual_trigger_cooldown_minutes",
    title: "Run Now cooldown (minutes)",
    description: "Minimum wait time between manual pipeline runs for the same project.",
    helper: "Set to 0 for testing. Increase for production to avoid accidental double-runs.",
    icon: Settings2,
  },
  {
    key: "listing_publish_max_per_day",
    title: "Max publishes per day",
    description: "Maximum number of listing updates allowed in one day.",
    helper: "Keeps publishing frequency within Google Play policy guidelines.",
    icon: Settings2,
  },
  {
    key: "listing_publish_max_per_week",
    title: "Max publishes per week",
    description: "Maximum number of listing updates allowed in one week.",
    helper: "Prevents aggressive metadata changes that could hurt app store ranking.",
    icon: Settings2,
  },
]

function extractErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === "string" && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (typeof first === "string" && first.trim()) return first
    if (first && typeof first === "object") {
      const location = Array.isArray((first as any).loc) ? (first as any).loc.join(".") : ""
      const message = typeof (first as any).msg === "string" ? (first as any).msg : "Validation error"
      return location ? `${location}: ${message}` : message
    }
  }
  return fallback
}

function formatLastChecked(checkedAt?: string) {
  return checkedAt ? new Date(checkedAt).toLocaleString() : null
}

function statusPill(item: IntegrationItem) {
  const status = item.last_check?.status
  if (status === "inference_healthy") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-2.5 py-1 text-xs font-medium text-green-600">
        <CheckCircle2 className="h-3.5 w-3.5" />
        Inference healthy
      </span>
    )
  }
  if (status === "billing_blocked") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-700">
        <AlertCircle className="h-3.5 w-3.5" />
        Billing blocked
      </span>
    )
  }
  if (status === "model_access_blocked" || status === "provider_error") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-600">
        <AlertCircle className="h-3.5 w-3.5" />
        Provider issue
      </span>
    )
  }
  if (item.configured) {
    return <span className="rounded-full bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-600">Configured</span>
  }
  return <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-600">Missing</span>
}

export function Settings() {
  const { selectedApp, user } = useAuth()
  const qc = useQueryClient()
  const isAdmin = user?.role === "admin"

  const [serviceFile, setServiceFile] = useState<File | null>(null)
  const [editingProvider, setEditingProvider] = useState<string | null>(null)
  const [editingControl, setEditingControl] = useState<string | null>(null)
  const [providerDrafts, setProviderDrafts] = useState<Record<string, Record<string, string>>>({})
  const [controlDrafts, setControlDrafts] = useState<Record<string, string>>({})
  const [projectKeyDrafts, setProjectKeyDrafts] = useState({ anthropic_api_key: "", openai_api_key: "" })
  const [editingTiming, setEditingTiming] = useState(false)
  const [timingDraft, setTimingDraft] = useState({ human_sim_enabled: "", pipeline_delay_min_minutes: "", pipeline_delay_max_minutes: "", publish_delay_min_minutes: "", publish_delay_max_minutes: "" })

  const { data: configs = [], isLoading } = useQuery<ConfigItem[]>({
    queryKey: ["settings"],
    queryFn: () => api.get("/api/v1/settings/global").then((response) => response.data),
  })

  const { data: integrations = [] } = useQuery<IntegrationItem[]>({
    queryKey: ["integration-status", selectedApp?.id],
    queryFn: () =>
      api
        .get("/api/v1/settings/integrations/status", { params: { app_id: selectedApp?.id } })
        .then((response) => response.data.integrations || []),
  })
  const { data: appCredentialStatus } = useQuery<AppCredentialStatus | null>({
    queryKey: ["app-credential-status", selectedApp?.id],
    queryFn: () =>
      api
        .get(`/api/v1/apps/${selectedApp?.id}/credentials/status`)
        .then((response) => response.data),
    enabled: !!selectedApp,
  })

  const configMap = useMemo(() => new Map(configs.map((item) => [item.key, item])), [configs])

  const saveProvider = useMutation({
    mutationFn: async (provider: string) => {
      const providerConfig = INTEGRATION_FIELDS[provider]
      const draft = providerDrafts[provider] || {}
      const updates = providerConfig.fields
        .map((field) => {
          const raw = draft[field.key]
          if (field.sensitive) return raw ? { key: field.key, value: raw } : null
          if (raw === undefined) return null
          return { key: field.key, value: raw.trim() }
        })
        .filter(Boolean) as Array<{ key: string; value: string }>
      if (updates.length === 0) return
      await Promise.all(updates.map((item) => api.put("/api/v1/settings/global", item)))
    },
    onSuccess: (_data, provider) => {
      setEditingProvider(null)
      setProviderDrafts((current) => ({ ...current, [provider]: {} }))
      qc.invalidateQueries({ queryKey: ["settings"] })
      qc.invalidateQueries({ queryKey: ["integration-status"] })
    },
  })

  const saveControl = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api.put("/api/v1/settings/global", { key, value }),
    onSuccess: () => {
      setEditingControl(null)
      qc.invalidateQueries({ queryKey: ["settings"] })
    },
  })

  const saveTimingSettings = useMutation({
    mutationFn: async (draft: typeof timingDraft) => {
      await Promise.all(
        Object.entries(draft)
          .filter(([, v]) => v !== "")
          .map(([key, value]) => api.put("/api/v1/settings/global", { key, value }))
      )
    },
    onSuccess: () => {
      setEditingTiming(false)
      qc.invalidateQueries({ queryKey: ["settings"] })
    },
  })

  const updatePublishMode = useMutation({
    mutationFn: (target: "manual" | "auto") =>
      api.patch("/api/v1/settings/publish-mode", {
        mode: "live",
        auto_approve: target === "auto",
      }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  })

  const isManualApproval = (configMap.get("manual_approval_required")?.value ?? "true") !== "false"
  const publishModeActive: "manual" | "auto" = isManualApproval ? "manual" : "auto"

  const checkIntegration = useMutation({
    mutationFn: (provider: string) =>
      api.post("/api/v1/settings/integrations/check", { provider, app_id: selectedApp?.id }).then((response) => response.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integration-status"] }),
  })

  const testTelegram = useMutation({
    mutationFn: () => api.post("/api/v1/settings/integrations/telegram/test").then((response) => response.data),
  })

  const uploadCredential = useMutation({
    mutationFn: async () => {
      if (!selectedApp || !serviceFile) throw new Error("Select a project and JSON file first")
      const formData = new FormData()
      formData.append("file", serviceFile)
      return api.post(`/api/v1/apps/${selectedApp.id}/credentials`, formData, {
        params: { credential_type: "service_account_json" },
      })
    },
    onSuccess: () => {
      setServiceFile(null)
      qc.invalidateQueries({ queryKey: ["integration-status"] })
    },
  })

  const saveProjectAiKeys = useMutation({
    mutationFn: async () => {
      if (!selectedApp) throw new Error("Select a project first")
      await api.put(`/api/v1/apps/${selectedApp.id}/credentials/text`, {
        credential_type: "anthropic_api_key",
        value: projectKeyDrafts.anthropic_api_key,
      })
      await api.put(`/api/v1/apps/${selectedApp.id}/credentials/text`, {
        credential_type: "openai_api_key",
        value: projectKeyDrafts.openai_api_key,
      })
    },
    onSuccess: () => {
      setProjectKeyDrafts({ anthropic_api_key: "", openai_api_key: "" })
      qc.invalidateQueries({ queryKey: ["app-credential-status"] })
      qc.invalidateQueries({ queryKey: ["integration-status"] })
    },
  })

  if (isLoading) return <div className="text-muted-foreground">Loading...</div>

  const controlValues = CONTROL_FIELDS.map((field) => ({
    ...field,
    value: configMap.get(field.key)?.value || "",
  }))

  return (
    <div className="space-y-6">
      <section className="panel soft-grid overflow-hidden p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">Control Center</div>
            <h1 className="text-3xl font-bold">Settings</h1>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
              Manage API providers, real inference health, and workflow controls without duplicating project or team management.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={checkIntegration.isPending}
              onClick={() => checkIntegration.mutate("all")}
              className="rounded-2xl border border-border bg-background/80 px-4 py-2 text-sm transition-colors hover:bg-accent disabled:opacity-50"
            >
              {checkIntegration.isPending ? "Checking..." : "Check all providers"}
            </button>
            <div className="rounded-2xl border border-border bg-background/80 px-4 py-2 text-sm">
              Current project: <span className="font-medium">{selectedApp?.name || "No project selected"}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-2xl font-bold">API Integrations</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Edit keys from these cards only. Health turns green only when real inference works.
          </p>
        </div>

        <div className="panel p-5 space-y-4">
          <div>
            <h3 className="text-lg font-semibold">Project AI Keys (Optional Override)</h3>
            <p className="text-sm text-muted-foreground mt-1">
              If set, this project will use its own API keys instead of shared global keys.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <input
              type="password"
              value={projectKeyDrafts.anthropic_api_key}
              onChange={(event) => setProjectKeyDrafts((current) => ({ ...current, anthropic_api_key: event.target.value }))}
              placeholder="Project Claude API key (leave empty to clear)"
              className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              type="password"
              value={projectKeyDrafts.openai_api_key}
              onChange={(event) => setProjectKeyDrafts((current) => ({ ...current, openai_api_key: event.target.value }))}
              placeholder="Project OpenAI key (optional)"
              className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className={`rounded-full px-2.5 py-1 ${appCredentialStatus?.anthropic_api_key ? "bg-green-500/10 text-green-700" : "bg-amber-500/10 text-amber-700"}`}>
              Claude key: {appCredentialStatus?.anthropic_api_key ? "Project override enabled" : "Using global key"}
            </span>
            <span className={`rounded-full px-2.5 py-1 ${appCredentialStatus?.openai_api_key ? "bg-green-500/10 text-green-700" : "bg-amber-500/10 text-amber-700"}`}>
              OpenAI key: {appCredentialStatus?.openai_api_key ? "Project override enabled" : "Using global key"}
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => saveProjectAiKeys.mutate()}
              disabled={saveProjectAiKeys.isPending || !selectedApp}
              className="rounded-2xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {saveProjectAiKeys.isPending ? "Saving..." : "Save Project AI Keys"}
            </button>
          </div>
          {saveProjectAiKeys.isError && (
            <p className="text-sm text-destructive">
              Failed: {extractErrorMessage(saveProjectAiKeys.error, "Could not save project AI keys")}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {integrations.map((integration) => {
            const integrationConfig = INTEGRATION_FIELDS[integration.provider]
            const Icon = integrationConfig.icon
            const isEditing = editingProvider === integration.provider
            return (
              <div key={integration.provider} className="panel p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex gap-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-lg font-semibold">{integrationConfig.title}</h3>
                        {integrationConfig.optional && (
                          <span className="rounded-full bg-secondary px-2.5 py-1 text-[11px] font-medium text-secondary-foreground">
                            Optional
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">{integrationConfig.subtitle}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {statusPill(integration)}
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingProvider(isEditing ? null : integration.provider)
                          setProviderDrafts((current) => ({
                            ...current,
                            [integration.provider]: integrationConfig.fields.reduce(
                              (accumulator, field) => ({
                                ...accumulator,
                                [field.key]:
                                  field.sensitive || configMap.get(field.key)?.value === "not set"
                                    ? ""
                                    : configMap.get(field.key)?.value || "",
                              }),
                              {},
                            ),
                          }))
                        }}
                        className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        <PencilLine className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-4 space-y-3">
                  <p className="text-sm text-muted-foreground">{integrationConfig.note}</p>

                  <div className="rounded-2xl bg-muted/60 p-4 text-sm">
                    <div className="font-medium">Endpoint</div>
                    <div className="mt-1 font-mono text-xs text-muted-foreground">{integration.endpoint}</div>
                    {integration.last_check?.message && <div className="mt-3 text-sm text-muted-foreground">{integration.last_check.message}</div>}
                    {integration.last_check?.checked_at && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        Last checked: {formatLastChecked(integration.last_check.checked_at)}
                      </div>
                    )}
                    {(integration.last_check?.estimated_cost || 0) > 0 && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        Probe cost: ${Number(integration.last_check?.estimated_cost || 0).toFixed(4)}
                      </div>
                    )}
                    {integration.last_check?.key_suffix && (
                      <div className="mt-1 text-xs text-muted-foreground">Key suffix: {integration.last_check.key_suffix}</div>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {integrationConfig.fields.map((field) => (
                      <div key={field.key} className="rounded-2xl border border-border/70 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{field.label}</div>
                        <div className="mt-2 text-sm font-medium">
                          {field.sensitive && configMap.get(field.key)?.value ? "••••••••" : configMap.get(field.key)?.value || "not set"}
                        </div>
                      </div>
                    ))}
                  </div>

                  {isEditing && isAdmin && (
                    <div className="rounded-2xl border border-border bg-background/70 p-4">
                      <div className="mb-3 text-sm font-medium">Update {integrationConfig.title}</div>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {integrationConfig.fields.map((field) => (
                          <label key={field.key} className="space-y-1 text-sm">
                            <span className="text-muted-foreground">{field.label}</span>
                            <input
                              type={field.sensitive ? "password" : "text"}
                              value={providerDrafts[integration.provider]?.[field.key] || ""}
                              onChange={(event) =>
                                setProviderDrafts((current) => ({
                                  ...current,
                                  [integration.provider]: {
                                    ...(current[integration.provider] || {}),
                                    [field.key]: event.target.value,
                                  },
                                }))
                              }
                              placeholder={field.placeholder}
                              className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                            />
                          </label>
                        ))}
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={saveProvider.isPending}
                          onClick={() => saveProvider.mutate(integration.provider)}
                          className="inline-flex items-center gap-2 rounded-2xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                        >
                          {saveProvider.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                          Save changes
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingProvider(null)}
                          className="rounded-2xl border border-border px-4 py-2 text-sm transition-colors hover:bg-accent"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={checkIntegration.isPending}
                      onClick={() => checkIntegration.mutate(integration.provider)}
                      className="rounded-2xl border border-border px-4 py-2 text-sm transition-colors hover:bg-accent disabled:opacity-50"
                    >
                      {checkIntegration.isPending ? "Checking..." : "Check provider"}
                    </button>
                    {integration.provider === "telegram" && (
                      <button
                        type="button"
                        disabled={testTelegram.isPending}
                        onClick={() => testTelegram.mutate()}
                        className="rounded-2xl border border-border px-4 py-2 text-sm transition-colors hover:bg-accent disabled:opacity-50"
                      >
                        {testTelegram.isPending ? "Sending..." : "Send Test Message"}
                      </button>
                    )}
                  </div>
                  {integration.provider === "telegram" && testTelegram.data && (
                    <div className={`rounded-2xl px-4 py-2 text-sm ${testTelegram.data.sent ? "bg-green-500/10 text-green-700" : "bg-red-500/10 text-red-600"}`}>
                      {testTelegram.data.sent ? "✅ " : "❌ "}{testTelegram.data.message}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Upload className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Play Console Credentials</h2>
            <p className="text-sm text-muted-foreground">
              Upload service account JSON for the selected project so publish actions can run safely.
            </p>
          </div>
        </div>

        <div className="mt-4 rounded-2xl bg-muted/60 p-4 text-sm">
          <div className="font-medium">Selected project</div>
          <div className="mt-1 text-muted-foreground">
            {selectedApp ? `${selectedApp.name} (${selectedApp.package_name})` : "Select a project first"}
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <input
            type="file"
            accept="application/json,.json"
            onChange={(event) => setServiceFile(event.target.files?.[0] || null)}
            className="block w-full text-sm"
          />
          <button
            type="button"
            disabled={!selectedApp || !serviceFile || uploadCredential.isPending}
            onClick={() => uploadCredential.mutate()}
            className="rounded-2xl border border-border px-4 py-3 text-sm transition-colors hover:bg-accent disabled:opacity-50"
          >
            {uploadCredential.isPending ? "Uploading..." : "Upload JSON"}
          </button>
        </div>

        {uploadCredential.isError && (
          <p className="mt-3 text-sm text-destructive">Failed: {extractErrorMessage(uploadCredential.error, "Upload error")}</p>
        )}
        {uploadCredential.isSuccess && <p className="mt-3 text-sm text-green-600">Credential uploaded.</p>}
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-2xl font-bold">Workflow Controls</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Control how the pipeline runs, when it publishes, and how much automation is allowed.
          </p>
        </div>

        <details className="rounded-2xl border border-border bg-muted/40 px-5 py-4">
          <summary className="cursor-pointer text-sm font-medium text-foreground select-none">
            📋 Recommended production settings
          </summary>
          <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground">
            <li>✅ <strong>Execution mode:</strong> Live — turn off Demo when ready for real Google Play actions</li>
            <li>✅ <strong>Publish mode:</strong> Manual — review each AI suggestion before it goes live</li>
            <li>✅ <strong>Human-like timing:</strong> ON — random delays before publishing (looks natural)</li>
            <li>✅ <strong>Publish window:</strong> 9AM–10PM UTC enforced automatically when timing is ON</li>
            <li>✅ <strong>Max per day:</strong> 1 listing update (safe for Google Play policy)</li>
            <li>✅ <strong>Max per week:</strong> 5 listing updates</li>
            <li>✅ <strong>Run Now cooldown:</strong> 30 minutes between manual runs</li>
            <li>✅ <strong>Telegram alerts:</strong> Configure bot token + chat ID for all notifications</li>
          </ul>
        </details>

        {/* Publish Mode card — mirrors Dashboard Manual/Auto toggle */}
        <div className="panel p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Rocket className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">Publish Mode</h3>
                <p className="text-sm text-muted-foreground">Controls whether suggestions require your approval before publishing to Google Play.</p>
              </div>
            </div>
          </div>
          <div className="mt-4 rounded-2xl bg-muted/60 p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Current mode</div>
            <div className="mt-2 text-lg font-semibold">{publishModeActive === "manual" ? "Manual — Approval required" : "Auto — Fully automated"}</div>
            <p className="mt-1 text-sm text-muted-foreground">
              {publishModeActive === "manual"
                ? "AI generates suggestions. You approve each one before anything goes live. Full control."
                : "AI generates → auto-approves → publishes live with random timing and daily limits. No manual action needed."}
            </p>
          </div>
          {isAdmin && (
            <div className="mt-4 rounded-2xl border border-border bg-background/70 p-4">
              <div className="flex flex-wrap gap-2">
                {(["manual", "auto"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    disabled={updatePublishMode.isPending}
                    onClick={() => updatePublishMode.mutate(m)}
                    className={`rounded-2xl px-4 py-2 text-sm transition-colors capitalize ${
                      publishModeActive === m ? "bg-primary text-primary-foreground" : "border border-border hover:bg-accent"
                    }`}
                  >
                    {m === "manual" ? "Manual" : "Auto"}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Same as the Dashboard toggle. Changes take effect immediately.</p>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {controlValues.map((control) => {
            const Icon = control.icon
            const isEditing = editingControl === control.key
            const rawValue = controlDrafts[control.key] ?? control.value
            const boolValue = rawValue === "true"
            return (
              <div key={control.key} className="panel p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold">{control.title}</h3>
                      <p className="text-sm text-muted-foreground">{control.description}</p>
                    </div>
                  </div>
                  {isAdmin && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingControl(isEditing ? null : control.key)
                        setControlDrafts((current) => ({ ...current, [control.key]: control.value }))
                      }}
                      className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    >
                      <PencilLine className="h-4 w-4" />
                    </button>
                  )}
                </div>

                <div className="mt-4 rounded-2xl bg-muted/60 p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Current value</div>
                  <div className="mt-2 text-lg font-semibold">
                    {control.type === "boolean" ? (boolValue ? control.trueLabel : control.falseLabel) : control.value}
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">{control.helper}</p>
                </div>

                {isEditing && isAdmin && (
                  <div className="mt-4 rounded-2xl border border-border bg-background/70 p-4">
                    {control.type === "boolean" ? (
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => setControlDrafts((current) => ({ ...current, [control.key]: "true" }))}
                          className={`rounded-2xl px-4 py-2 text-sm transition-colors ${
                            boolValue ? "bg-primary text-primary-foreground" : "border border-border hover:bg-accent"
                          }`}
                        >
                          {control.trueLabel}
                        </button>
                        <button
                          type="button"
                          onClick={() => setControlDrafts((current) => ({ ...current, [control.key]: "false" }))}
                          className={`rounded-2xl px-4 py-2 text-sm transition-colors ${
                            boolValue ? "border border-border hover:bg-accent" : "bg-primary text-primary-foreground"
                          }`}
                        >
                          {control.falseLabel}
                        </button>
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={rawValue}
                        onChange={(event) => setControlDrafts((current) => ({ ...current, [control.key]: event.target.value }))}
                        className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    )}

                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={saveControl.isPending}
                        onClick={() => saveControl.mutate({ key: control.key, value: rawValue })}
                        className="inline-flex items-center gap-2 rounded-2xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                      >
                        {saveControl.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingControl(null)}
                        className="rounded-2xl border border-border px-4 py-2 text-sm transition-colors hover:bg-accent"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Human-like timing — expanded card with editable delay ranges */}
        {(() => {
          const simEnabled = (configMap.get("human_sim_enabled")?.value ?? "false") === "true"
          const pipMin = configMap.get("pipeline_delay_min_minutes")?.value ?? "5"
          const pipMax = configMap.get("pipeline_delay_max_minutes")?.value ?? "20"
          const pubMin = configMap.get("publish_delay_min_minutes")?.value ?? "45"
          const pubMax = configMap.get("publish_delay_max_minutes")?.value ?? "180"
          return (
            <div className="panel p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <Settings2 className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold">Human-like timing</h3>
                    <p className="text-sm text-muted-foreground">Random delays before pipeline and publish steps to mimic natural human behavior. Avoids bot-like patterns.</p>
                  </div>
                </div>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => {
                      setEditingTiming(!editingTiming)
                      setTimingDraft({ human_sim_enabled: simEnabled ? "true" : "false", pipeline_delay_min_minutes: pipMin, pipeline_delay_max_minutes: pipMax, publish_delay_min_minutes: pubMin, publish_delay_max_minutes: pubMax })
                    }}
                    className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    <PencilLine className="h-4 w-4" />
                  </button>
                )}
              </div>
              <div className="mt-4 rounded-2xl bg-muted/60 p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Current value</div>
                <div className="mt-2 text-lg font-semibold">{simEnabled ? "Enabled (realistic delays)" : "Disabled (instant)"}</div>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-muted-foreground">
                  <div>
                    <span className="font-medium text-foreground">Pipeline delay</span>
                    <div>{pipMin}–{pipMax} min (random)</div>
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Publish delay</span>
                    <div>{pubMin}–{Math.round(Number(pubMax) / 60 * 10) / 10} hr (random)</div>
                  </div>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Turn off during testing to skip all delays.</p>
              </div>
              {editingTiming && isAdmin && (
                <div className="mt-4 rounded-2xl border border-border bg-background/70 p-4 space-y-4">
                  <div>
                    <div className="mb-2 text-sm font-medium">Enable/disable</div>
                    <div className="flex flex-wrap gap-2">
                      {[{ v: "true", label: "Enabled (realistic delays)" }, { v: "false", label: "Disabled (instant)" }].map(({ v, label }) => (
                        <button key={v} type="button"
                          onClick={() => setTimingDraft((d) => ({ ...d, human_sim_enabled: v }))}
                          className={`rounded-2xl px-4 py-2 text-sm transition-colors ${timingDraft.human_sim_enabled === v ? "bg-primary text-primary-foreground" : "border border-border hover:bg-accent"}`}
                        >{label}</button>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="mb-1.5 text-sm font-medium">Pipeline delay min (min)</div>
                      <input type="number" min="1" max="60" value={timingDraft.pipeline_delay_min_minutes}
                        onChange={(e) => setTimingDraft((d) => ({ ...d, pipeline_delay_min_minutes: e.target.value }))}
                        className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                      <div className="mt-1 text-xs text-muted-foreground">Default: 5</div>
                    </div>
                    <div>
                      <div className="mb-1.5 text-sm font-medium">Pipeline delay max (min)</div>
                      <input type="number" min="1" max="60" value={timingDraft.pipeline_delay_max_minutes}
                        onChange={(e) => setTimingDraft((d) => ({ ...d, pipeline_delay_max_minutes: e.target.value }))}
                        className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                      <div className="mt-1 text-xs text-muted-foreground">Default: 20</div>
                    </div>
                    <div>
                      <div className="mb-1.5 text-sm font-medium">Publish delay min (min)</div>
                      <input type="number" min="1" max="240" value={timingDraft.publish_delay_min_minutes}
                        onChange={(e) => setTimingDraft((d) => ({ ...d, publish_delay_min_minutes: e.target.value }))}
                        className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                      <div className="mt-1 text-xs text-muted-foreground">Default: 45</div>
                    </div>
                    <div>
                      <div className="mb-1.5 text-sm font-medium">Publish delay max (min)</div>
                      <input type="number" min="1" max="240" value={timingDraft.publish_delay_max_minutes}
                        onChange={(e) => setTimingDraft((d) => ({ ...d, publish_delay_max_minutes: e.target.value }))}
                        className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                      <div className="mt-1 text-xs text-muted-foreground">Default: 180 (3 hrs)</div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" disabled={saveTimingSettings.isPending}
                      onClick={() => saveTimingSettings.mutate(timingDraft)}
                      className="inline-flex items-center gap-2 rounded-2xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                    >
                      {saveTimingSettings.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      Save
                    </button>
                    <button type="button" onClick={() => setEditingTiming(false)}
                      className="rounded-2xl border border-border px-4 py-2 text-sm transition-colors hover:bg-accent"
                    >Cancel</button>
                  </div>
                </div>
              )}
            </div>
          )
        })()}
      </section>
    </div>
  )
}

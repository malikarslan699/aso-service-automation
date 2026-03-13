import { useMemo, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { ChevronDown, FolderKanban, Plus, Search, X } from "lucide-react"

import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"

function extractErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === "string" && detail.trim()) return detail
  return fallback
}

export function AppSelector() {
  const { apps, selectedApp, setSelectedApp, refreshApps, user } = useAuth()
  const [open, setOpen] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState("")
  const [form, setForm] = useState({ name: "", package_name: "", store: "google_play" })

  const canCreate = user?.role === "admin" || user?.role === "sub_admin"
  const filteredApps = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return apps
    return apps.filter(
      (app) => app.name.toLowerCase().includes(needle) || app.package_name.toLowerCase().includes(needle),
    )
  }, [apps, search])

  const createApp = useMutation({
    mutationFn: () => api.post("/api/v1/apps", form).then((response) => response.data),
    onSuccess: async (created) => {
      setForm({ name: "", package_name: "", store: "google_play" })
      setShowCreate(false)
      setOpen(false)
      await refreshApps()
      setSelectedApp(created)
    },
  })

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-3 rounded-2xl border border-border/80 bg-background/80 px-3 py-3 text-left text-sm shadow-sm transition-colors hover:bg-accent"
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <FolderKanban className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Project</div>
          <div className="truncate font-medium">{selectedApp?.name || "Select project"}</div>
          <div className="truncate text-xs text-muted-foreground">
            {selectedApp?.package_name || `${apps.length} project${apps.length === 1 ? "" : "s"}`}
          </div>
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-2 rounded-2xl border border-border bg-background shadow-lg">
          <div className="border-b border-border p-3">
            <div className="flex items-center gap-2 rounded-2xl border border-input bg-background px-3 py-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search projects"
                className="w-full bg-transparent text-sm outline-none"
              />
            </div>
          </div>

          <div className="max-h-80 overflow-y-auto p-2">
            {filteredApps.length === 0 ? (
              <div className="rounded-xl px-3 py-4 text-sm text-muted-foreground">No visible projects match your search.</div>
            ) : (
              filteredApps.map((app) => (
                <button
                  key={app.id}
                  onClick={() => {
                    setSelectedApp(app)
                    setOpen(false)
                  }}
                  className={`w-full rounded-xl px-4 py-3 text-left text-sm transition-colors hover:bg-accent ${
                    selectedApp?.id === app.id ? "bg-accent/70 font-medium text-primary" : ""
                  }`}
                >
                  <div className="truncate font-medium">{app.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{app.package_name}</div>
                </button>
              ))
            )}
          </div>

          {canCreate && (
            <div className="border-t border-border p-2">
              <button
                type="button"
                onClick={() => setShowCreate(true)}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border px-4 py-3 text-sm font-medium transition-colors hover:bg-accent"
              >
                <Plus className="h-4 w-4" />
                Add project
              </button>
            </div>
          )}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/40 px-4">
          <div className="panel w-full max-w-xl p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold">Add project</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Create a new project directly from the selector so switching and setup stay in one place.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <input
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="Project name"
                className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <input
                value={form.package_name}
                onChange={(event) => setForm((current) => ({ ...current, package_name: event.target.value }))}
                placeholder="Package name"
                className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <select
                value={form.store}
                onChange={(event) => setForm((current) => ({ ...current, store: event.target.value }))}
                className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="google_play">Google Play</option>
                <option value="app_store">App Store</option>
              </select>
            </div>

            {createApp.isError && (
              <p className="mt-3 text-sm text-destructive">
                Failed: {extractErrorMessage(createApp.error, "Could not create project")}
              </p>
            )}

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => createApp.mutate()}
                disabled={createApp.isPending || !form.name.trim() || !form.package_name.trim()}
                className="rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {createApp.isPending ? "Creating..." : "Create project"}
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-2xl border border-border px-4 py-3 text-sm transition-colors hover:bg-accent"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import api from "@/lib/api"
import { FileText } from "lucide-react"
import { useState } from "react"
import { useAuth } from "@/hooks/useAuth"

const LEVEL_COLOR = {
  info: "text-blue-600 bg-blue-50 border-blue-200",
  warning: "text-yellow-600 bg-yellow-50 border-yellow-200",
  error: "text-red-600 bg-red-50 border-red-200",
}

export function Logs() {
  const { selectedApp } = useAuth()
  const qc = useQueryClient()
  const [confirmClear, setConfirmClear] = useState(false)

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ["logs", selectedApp?.id],
    queryFn: () =>
      api
        .get("/api/v1/logs", { params: selectedApp?.id ? { app_id: selectedApp.id } : {} })
        .then((r) => r.data),
    refetchInterval: 10000,
    enabled: !!selectedApp,
  })

  const clearLogs = useMutation({
    mutationFn: () => api.delete("/api/v1/logs", { params: selectedApp?.id ? { app_id: selectedApp.id } : {} }),
    onSuccess: () => {
      setConfirmClear(false)
      qc.invalidateQueries({ queryKey: ["logs"] })
    },
  })

  if (!selectedApp) return <div className="text-muted-foreground">Select an app first</div>
  if (isLoading) return <div className="text-muted-foreground">Loading...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System Logs</h1>
        <p className="text-muted-foreground text-sm mt-1">Project-scoped backend logs for {selectedApp.name}</p>
      </div>

      <div className="flex items-center justify-end gap-2">
        {confirmClear ? (
          <>
            <span className="text-xs text-red-600">Clear all logs?</span>
            <button
              onClick={() => clearLogs.mutate()}
              disabled={clearLogs.isPending}
              className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              onClick={() => setConfirmClear(false)}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-accent"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            onClick={() => setConfirmClear(true)}
            className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
          >
            Clear Logs
          </button>
        )}
      </div>

      {logs.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-muted-foreground">
          <FileText className="h-12 w-12 mb-3 opacity-20" />
          <p>No logs yet</p>
        </div>
      ) : (
        <div className="space-y-2">
          {logs.map((log: any) => (
            <div key={log.id} className="rounded-lg border border-border bg-card p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${
                  LEVEL_COLOR[log.level as keyof typeof LEVEL_COLOR] ?? "text-muted-foreground border-border"
                }`}>
                  {log.level}
                </span>
                <span className="text-xs text-muted-foreground font-mono">{log.module}</span>
                <span className="text-xs text-muted-foreground ml-auto">
                  {log.created_at ? new Date(log.created_at).toLocaleString() : ""}
                </span>
              </div>
              <p className="text-sm">{log.message}</p>
              {log.details && (
                <pre className="text-xs text-muted-foreground mt-1 overflow-x-auto">{log.details}</pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

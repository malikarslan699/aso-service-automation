import { useQuery } from "@tanstack/react-query"
import api from "@/lib/api"
import { FileText } from "lucide-react"

const LEVEL_COLOR = {
  info: "text-blue-600 bg-blue-50 border-blue-200",
  warning: "text-yellow-600 bg-yellow-50 border-yellow-200",
  error: "text-red-600 bg-red-50 border-red-200",
}

export function Logs() {
  const { data: logs = [], isLoading } = useQuery({
    queryKey: ["logs"],
    queryFn: () => api.get("/api/v1/logs").then((r) => r.data),
    refetchInterval: 10000,
  })

  if (isLoading) return <div className="text-muted-foreground">Loading...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System Logs</h1>
        <p className="text-muted-foreground text-sm mt-1">Backend error and info logs</p>
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

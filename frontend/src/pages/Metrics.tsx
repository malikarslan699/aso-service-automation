import { useQuery } from "@tanstack/react-query"
import { useAuth } from "@/hooks/useAuth"
import { BarChart2 } from "lucide-react"
import { getPublishBadge } from "@/lib/publishState"
import { fetchAllSuggestions } from "@/lib/suggestions"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"

export function Metrics() {
  const { selectedApp } = useAuth()

  const { data: suggestions = [], isLoading } = useQuery({
    queryKey: ["suggestions-metrics", selectedApp?.id],
    queryFn: () => fetchAllSuggestions(selectedApp!.id),
    enabled: !!selectedApp,
  })

  const publishHistory = suggestions.filter((s: any) =>
    ["published", "dry_run_only", "blocked", "failed"].includes(s.publish_status)
  )

  const grouped: Record<string, { published: number; dryRuns: number }> = {}
  publishHistory.forEach((s: any) => {
    const dateValue = s.publish_completed_at || s.published_at || s.last_transition_at
    if (dateValue) {
      const day = dateValue.slice(0, 10)
      grouped[day] = grouped[day] || { published: 0, dryRuns: 0 }
      if (s.publish_status === "published") {
        grouped[day].published += 1
      }
      if (s.publish_status === "dry_run_only") {
        grouped[day].dryRuns += 1
      }
    }
  })

  const chartData = Object.entries(grouped)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({ date, publishes: count.published, dryRuns: count.dryRuns }))

  if (!selectedApp) return <div className="text-muted-foreground">Select an app first</div>
  if (isLoading) return <div className="text-muted-foreground">Loading...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Metrics</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Performance tracking for {selectedApp.name}
        </p>
      </div>

      {/* Publication timeline */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium mb-4">Publish Outcomes Over Time</h2>
        {chartData.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-muted-foreground">
            <BarChart2 className="h-12 w-12 mb-3 opacity-20" />
            <p>No publish data yet</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="publishes"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="dryRuns"
                stroke="hsl(var(--muted-foreground))"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div>
        <h2 className="text-sm font-medium mb-3">Recent Publish Outcomes</h2>
        {publishHistory.length === 0 ? (
          <p className="text-sm text-muted-foreground">No publish outcomes yet</p>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium">Field</th>
                  <th className="text-left px-4 py-3 font-medium">New Value</th>
                  <th className="text-left px-4 py-3 font-medium">Finished</th>
                  <th className="text-left px-4 py-3 font-medium">Publish State</th>
                </tr>
              </thead>
              <tbody>
                {publishHistory.map((s: any) => {
                  const badge = getPublishBadge(s)
                  return (
                    <tr key={s.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 capitalize font-medium">
                        {s.field_name.replace("_", " ")}
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-xs text-muted-foreground">
                        {s.new_value}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {s.publish_completed_at
                          ? new Date(s.publish_completed_at).toLocaleString()
                          : s.published_at
                          ? new Date(s.published_at).toLocaleString()
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full border px-2 py-0.5 text-xs ${badge?.classes || "text-slate-700 bg-slate-50 border-slate-200"}`}>
                          {badge?.label || s.publish_status || "Unknown"}
                        </span>
                        {s.publish_message && (
                          <div className="mt-1 max-w-sm text-[11px] text-muted-foreground">
                            {s.publish_message}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

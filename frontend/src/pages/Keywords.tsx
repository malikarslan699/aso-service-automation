import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { TrendingUp, Users, RefreshCw } from "lucide-react"

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 60 ? "bg-green-500" : pct >= 30 ? "bg-yellow-500" : "bg-red-400"
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground w-8 text-right">{pct}%</span>
    </div>
  )
}

export function Keywords() {
  const { selectedApp, user } = useAuth()
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<"opportunities" | "competitors">("opportunities")

  const { data: keywords = [], isLoading } = useQuery({
    queryKey: ["keywords", selectedApp?.id],
    queryFn: () =>
      api.get(`/api/v1/apps/${selectedApp?.id}/keywords`).then((r) => r.data),
    enabled: !!selectedApp,
  })

  const { data: competitorData, isLoading: loadingCompetitors } = useQuery({
    queryKey: ["keywords-competitors", selectedApp?.id],
    queryFn: () =>
      api.get(`/api/v1/apps/${selectedApp?.id}/keywords/competitors`).then((r) => r.data),
    enabled: !!selectedApp && activeTab === "competitors",
  })

  const discover = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/apps/${selectedApp?.id}/keywords/discover`),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["keywords"] }), 2000)
    },
  })

  if (!selectedApp) return <div className="text-muted-foreground">Select an app first</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Keywords</h1>
          <p className="text-muted-foreground text-sm mt-1">AI-discovered keyword opportunities</p>
        </div>
        {user?.role === "admin" && (
          <button
            onClick={() => discover.mutate()}
            disabled={discover.isPending}
            className="flex items-center gap-2 px-3 py-2 rounded-md border border-border text-sm hover:bg-accent disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`h-4 w-4 ${discover.isPending ? "animate-spin" : ""}`} />
            {discover.isPending ? "Running..." : "Discover"}
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        <button
          onClick={() => setActiveTab("opportunities")}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeTab === "opportunities"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <span className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Opportunities ({keywords.length})
          </span>
        </button>
        <button
          onClick={() => setActiveTab("competitors")}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeTab === "competitors"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <span className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            Competitor Analysis
          </span>
        </button>
      </div>

      {/* Opportunities tab */}
      {activeTab === "opportunities" && (
        <div>
          {isLoading ? (
            <div className="text-muted-foreground">Loading...</div>
          ) : keywords.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <TrendingUp className="h-12 w-12 mx-auto mb-3 opacity-20" />
              <p>No keywords yet. Run keyword discovery to get started.</p>
            </div>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium">Keyword</th>
                    <th className="text-left px-4 py-3 font-medium w-40">Opportunity</th>
                    <th className="text-left px-4 py-3 font-medium">Source</th>
                    <th className="text-left px-4 py-3 font-medium">Cluster</th>
                    <th className="text-center px-4 py-3 font-medium">Rec.</th>
                  </tr>
                </thead>
                <tbody>
                  {keywords.map((kw: any) => (
                    <tr key={kw.id} className="border-b border-border last:border-0 hover:bg-muted/20">
                      <td className="px-4 py-3 font-medium">{kw.keyword}</td>
                      <td className="px-4 py-3">
                        <ScoreBar score={kw.opportunity_score} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">{kw.source}</td>
                      <td className="px-4 py-3 text-xs">{kw.cluster || "—"}</td>
                      <td className="px-4 py-3 text-center text-xs">
                        {kw.recommended ? "✓" : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Competitors tab */}
      {activeTab === "competitors" && (
        <div>
          {loadingCompetitors ? (
            <div className="text-muted-foreground">Loading competitor data...</div>
          ) : !competitorData?.competitor_keywords?.length ? (
            <div className="text-center py-16 text-muted-foreground">
              <Users className="h-12 w-12 mx-auto mb-3 opacity-20" />
              <p>No competitor keyword data yet.</p>
            </div>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium">Keyword</th>
                    <th className="text-left px-4 py-3 font-medium w-40">Score</th>
                    <th className="text-left px-4 py-3 font-medium">Cluster</th>
                  </tr>
                </thead>
                <tbody>
                  {competitorData.competitor_keywords.map((kw: any, i: number) => (
                    <tr key={i} className="border-b border-border last:border-0 hover:bg-muted/20">
                      <td className="px-4 py-3 font-medium">{kw.keyword}</td>
                      <td className="px-4 py-3">
                        <ScoreBar score={kw.opportunity_score} />
                      </td>
                      <td className="px-4 py-3 text-xs">{kw.cluster || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

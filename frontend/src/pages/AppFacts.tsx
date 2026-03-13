import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Shield, Plus, Pencil, Trash2, Check, X } from "lucide-react"

export function AppFacts() {
  const { selectedApp, user } = useAuth()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<number | null>(null)
  const [editValues, setEditValues] = useState<{ fact_key: string; fact_value: string; verified: boolean }>({
    fact_key: "", fact_value: "", verified: false,
  })
  const [adding, setAdding] = useState(false)
  const [newFact, setNewFact] = useState({ fact_key: "", fact_value: "", verified: false })

  const { data: facts = [], isLoading } = useQuery({
    queryKey: ["facts", selectedApp?.id],
    queryFn: () =>
      api.get(`/api/v1/apps/${selectedApp?.id}/facts`).then((r) => r.data),
    enabled: !!selectedApp,
  })

  const create = useMutation({
    mutationFn: (data: typeof newFact) =>
      api.post(`/api/v1/apps/${selectedApp?.id}/facts`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facts"] })
      setAdding(false)
      setNewFact({ fact_key: "", fact_value: "", verified: false })
    },
  })

  const update = useMutation({
    mutationFn: ({ id, data }: { id: number; data: typeof editValues }) =>
      api.patch(`/api/v1/apps/${selectedApp?.id}/facts/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facts"] })
      setEditing(null)
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) =>
      api.delete(`/api/v1/apps/${selectedApp?.id}/facts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facts"] }),
  })

  if (!selectedApp) return <div className="text-muted-foreground">Select an app first</div>
  if (isLoading) return <div className="text-muted-foreground">Loading...</div>

  const isAdmin = user?.role === "admin"

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">App Facts</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Verified features used for AI safety validation
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => setAdding(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add Fact
          </button>
        )}
      </div>

      {/* Add new fact form */}
      {adding && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <h3 className="text-sm font-medium">New Fact</h3>
          <div className="grid grid-cols-2 gap-3">
            <input
              placeholder="Key (e.g. encryption_type)"
              value={newFact.fact_key}
              onChange={(e) => setNewFact({ ...newFact, fact_key: e.target.value })}
              className="px-3 py-2 rounded-md border border-input text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              placeholder="Value (e.g. AES-256)"
              value={newFact.fact_value}
              onChange={(e) => setNewFact({ ...newFact, fact_value: e.target.value })}
              className="px-3 py-2 rounded-md border border-input text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={newFact.verified}
              onChange={(e) => setNewFact({ ...newFact, verified: e.target.checked })}
            />
            Verified
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => create.mutate(newFact)}
              disabled={!newFact.fact_key || !newFact.fact_value}
              className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm disabled:opacity-50 transition-colors"
            >
              Save
            </button>
            <button
              onClick={() => setAdding(false)}
              className="px-3 py-1.5 rounded-md border border-border text-sm hover:bg-accent transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {facts.length === 0 && !adding ? (
        <div className="flex flex-col items-center py-16 text-muted-foreground">
          <Shield className="h-12 w-12 mb-3 opacity-20" />
          <p>No app facts yet. Add facts to enable evidence-based AI suggestions.</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-4 py-3 font-medium">Key</th>
                <th className="text-left px-4 py-3 font-medium">Value</th>
                <th className="text-center px-4 py-3 font-medium">Verified</th>
                {isAdmin && <th className="px-4 py-3 font-medium" />}
              </tr>
            </thead>
            <tbody>
              {facts.map((f: any) => (
                <tr key={f.id} className="border-b border-border last:border-0">
                  {editing === f.id ? (
                    <>
                      <td className="px-4 py-2">
                        <input
                          value={editValues.fact_key}
                          onChange={(e) => setEditValues({ ...editValues, fact_key: e.target.value })}
                          className="w-full px-2 py-1 rounded border border-input text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                      </td>
                      <td className="px-4 py-2">
                        <input
                          value={editValues.fact_value}
                          onChange={(e) => setEditValues({ ...editValues, fact_value: e.target.value })}
                          className="w-full px-2 py-1 rounded border border-input text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                      </td>
                      <td className="px-4 py-2 text-center">
                        <input
                          type="checkbox"
                          checked={editValues.verified}
                          onChange={(e) => setEditValues({ ...editValues, verified: e.target.checked })}
                        />
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex gap-1 justify-end">
                          <button onClick={() => update.mutate({ id: f.id, data: editValues })}
                            className="p-1 text-green-600 hover:bg-green-50 rounded">
                            <Check className="h-4 w-4" />
                          </button>
                          <button onClick={() => setEditing(null)}
                            className="p-1 text-muted-foreground hover:bg-accent rounded">
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-4 py-3 font-mono text-xs">{f.fact_key}</td>
                      <td className="px-4 py-3">{f.fact_value}</td>
                      <td className="px-4 py-3 text-center">
                        {f.verified ? (
                          <span className="text-green-600 text-xs font-medium">✓</span>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </td>
                      {isAdmin && (
                        <td className="px-4 py-3">
                          <div className="flex gap-1 justify-end">
                            <button
                              onClick={() => { setEditing(f.id); setEditValues(f) }}
                              className="p-1 text-muted-foreground hover:bg-accent rounded"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => remove.mutate(f.id)}
                              className="p-1 text-destructive hover:bg-destructive/10 rounded"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      )}
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Star, CheckCircle, MessageSquare } from "lucide-react"

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          className={`h-3 w-3 ${n <= rating ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"}`}
        />
      ))}
    </div>
  )
}

export function Reviews() {
  const { selectedApp, user } = useAuth()
  const qc = useQueryClient()

  const { data: reviews = [], isLoading } = useQuery({
    queryKey: ["reviews", selectedApp?.id],
    queryFn: () =>
      api.get(`/api/v1/apps/${selectedApp?.id}/reviews`).then((r) => r.data),
    enabled: !!selectedApp,
  })

  const approve = useMutation({
    mutationFn: (id: number) =>
      api.post(`/api/v1/apps/${selectedApp?.id}/reviews/${id}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reviews"] }),
  })

  if (!selectedApp) return <div className="text-muted-foreground">Select an app first</div>
  if (isLoading) return <div className="text-muted-foreground">Loading...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Review Replies</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {reviews.length} draft{reviews.length !== 1 ? "s" : ""} ready for review
        </p>
      </div>

      {reviews.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-muted-foreground">
          <MessageSquare className="h-12 w-12 mb-3 opacity-20" />
          <p>No review reply drafts yet.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {reviews.map((r: any) => (
            <div key={r.id} className="rounded-lg border border-border bg-card p-4 space-y-3">
              {/* Review */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <StarRating rating={r.review_rating} />
                  {r.reviewer_name && (
                    <span className="text-xs text-muted-foreground">{r.reviewer_name}</span>
                  )}
                </div>
                <p className="text-sm">{r.review_text}</p>
              </div>

              {/* Draft reply */}
              <div className="border-l-2 border-primary/30 pl-3">
                <div className="text-xs font-medium text-muted-foreground mb-1">Draft Reply</div>
                <p className="text-sm text-muted-foreground italic">{r.draft_reply}</p>
              </div>

              {/* Action */}
              {user?.role === "admin" && r.status === "pending" && (
                <button
                  onClick={() => approve.mutate(r.id)}
                  disabled={approve.isPending}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  <CheckCircle className="h-4 w-4" />
                  Approve Reply
                </button>
              )}
              {r.status === "approved" && (
                <span className="inline-flex items-center gap-1 text-xs text-green-600">
                  <CheckCircle className="h-3 w-3" />
                  Approved
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

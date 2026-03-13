import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { PencilLine, Power, Trash2, UserPlus, X } from "lucide-react"

import api from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"

type ProjectRef = {
  id: number
  name: string
  package_name: string
}

type TeamUser = {
  id: number
  username: string
  email: string | null
  role: string
  is_active: boolean
  app_ids: number[]
  assigned_projects: ProjectRef[]
  owned_projects: ProjectRef[]
}

function extractErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === "string" && detail.trim()) return detail
  return fallback
}

export function SubAdmins() {
  const { user, apps } = useAuth()
  const qc = useQueryClient()

  const [form, setForm] = useState({ username: "", password: "", email: "", app_ids: [] as number[] })
  const [editingUser, setEditingUser] = useState<TeamUser | null>(null)
  const [editPassword, setEditPassword] = useState("")
  const [editEmail, setEditEmail] = useState("")
  const [editAppIds, setEditAppIds] = useState<number[]>([])
  const [deleteTarget, setDeleteTarget] = useState<TeamUser | null>(null)

  const { data: subAdmins = [], isLoading } = useQuery<TeamUser[]>({
    queryKey: ["team-users"],
    queryFn: () => api.get("/api/v1/team/users").then((response) => response.data),
    enabled: user?.role === "admin",
  })

  const createSubAdmin = useMutation({
    mutationFn: () =>
      api.post("/api/v1/team/users", {
        username: form.username,
        password: form.password,
        email: form.email.trim() || null,
        app_ids: form.app_ids,
      }),
    onSuccess: () => {
      setForm({ username: "", password: "", email: "", app_ids: [] })
      qc.invalidateQueries({ queryKey: ["team-users"] })
    },
  })

  const updateSubAdmin = useMutation({
    mutationFn: () =>
      api.patch(`/api/v1/team/users/${editingUser?.id}`, {
        password: editPassword.trim() || undefined,
        email: editEmail.trim() || "",
        app_ids: editAppIds,
      }),
    onSuccess: () => {
      setEditingUser(null)
      setEditPassword("")
      setEditEmail("")
      setEditAppIds([])
      qc.invalidateQueries({ queryKey: ["team-users"] })
    },
  })

  const updateStatus = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      api.patch(`/api/v1/team/users/${id}/status`, { is_active: isActive }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["team-users"] }),
  })

  const removeSubAdmin = useMutation({
    mutationFn: (id: number) => api.delete(`/api/v1/team/users/${id}`),
    onSuccess: () => {
      setDeleteTarget(null)
      qc.invalidateQueries({ queryKey: ["team-users"] })
    },
  })

  if (user?.role !== "admin") {
    return <div className="text-muted-foreground">Only admin can manage sub-admins.</div>
  }

  if (isLoading) {
    return <div className="text-muted-foreground">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Sub Admins</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage access, assign projects, and keep project ownership separate from admin-level assignment.
        </p>
      </div>

      <section className="panel p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <UserPlus className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Create Sub-admin</h2>
            <p className="text-sm text-muted-foreground">Username must be unique. Email is optional.</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          <input
            value={form.username}
            onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
            placeholder="Username"
            className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            type="password"
            value={form.password}
            onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
            placeholder="Password"
            className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            value={form.email}
            onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
            placeholder="Email (Optional)"
            className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div className="mt-4 rounded-2xl border border-border p-4">
          <div className="mb-2 text-sm font-medium">Assigned Projects</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {apps.map((app) => (
              <label key={app.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.app_ids.includes(app.id)}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      app_ids: event.target.checked
                        ? [...current.app_ids, app.id]
                        : current.app_ids.filter((value) => value !== app.id),
                    }))
                  }
                />
                <span>{app.name}</span>
              </label>
            ))}
          </div>
        </div>

        <button
          type="button"
          disabled={createSubAdmin.isPending || !form.username.trim() || !form.password.trim()}
          onClick={() => createSubAdmin.mutate()}
          className="mt-4 rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {createSubAdmin.isPending ? "Creating..." : "Create sub-admin"}
        </button>

        {createSubAdmin.isError && (
          <p className="mt-3 text-sm text-destructive">
            Failed: {extractErrorMessage(createSubAdmin.error, "Could not create sub-admin")}
          </p>
        )}
      </section>

      <section className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1040px] text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">Username</th>
                <th className="px-4 py-3 text-left font-medium">Password</th>
                <th className="px-4 py-3 text-left font-medium">Email</th>
                <th className="px-4 py-3 text-left font-medium">Assigned Projects</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {subAdmins.map((member) => (
                <tr key={member.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-medium">{member.username}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span>••••••••</span>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingUser(member)
                          setEditPassword("")
                          setEditEmail(member.email || "")
                          setEditAppIds(member.app_ids)
                        }}
                        className="rounded-lg border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        <PencilLine className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span>{member.email?.trim() ? member.email : "---"}</span>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingUser(member)
                          setEditPassword("")
                          setEditEmail(member.email || "")
                          setEditAppIds(member.app_ids)
                        }}
                        className="rounded-lg border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        <PencilLine className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      {member.assigned_projects.length > 0 ? (
                        member.assigned_projects.map((project) => (
                          <span
                            key={project.id}
                            className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground"
                          >
                            {project.name} · Assigned by Admin
                          </span>
                        ))
                      ) : (
                        <span className="text-muted-foreground">---</span>
                      )}
                      {member.owned_projects.length > 0 &&
                        member.owned_projects.map((project) => (
                          <span
                            key={`owned-${project.id}`}
                            className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
                          >
                            Own: {project.name}
                          </span>
                        ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={updateStatus.isPending}
                      onClick={() => updateStatus.mutate({ id: member.id, isActive: !member.is_active })}
                      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                        member.is_active ? "bg-green-500/15 text-green-700" : "bg-slate-500/15 text-slate-600"
                      }`}
                    >
                      <Power className="h-3.5 w-3.5" />
                      {member.is_active ? "ON" : "OFF"}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(member)}
                      className="inline-flex items-center gap-2 rounded-xl border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {subAdmins.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                    No sub-admins yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {editingUser && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/40 px-4">
          <div className="panel w-full max-w-2xl p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">Edit {editingUser.username}</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Update password, email, and assigned projects from one place.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingUser(null)}
                className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <input
                type="password"
                value={editPassword}
                onChange={(event) => setEditPassword(event.target.value)}
                placeholder="New password"
                className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <input
                value={editEmail}
                onChange={(event) => setEditEmail(event.target.value)}
                placeholder="Email (Optional)"
                className="w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div className="mt-4 rounded-2xl border border-border p-4">
              <div className="mb-2 text-sm font-medium">Assigned Projects</div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {apps.map((app) => (
                  <label key={app.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={editAppIds.includes(app.id)}
                      onChange={(event) =>
                        setEditAppIds((current) =>
                          event.target.checked ? [...current, app.id] : current.filter((value) => value !== app.id),
                        )
                      }
                    />
                    <span>{app.name}</span>
                  </label>
                ))}
              </div>
            </div>

            {updateSubAdmin.isError && (
              <p className="mt-3 text-sm text-destructive">
                Failed: {extractErrorMessage(updateSubAdmin.error, "Could not update sub-admin")}
              </p>
            )}

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => updateSubAdmin.mutate()}
                disabled={updateSubAdmin.isPending}
                className="rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {updateSubAdmin.isPending ? "Saving..." : "Save changes"}
              </button>
              <button
                type="button"
                onClick={() => setEditingUser(null)}
                className="rounded-2xl border border-border px-4 py-3 text-sm transition-colors hover:bg-accent"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/40 px-4">
          <div className="panel w-full max-w-md p-5">
            <h2 className="text-lg font-semibold">Remove sub-admin</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to remove <span className="font-medium text-foreground">{deleteTarget.username}</span>?
            </p>

            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={() => removeSubAdmin.mutate(deleteTarget.id)}
                disabled={removeSubAdmin.isPending}
                className="rounded-2xl bg-destructive px-4 py-3 text-sm font-medium text-destructive-foreground transition-colors hover:opacity-90 disabled:opacity-50"
              >
                {removeSubAdmin.isPending ? "Removing..." : "Yes"}
              </button>
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="rounded-2xl border border-border px-4 py-3 text-sm transition-colors hover:bg-accent"
              >
                No
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

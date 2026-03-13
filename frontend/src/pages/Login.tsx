import { useState, FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/hooks/useAuth"
import { useTheme } from "@/hooks/useTheme"
import { Shield, CheckCircle2, AlertCircle, MoonStar, SunMedium } from "lucide-react"

export function Login() {
  const { login, backendConnected, refreshConnection } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await login(username, password)
      navigate("/")
    } catch {
      setError("Invalid username or password")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen px-4 py-10">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-5xl items-center justify-center">
        <div className="grid w-full overflow-hidden rounded-[2rem] border border-border/80 bg-card/90 shadow-[0_30px_90px_-45px_rgba(15,23,42,0.55)] backdrop-blur md:grid-cols-[1.1fr_0.9fr]">
          <div className="hidden flex-col justify-between bg-[linear-gradient(135deg,rgba(14,116,240,0.15),rgba(251,191,36,0.18))] p-10 md:flex">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/15 text-primary">
                <Shield className="h-6 w-6" />
              </div>
              <div>
                <h1 className="text-3xl font-bold">ASO Service</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  AI-assisted workflows for approvals, listings, reviews and publishing.
                </p>
              </div>
            </div>
            <div className="space-y-4 text-sm text-muted-foreground">
              <p>Use demo mode while validating prompts and approvals. Switch to live mode only when Google Play checks are green.</p>
              <button
                type="button"
                onClick={() => void refreshConnection()}
                className="inline-flex items-center gap-2 rounded-full border border-border bg-background/70 px-4 py-2"
              >
                {backendConnected ? (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                    Backend connected
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-4 w-4 text-red-600" />
                    Backend unreachable
                  </>
                )}
              </button>
            </div>
          </div>

          <div className="p-6 sm:p-8 md:p-10">
            <div className="mb-8 flex items-start justify-between gap-4">
              <div>
                <div className="mb-2 text-xs uppercase tracking-[0.22em] text-muted-foreground">Access Panel</div>
                <h2 className="text-3xl font-bold">Sign in</h2>
                <p className="mt-2 text-sm text-muted-foreground">Use your admin or sub-admin credentials to continue.</p>
              </div>
              <button
                type="button"
                onClick={toggleTheme}
                className="rounded-2xl border border-border p-3 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {theme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="username" className="mb-1 block text-sm font-medium">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded-2xl border border-input bg-background/80 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="admin"
                />
              </div>

              <div>
                <label htmlFor="password" className="mb-1 block text-sm font-medium">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-2xl border border-input bg-background/80 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="••••••••"
                />
              </div>

              <button
                type="button"
                onClick={() => void refreshConnection()}
                className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs md:hidden"
              >
                {backendConnected ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                    Backend connected
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-3.5 w-3.5 text-red-600" />
                    Backend unreachable
                  </>
                )}
              </button>

              {error && (
                <p className="rounded-2xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? "Signing in..." : "Sign in"}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

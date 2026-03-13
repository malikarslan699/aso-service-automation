import { Link } from "react-router-dom"
import {
  Activity,
  CheckCircle2,
  GitBranch,
  Lock,
  Rocket,
  ShieldCheck,
  Users,
  Workflow,
} from "lucide-react"

type OverviewProps = {
  publicView?: boolean
}

const publishStates = [
  { state: "Pending Review", meaning: "Suggestion generated and waiting for human action." },
  { state: "Approved (Ready to Publish in Google)", meaning: "Approved, waiting for publish mode and queue flow." },
  { state: "Queued in Listing Bundle", meaning: "Approved listing fields merged into one paced publish job." },
  { state: "Waiting Safe Window", meaning: "Bundle is waiting for safe dispatch window, jitter, and minimum gap." },
  { state: "Publishing to Google", meaning: "Live publish attempt in progress." },
  { state: "Published on Google", meaning: "Real live publish/reply completed successfully." },
  { state: "Dry Run Only", meaning: "Simulated publish in demo mode. Nothing sent to Google." },
  { state: "Blocked / Failed", meaning: "Stopped by safety limits, credential issue, or platform error." },
  { state: "Superseded", meaning: "Older pending item replaced by a newer pipeline run." },
]

const roleMatrix = [
  { role: "Admin", access: "All projects, settings, sub-admin management, approvals, publish control." },
  { role: "Sub Admin", access: "Own + assigned projects, approvals, run actions within allowed scope." },
]

const runFlow = [
  "Queue accepted",
  "Run started",
  "App data fetch",
  "Keyword discovery",
  "Duplicate filtering",
  "AI generation",
  "Approval creation",
  "Publish eligibility check",
  "Finalization",
]

export function AsoOverview({ publicView = false }: OverviewProps) {
  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-bold">ASO Service Overview</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              End-to-end structure for clients and developers: how data flows, how approvals work, and how publishing is controlled safely.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {publicView ? (
              <Link
                to="/login"
                className="rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                Open Dashboard Login
              </Link>
            ) : (
              <Link
                to="/"
                className="rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                Open Dashboard
              </Link>
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="panel p-5">
          <div className="mb-2 flex items-center gap-2 text-primary">
            <Workflow className="h-4 w-4" />
            <span className="text-sm font-semibold">Manual-First Workflow</span>
          </div>
          <p className="text-sm text-muted-foreground">
            AI suggests. Human approves. Backend publishes with limits and policy checks.
          </p>
        </div>
        <div className="panel p-5">
          <div className="mb-2 flex items-center gap-2 text-primary">
            <ShieldCheck className="h-4 w-4" />
            <span className="text-sm font-semibold">Safety Guardrails</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Duplicate control, near-duplicate blocking, churn limits, and role-based access checks.
          </p>
        </div>
        <div className="panel p-5">
          <div className="mb-2 flex items-center gap-2 text-primary">
            <Activity className="h-4 w-4" />
            <span className="text-sm font-semibold">Traceable States</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Every suggestion has review state, publish state, and a stage timeline.
          </p>
        </div>
        <div className="panel p-5">
          <div className="mb-2 flex items-center gap-2 text-primary">
            <Rocket className="h-4 w-4" />
            <span className="text-sm font-semibold">Deployment Ready</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Demo and live modes are separated clearly for controlled rollout.
          </p>
        </div>
      </section>

      <section className="panel p-6">
        <div className="mb-4 flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-primary" />
          <h2 className="text-xl font-semibold">System Architecture</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-border bg-background/60 p-4">
            <h3 className="text-sm font-semibold">Backend Core</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              FastAPI handles auth, app-scoped APIs, settings, approvals, and dashboard summaries. Celery worker/beat runs pipeline and publish tasks.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-background/60 p-4">
            <h3 className="text-sm font-semibold">Data Layer</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              PostgreSQL stores users, projects, suggestions, pipeline runs, status logs, keywords, and configuration values.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-background/60 p-4">
            <h3 className="text-sm font-semibold">AI + Integrations</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Anthropic (primary) and OpenAI (fallback) for generation. Google Play API for listing/reply publish. Telegram optional alerts.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-background/60 p-4">
            <h3 className="text-sm font-semibold">Frontend Control Panel</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Dashboard, Approvals, Settings, Sub Admins, and Metrics show operational state and make every decision traceable.
            </p>
          </div>
        </div>
      </section>

      <section className="panel p-6">
        <div className="mb-4 flex items-center gap-2">
          <Workflow className="h-4 w-4 text-primary" />
          <h2 className="text-xl font-semibold">Pipeline Flow</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {runFlow.map((item, idx) => (
            <div key={item} className="rounded-xl border border-border bg-background/60 p-3 text-sm">
              <div className="text-xs text-muted-foreground">Step {idx + 1}</div>
              <div className="mt-1 font-medium">{item}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-6">
        <div className="mb-4 flex items-center gap-2">
          <Rocket className="h-4 w-4 text-primary" />
          <h2 className="text-xl font-semibold">Publish Modes</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-border bg-background/60 p-4 space-y-2">
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">Manual</span>
            </div>
            <p className="text-sm text-muted-foreground">
              AI generates suggestions — you approve each one before anything goes <strong>live on Google Play</strong>. Full human control. Nothing publishes without your action.
            </p>
            <p className="text-xs text-muted-foreground italic">Best for: supervised publishing where you review every change.</p>
          </div>
          <div className="rounded-xl border border-border bg-background/60 p-4 space-y-2">
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-700">Auto</span>
            </div>
            <p className="text-sm text-muted-foreground">
              Fully automated. AI generates → auto-approves → publishes live with <strong>random human-like timing</strong> and daily/weekly publish limits. No manual action needed.
            </p>
            <p className="text-xs text-muted-foreground italic">Best for: set-and-forget once you trust AI quality and limits.</p>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          All modes respect the 9AM–10PM UTC publish window when human-like timing is enabled. Publishes outside the window are held and retried automatically on the next hour.
        </p>
      </section>

      <section className="panel p-6">
        <div className="mb-4 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-primary" />
          <h2 className="text-xl font-semibold">Suggestion States</h2>
        </div>
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50">
                <th className="px-4 py-3 text-left font-semibold">State</th>
                <th className="px-4 py-3 text-left font-semibold">Meaning</th>
              </tr>
            </thead>
            <tbody>
              {publishStates.map((row) => (
                <tr key={row.state} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">{row.state}</td>
                  <td className="px-4 py-3 text-muted-foreground">{row.meaning}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="panel p-6">
          <div className="mb-4 flex items-center gap-2">
            <Users className="h-4 w-4 text-primary" />
            <h2 className="text-xl font-semibold">Role Access</h2>
          </div>
          <div className="space-y-3">
            {roleMatrix.map((row) => (
              <div key={row.role} className="rounded-xl border border-border bg-background/60 p-3">
                <div className="text-sm font-medium">{row.role}</div>
                <div className="mt-1 text-sm text-muted-foreground">{row.access}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel p-6">
          <div className="mb-4 flex items-center gap-2">
            <Lock className="h-4 w-4 text-primary" />
            <h2 className="text-xl font-semibold">Operational Safeguards</h2>
          </div>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li>Exact duplicate and near-duplicate filtering before new suggestions are stored.</li>
            <li>Older unresolved pending suggestions are marked superseded by newer valid runs.</li>
            <li>Daily and weekly publish limits stop unsafe publish frequency.</li>
            <li>Live publish blocks if credential or policy preconditions are not satisfied.</li>
            <li>Dry-run mode never marks simulated actions as real Google publish.</li>
          </ul>
        </div>
      </section>

      <section className="panel p-6">
        <h2 className="text-xl font-semibold">Client Demo Walkthrough</h2>
        <ol className="mt-3 space-y-2 text-sm text-muted-foreground">
          <li>Open Dashboard and select a project.</li>
          <li>Run pipeline from `Run now`.</li>
          <li>Open Approvals and review run batch suggestions.</li>
          <li>Approve one item in dry-run to show simulation states.</li>
          <li>Switch to live mode only when credentials and policy checks are green.</li>
          <li>Track final outcome in Approvals timeline and Metrics publish outcomes table.</li>
        </ol>
      </section>
    </div>
  )
}

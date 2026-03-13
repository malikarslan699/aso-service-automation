import { Link, useLocation, Outlet } from "react-router-dom"
import { useAuth } from "@/hooks/useAuth"
import { useTheme } from "@/hooks/useTheme"
import { AppSelector } from "@/components/AppSelector"
import {
  LayoutDashboard,
  Compass,
  CheckSquare,
  Key,
  MessageSquare,
  BarChart2,
  Shield,
  Users,
  Settings,
  FileText,
  LogOut,
  CheckCircle2,
  AlertCircle,
  MoonStar,
  SunMedium,
  Menu,
  X,
} from "lucide-react"
import { useState } from "react"

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/overview", label: "Overview", icon: Compass },
  { to: "/approvals", label: "Approvals", icon: CheckSquare },
  { to: "/keywords", label: "Keywords", icon: Key },
  { to: "/reviews", label: "Reviews", icon: MessageSquare },
  { to: "/metrics", label: "Metrics", icon: BarChart2 },
  { to: "/facts", label: "App Facts", icon: Shield },
  { to: "/sub-admins", label: "Sub Admins", icon: Users, adminOnly: true },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/logs", label: "Logs", icon: FileText, adminOnly: true },
]

export function Layout() {
  const { pathname } = useLocation()
  const { user, logout, backendConnected, authConnected } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || user?.role === "admin"
  )

  return (
    <div className="flex min-h-[100dvh] flex-col overflow-hidden soft-grid md:h-screen md:flex-row">
      {/* Sidebar — desktop only */}
      <aside className="hidden md:flex w-72 flex-col border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))]">
        {/* Logo */}
        <div className="border-b border-[hsl(var(--sidebar-border))] px-4 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <span className="block text-base font-semibold">ASO Service</span>
              <span className="block text-xs text-muted-foreground">Projects, approvals and publishing</span>
            </div>
          </div>
        </div>

        {/* App Selector */}
        <div className="border-b border-[hsl(var(--sidebar-border))] px-3 py-4">
          <AppSelector />
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {visibleItems.map(({ to, label, icon: Icon }) => {
            const active = pathname === to
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-colors ${
                  active
                    ? "bg-primary text-primary-foreground shadow-md"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            )
          })}
        </nav>

        {/* User + Logout */}
        <div className="border-t border-[hsl(var(--sidebar-border))] px-3 py-4">
          <div className="panel bg-background/70 p-3">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs text-muted-foreground">
                <div className="font-medium text-foreground">{user?.username}</div>
                <div>{user?.role}</div>
              </div>
              <button
                onClick={toggleTheme}
                className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              >
                {theme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div className="text-xs text-muted-foreground">
                {backendConnected && authConnected ? (
                  <span className="inline-flex items-center gap-1 text-green-600">
                    <CheckCircle2 className="h-3 w-3" />
                    Connected
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-red-600">
                    <AlertCircle className="h-3 w-3" />
                    Disconnected
                  </span>
                )}
              </div>
              <button
                onClick={logout}
                className="rounded-xl p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                title="Logout"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex min-h-[100dvh] flex-1 flex-col overflow-hidden md:min-h-0">
        {/* Mobile header */}
        <header className="sticky top-0 z-40 md:hidden border-b border-border bg-card/90 px-4 py-3 backdrop-blur">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <span className="font-semibold text-sm">ASO Service</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={toggleTheme}
                className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {theme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
              </button>
              <button
                onClick={() => setMobileMenuOpen((current) => !current)}
                className="rounded-xl border border-border p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="mt-3">
            <AppSelector />
          </div>

          {mobileMenuOpen && (
            <div className="mt-3 rounded-2xl border border-border bg-background/95 p-2 shadow-lg">
              <nav className="space-y-1">
                {visibleItems.map(({ to, label, icon: Icon }) => {
                  const active = pathname === to
                  return (
                    <Link
                      key={to}
                      to={to}
                      onClick={() => setMobileMenuOpen(false)}
                      className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-colors ${
                        active
                          ? "bg-primary text-primary-foreground"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      {label}
                    </Link>
                  )
                })}
              </nav>
            </div>
          )}
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto px-4 pb-[calc(6rem+env(safe-area-inset-bottom))] pt-4 md:p-6">
          <Outlet />
        </main>

        {/* Mobile bottom nav */}
        <nav className="sticky bottom-0 z-40 border-t border-border bg-card/95 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur md:hidden">
          <div className="flex gap-2 overflow-x-auto pb-1">
          {visibleItems.map(({ to, label, icon: Icon }) => {
            const active = pathname === to
            return (
              <Link
                key={to}
                to={to}
                className={`flex min-w-[82px] shrink-0 flex-col items-center gap-1 rounded-2xl px-3 py-2 text-xs transition-colors ${
                  active ? "bg-primary/10 text-primary" : "text-muted-foreground"
                }`}
              >
                <Icon className="h-5 w-5" />
                <span className="truncate max-w-[72px]">{label}</span>
              </Link>
            )
          })}
          </div>
        </nav>
      </div>
    </div>
  )
}

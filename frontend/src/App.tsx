import { Routes, Route, Navigate } from "react-router-dom"
import { useAuth } from "@/hooks/useAuth"
import { Layout } from "@/components/Layout"
import { Login } from "@/pages/Login"
import { Dashboard } from "@/pages/Dashboard"
import { Approvals } from "@/pages/Approvals"
import { Keywords } from "@/pages/Keywords"
import { Reviews } from "@/pages/Reviews"
import { Metrics } from "@/pages/Metrics"
import { AppFacts } from "@/pages/AppFacts"
import { SubAdmins } from "@/pages/SubAdmins"
import { Settings } from "@/pages/Settings"
import { Logs } from "@/pages/Logs"
import { AsoOverview } from "@/pages/AsoOverview"

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-muted-foreground text-sm">Loading...</div>
      </div>
    )
  }

  if (!token) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/aso-overview" element={<AsoOverview publicView />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="overview" element={<AsoOverview />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="keywords" element={<Keywords />} />
        <Route path="reviews" element={<Reviews />} />
        <Route path="metrics" element={<Metrics />} />
        <Route path="facts" element={<AppFacts />} />
        <Route path="sub-admins" element={<SubAdmins />} />
        <Route path="settings" element={<Settings />} />
        <Route path="logs" element={<Logs />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

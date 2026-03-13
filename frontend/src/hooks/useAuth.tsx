import React, { createContext, useContext, useState, useEffect, ReactNode } from "react"
import api from "@/lib/api"

interface User {
  id: number
  username: string
  email: string
  role: "admin" | "sub_admin" | "viewer"
}

interface AppOption {
  id: number
  name: string
  package_name: string
  status: string
}

interface AuthContextType {
  user: User | null
  token: string | null
  selectedApp: AppOption | null
  apps: AppOption[]
  isLoading: boolean
  backendConnected: boolean
  authConnected: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  setSelectedApp: (app: AppOption) => void
  refreshConnection: () => Promise<void>
  refreshApps: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"))
  const [selectedApp, setSelectedAppState] = useState<AppOption | null>(null)
  const [apps, setApps] = useState<AppOption[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [backendConnected, setBackendConnected] = useState(false)
  const [authConnected, setAuthConnected] = useState(false)

  const refreshApps = async () => {
    if (!token) {
      setApps([])
      setSelectedAppState(null)
      localStorage.removeItem("selectedAppId")
      return
    }

    const res = await api.get("/api/v1/apps")
    const nextApps: AppOption[] = res.data
    setApps(nextApps)

    if (nextApps.length === 0) {
      setSelectedAppState(null)
      localStorage.removeItem("selectedAppId")
      return
    }

    const savedAppId = localStorage.getItem("selectedAppId")
    const fromSaved = savedAppId ? nextApps.find((a) => a.id === parseInt(savedAppId)) : null
    const fromCurrent = selectedApp ? nextApps.find((a) => a.id === selectedApp.id) : null
    const active = fromSaved || fromCurrent || nextApps[0]

    setSelectedAppState(active)
    localStorage.setItem("selectedAppId", String(active.id))
  }

  const refreshConnection = async () => {
    try {
      await api.get("/health")
      setBackendConnected(true)
    } catch {
      setBackendConnected(false)
    }

    if (!token) {
      setAuthConnected(false)
      return
    }

    try {
      await api.get("/auth/me")
      setAuthConnected(true)
    } catch {
      setAuthConnected(false)
    }
  }

  useEffect(() => {
    if (token) {
      setIsLoading(true)
      // Load current user
      api.get("/auth/me")
        .then((res) => {
          setBackendConnected(true)
          setAuthConnected(true)
          setUser(res.data)
          return refreshApps()
        })
        .catch(() => {
          // Token invalid — clear it
          localStorage.removeItem("token")
          setToken(null)
          setUser(null)
          setAuthConnected(false)
        })
        .finally(() => setIsLoading(false))
    } else {
      setUser(null)
      setApps([])
      setSelectedAppState(null)
      setAuthConnected(false)
      api.get("/health")
        .then(() => setBackendConnected(true))
        .catch(() => setBackendConnected(false))
        .finally(() => setIsLoading(false))
    }
  }, [token])

  const login = async (username: string, password: string) => {
    const res = await api.post("/auth/login", { username, password })
    const newToken: string = res.data.access_token

    localStorage.setItem("token", newToken)
    setToken(newToken)
  }

  const logout = () => {
    localStorage.removeItem("token")
    localStorage.removeItem("selectedAppId")
    setToken(null)
    setUser(null)
    setSelectedAppState(null)
    setApps([])
  }

  const setSelectedApp = (app: AppOption) => {
    setSelectedAppState(app)
    localStorage.setItem("selectedAppId", String(app.id))
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        selectedApp,
        apps,
        isLoading,
        backendConnected,
        authConnected,
        login,
        logout,
        setSelectedApp,
        refreshConnection,
        refreshApps,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

import axios from "axios"

const api = axios.create({
  baseURL: "/",
})

// Inject auth token and selected app on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  const appId = localStorage.getItem("selectedAppId")

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (appId) {
    config.headers["X-App-Id"] = appId
  }

  // Let browser/axios set multipart boundaries for FormData uploads.
  if (config.data instanceof FormData) {
    if (typeof config.headers?.delete === "function") {
      config.headers.delete("Content-Type")
    } else if (config.headers) {
      delete (config.headers as Record<string, string>)["Content-Type"]
    }
  } else if (config.data && !config.headers?.["Content-Type"]) {
    config.headers["Content-Type"] = "application/json"
  }

  return config
})

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token")
      localStorage.removeItem("selectedAppId")
      window.location.href = "/login"
    }
    return Promise.reject(error)
  }
)

export default api

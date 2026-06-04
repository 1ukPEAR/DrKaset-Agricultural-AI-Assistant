import { createContext, useContext, useState, useCallback } from 'react'
import { authAPI } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('drkaset_token'))
  const [user, setUser] = useState(() => {
    const t = localStorage.getItem('drkaset_token')
    if (!t) return null
    try {
      const payload = JSON.parse(atob(t.split('.')[1]))
      return { email: payload.email, id: payload.sub }
    } catch { return null }
  })

  const login = useCallback(async (email, password) => {
    const res = await authAPI.login(email, password)
    const { access_token } = res.data
    localStorage.setItem('drkaset_token', access_token)
    setToken(access_token)
    const payload = JSON.parse(atob(access_token.split('.')[1]))
    setUser({ email: payload.email, id: payload.sub })
    return res.data
  }, [])

  const register = useCallback(async (email, password) => {
    const res = await authAPI.register(email, password)
    const { access_token } = res.data
    localStorage.setItem('drkaset_token', access_token)
    setToken(access_token)
    const payload = JSON.parse(atob(access_token.split('.')[1]))
    setUser({ email: payload.email, id: payload.sub })
    return res.data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('drkaset_token')
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ token, user, login, register, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)

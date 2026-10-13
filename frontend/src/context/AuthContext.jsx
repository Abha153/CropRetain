import React, { createContext, useContext, useState, useCallback } from 'react'
import { api } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('cropretain_token'))
  const [role, setRole] = useState(() => localStorage.getItem('cropretain_role'))
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('cropretain_user')
    return raw ? JSON.parse(raw) : null
  })

  const applySession = useCallback((data) => {
    localStorage.setItem('cropretain_token', data.access_token)
    localStorage.setItem('cropretain_role', data.role)
    localStorage.setItem('cropretain_user', JSON.stringify(data.user))
    setToken(data.access_token)
    setRole(data.role)
    setUser(data.user)
  }, [])

  const loginFarmer = useCallback(async (email, password) => {
    const data = await api.loginFarmer(email, password)
    applySession(data)
    return data
  }, [applySession])

  const registerFarmer = useCallback(async (payload) => {
    const data = await api.registerFarmer(payload)
    applySession(data)
    return data
  }, [applySession])

  const registerBuyer = useCallback(async (payload) => {
    const data = await api.registerBuyer(payload)
    applySession(data)
    return data
  }, [applySession])

  const registerTransporter = useCallback(async (payload) => {
    const data = await api.registerTransporter(payload)
    applySession(data)
    return data
  }, [applySession])

  const logout = useCallback(() => {
    localStorage.removeItem('cropretain_token')
    localStorage.removeItem('cropretain_role')
    localStorage.removeItem('cropretain_user')
    setToken(null)
    setRole(null)
    setUser(null)
  }, [])

  const value = {
    token, role, user, isAuthenticated: !!token,
    loginFarmer, registerFarmer, registerBuyer, registerTransporter, logout, setUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { AUTH_REQUIRED_EVENT } from '@/lib/api/auth-events'
import { clearLegacyApiAuthToken } from '@/lib/api/auth-token'
import {
  getAuthStatus,
  getCurrentIdentity,
  loginLocalAuth,
  logoutCurrentSession,
  setupLocalAuth,
} from '@/lib/api/endpoints'
import { getOidcManager, isOidcConfigured, oidcReturnTo, sanitizeReturnTo } from '@/lib/auth/oidc'
import {
  clearIdentityToken,
  clearLegacyBootstrapIdentityToken,
  hasDevelopmentSession,
  isDevelopmentLoginAllowed,
  setDevelopmentSession,
  setRuntimeIdentityToken,
} from '@/lib/auth/session'
import type {
  AuthIdentity,
  AuthServerStatus,
  AuthStatus,
  LocalAuthLoginInput,
  LocalAuthSetupInput,
} from '@/lib/auth/types'

type AuthContextValue = {
  status: AuthStatus
  identity: AuthIdentity | null
  serverStatus: AuthServerStatus | null
  oidcEnabled: boolean
  developmentLoginEnabled: boolean
  setupLocalAccount: (input: LocalAuthSetupInput) => Promise<AuthIdentity>
  signInWithLocal: (input: LocalAuthLoginInput) => Promise<AuthIdentity>
  signInWithOidc: (returnTo?: string) => Promise<void>
  completeOidcSignIn: () => Promise<string>
  enterDevelopmentMode: () => void
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const DEVELOPMENT_IDENTITY: AuthIdentity = {
  subject: 'bootstrap-admin',
  email: null,
  name: 'Local Development',
  username: null,
  picture: null,
  is_platform_admin: true,
  auth_method: 'development',
}

function legacyServerStatus(): AuthServerStatus {
  return {
    initialized: true,
    claim_available: true,
    oidc_enabled: isOidcConfigured(),
    local_login_enabled: true,
    recovery_enabled: true,
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [identity, setIdentity] = useState<AuthIdentity | null>(null)
  const [serverStatus, setServerStatus] = useState<AuthServerStatus | null>(null)
  const oidcEnabled = isOidcConfigured() && (serverStatus?.oidc_enabled ?? true)
  const developmentLoginEnabled = isDevelopmentLoginAllowed()

  const acceptIdentityToken = useCallback(async (token: string) => {
    setRuntimeIdentityToken(token)
    try {
      const nextIdentity = await getCurrentIdentity()
      setIdentity(nextIdentity)
      setStatus('authenticated')
      setDevelopmentSession(false)
      return nextIdentity
    } catch (error) {
      setRuntimeIdentityToken('')
      throw error
    }
  }, [])

  const acceptCookieIdentity = useCallback((nextIdentity: AuthIdentity) => {
    clearIdentityToken()
    setDevelopmentSession(false)
    setIdentity(nextIdentity)
    setStatus('authenticated')
    return nextIdentity
  }, [])

  const becomeAnonymous = useCallback(() => {
    clearIdentityToken()
    setDevelopmentSession(false)
    setIdentity(null)
    setStatus(serverStatus?.initialized === false ? 'setup-required' : 'anonymous')
  }, [serverStatus?.initialized])

  useEffect(() => {
    let active = true

    async function restoreSession() {
      clearLegacyBootstrapIdentityToken()
      clearLegacyApiAuthToken()

      let nextServerStatus: AuthServerStatus
      try {
        nextServerStatus = await getAuthStatus()
      } catch {
        // Keep the previous OIDC/development posture usable during a rolling
        // upgrade where the new status endpoint is not available yet.
        nextServerStatus = legacyServerStatus()
      }
      if (!active) return
      setServerStatus(nextServerStatus)

      if (!nextServerStatus.initialized) {
        setIdentity(null)
        setStatus('setup-required')
        return
      }

      if (nextServerStatus.oidc_enabled) {
        try {
          const oidcUser = await getOidcManager()?.getUser()
          if (oidcUser && !oidcUser.expired) {
            if (!oidcUser.id_token) throw new Error('OIDC 未返回身份令牌')
            await acceptIdentityToken(oidcUser.id_token)
            return
          }
        } catch {
          clearIdentityToken()
        }
      }

      try {
        const nextIdentity = await getCurrentIdentity()
        if (!active) return
        acceptCookieIdentity(nextIdentity)
        return
      } catch {
        // No valid local cookie is the ordinary signed-out state.
      }

      if (developmentLoginEnabled && hasDevelopmentSession()) {
        if (!active) return
        setIdentity(DEVELOPMENT_IDENTITY)
        setStatus('authenticated')
        return
      }

      if (active) {
        setIdentity(null)
        setStatus('anonymous')
      }
    }

    void restoreSession()
    return () => {
      active = false
    }
  }, [acceptCookieIdentity, acceptIdentityToken, developmentLoginEnabled])

  useEffect(() => {
    const manager = getOidcManager()
    if (!manager) return

    const onUserLoaded = (user: { id_token?: string }) => {
      if (user.id_token) void acceptIdentityToken(user.id_token)
    }
    const onSessionEnded = () => becomeAnonymous()

    manager.events.addUserLoaded(onUserLoaded)
    manager.events.addUserUnloaded(onSessionEnded)
    manager.events.addAccessTokenExpired(onSessionEnded)
    return () => {
      manager.events.removeUserLoaded(onUserLoaded)
      manager.events.removeUserUnloaded(onSessionEnded)
      manager.events.removeAccessTokenExpired(onSessionEnded)
    }
  }, [acceptIdentityToken, becomeAnonymous])

  useEffect(() => {
    const onAuthRequired = () => {
      if (developmentLoginEnabled && hasDevelopmentSession()) return
      becomeAnonymous()
    }
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
  }, [becomeAnonymous, developmentLoginEnabled])

  const setupLocalAccount = useCallback(
    async (input: LocalAuthSetupInput) => {
      const nextIdentity = await setupLocalAuth(input)
      await getOidcManager()?.removeUser()
      setServerStatus((current) => ({
        ...(current ?? legacyServerStatus()),
        initialized: true,
        claim_available: false,
        local_login_enabled: true,
      }))
      return acceptCookieIdentity(nextIdentity)
    },
    [acceptCookieIdentity],
  )

  const signInWithLocal = useCallback(
    async (input: LocalAuthLoginInput) => {
      const nextIdentity = await loginLocalAuth(input)
      await getOidcManager()?.removeUser()
      return acceptCookieIdentity(nextIdentity)
    },
    [acceptCookieIdentity],
  )

  const signInWithOidc = useCallback(async (returnTo = '/studio') => {
    const manager = getOidcManager()
    if (!manager) throw new Error('OIDC 登录尚未配置')
    await manager.signinRedirect({ state: { returnTo: sanitizeReturnTo(returnTo) } })
  }, [])

  const completeOidcSignIn = useCallback(async () => {
    const manager = getOidcManager()
    if (!manager) throw new Error('OIDC 登录尚未配置')
    const user = await manager.signinRedirectCallback()
    if (!user.id_token) throw new Error('OIDC 未返回身份令牌')
    await acceptIdentityToken(user.id_token)
    return oidcReturnTo(user)
  }, [acceptIdentityToken])

  const enterDevelopmentMode = useCallback(() => {
    if (!developmentLoginEnabled) throw new Error('本地开发模式不可用')
    clearIdentityToken()
    setDevelopmentSession(true)
    setIdentity(DEVELOPMENT_IDENTITY)
    setStatus('authenticated')
  }, [developmentLoginEnabled])

  const signOut = useCallback(async () => {
    const manager = getOidcManager()
    const oidcUser = await manager?.getUser()
    try {
      await logoutCurrentSession()
    } catch {
      // A missing/expired cookie is already signed out from the local service.
    }
    becomeAnonymous()
    if (!manager || !oidcUser) return
    try {
      await manager.signoutRedirect()
    } catch {
      await manager.removeUser()
    }
  }, [becomeAnonymous])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      identity,
      serverStatus,
      oidcEnabled,
      developmentLoginEnabled,
      setupLocalAccount,
      signInWithLocal,
      signInWithOidc,
      completeOidcSignIn,
      enterDevelopmentMode,
      signOut,
    }),
    [
      completeOidcSignIn,
      developmentLoginEnabled,
      enterDevelopmentMode,
      identity,
      oidcEnabled,
      serverStatus,
      setupLocalAccount,
      signInWithLocal,
      signInWithOidc,
      signOut,
      status,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}

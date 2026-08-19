export type AuthIdentity = {
  subject: string
  email: string | null
  name: string | null
  username: string | null
  picture: string | null
  is_platform_admin: boolean
  auth_method: 'local' | 'oidc' | 'bootstrap' | 'development' | string
}

export type AuthServerStatus = {
  initialized: boolean
  claim_available?: boolean
  oidc_enabled: boolean
  local_login_enabled: boolean
  recovery_enabled: boolean
}

export type LocalAuthSetupInput = {
  claim_code: string
  username: string
  display_name?: string
  password: string
  remember_device: boolean
}

export type LocalAuthLoginInput = {
  username: string
  password: string
  remember_device: boolean
}

export type AuthSignOutResult = {
  signed_out: true
}

export type AuthStatus = 'loading' | 'setup-required' | 'authenticated' | 'anonymous'

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('login keeps the liquid, terminal, and pixel theme switcher', async () => {
  const login = await read('app/login/page.tsx')

  assert.match(login, /type LoginBackdrop = 'liquid' \| 'terminal' \| 'pixel'/)
  assert.match(login, /aria-label="登录背景主题"/)
  assert.match(login, /<PixelLiquidBg/)
  assert.match(login, /<FaultyTerminal/)
  assert.match(login, /<Dither/)
})

test('login preserves the current auth paths and reduced-motion fallback', async () => {
  const login = await read('app/login/page.tsx')

  assert.match(login, /signInWithOidc/)
  assert.match(login, /setupLocalAccount/)
  assert.match(login, /signInWithLocal/)
  assert.match(login, /enterDevelopmentMode/)
  assert.doesNotMatch(login, /signInWithBootstrap/)
  assert.match(login, /prefers-reduced-motion: reduce/)
})

test('local owner setup replaces browser-held operator credentials', async () => {
  const [login, provider, session, authToken, headers, client, endpoints] = await Promise.all([
    read('app/login/page.tsx'),
    read('components/auth/auth-provider.tsx'),
    read('lib/auth/session.ts'),
    read('lib/api/auth-token.ts'),
    read('lib/api/auth-headers.ts'),
    read('lib/api/client.ts'),
    read('lib/api/endpoints.ts'),
  ])

  assert.match(login, /设置此设备/)
  assert.match(login, /设备认领码/)
  assert.match(login, /设备认领码尚未配置/)
  assert.match(login, /DEVICE_CLAIM_CODE/)
  assert.match(login, /管理员密码至少需要 10 个字符/)
  assert.match(login, /minLength=\{10\}/)
  assert.match(login, /使用本机管理员账号登录/)
  assert.doesNotMatch(login, /BOOTSTRAP_ADMIN_TOKEN|API_AUTH_TOKEN|Fleet API 令牌/)
  assert.match(provider, /getAuthStatus/)
  assert.match(provider, /setupLocalAuth/)
  assert.match(provider, /loginLocalAuth/)
  assert.match(provider, /logoutCurrentSession/)
  assert.doesNotMatch(provider, /persistBootstrapIdentityToken|setApiAuthToken/)
  assert.match(session, /return runtimeIdentityToken/)
  assert.doesNotMatch(session, /sessionStorage\.setItem\(.*bootstrap/i)
  assert.match(authToken, /localStorage\.removeItem\(API_AUTH_TOKEN_KEY\)/)
  assert.match(authToken, /return ''/)
  assert.doesNotMatch(headers, /getApiAuthToken/)
  assert.doesNotMatch(client, /headers\['X-API-Token'\]/)
  assert.match(client, /X-OpenCLI-CSRF/)
  assert.match(endpoints, /get<ApiResponse<AuthServerStatus>>\('\/auth\/status'\)/)
  assert.match(endpoints, /post<ApiResponse<AuthIdentity>>\('\/auth\/setup'/)
  assert.match(endpoints, /post<ApiResponse<AuthIdentity>>\('\/auth\/login'/)
  assert.match(endpoints, /post<ApiResponse<AuthSignOutResult>>\('\/auth\/logout'\)/)
})

test('auth defaults return to the project list instead of a contextless workflow', async () => {
  const [provider, oidc] = await Promise.all([
    read('components/auth/auth-provider.tsx'),
    read('lib/auth/oidc.ts'),
  ])

  assert.match(provider, /returnTo = ['"]\/studio['"]/)
  assert.doesNotMatch(provider, /returnTo = ['"]\/studio\/workflow['"]/)
  assert.match(oidc, /return ['"]\/studio['"]/)
  assert.doesNotMatch(oidc, /return ['"]\/studio\/workflow['"]/)
})

test('OIDC keeps PKCE in the browser while proxying CORS-blocked token and JWKS calls', async () => {
  const [provider, header, oidc, nextConfig] = await Promise.all([
    read('components/auth/auth-provider.tsx'),
    read('components/shell/app-header.tsx'),
    read('lib/auth/oidc.ts'),
    read('next.config.mjs'),
  ])

  assert.match(provider, /acceptIdentityToken\(user\.id_token\)/)
  assert.match(provider, /acceptIdentityToken\(oidcUser\.id_token\)/)
  assert.doesNotMatch(provider, /acceptIdentityToken\(user\.access_token\)/)
  assert.doesNotMatch(provider, /acceptIdentityToken\(oidcUser\.access_token\)/)
  assert.match(oidc, /NEXT_PUBLIC_OIDC_AUTHORIZATION_ENDPOINT/)
  assert.match(oidc, /token_endpoint: `\$\{origin\}\/api\/auth\/oidc\/token`/)
  assert.match(oidc, /jwks_uri: `\$\{origin\}\/api\/auth\/oidc\/jwks`/)
  assert.doesNotMatch(oidc, /login\/oauth/)
  assert.match(nextConfig, /destination: OIDC_TOKEN_ENDPOINT/)
  assert.match(nextConfig, /destination: OIDC_JWKS_URL/)
  assert.doesNotMatch(nextConfig, /login\/oauth/)
  assert.match(header, /<AvatarImage src=\{avatarUrl\}/)
  assert.match(header, /identity\?\.picture/)
  assert.match(header, /identity\?\.username/)
})

test('local owner credentials survive browser and workflow proxy boundaries', async () => {
  const proxyPaths = [
    'app/api/workflow/opentabs-tool-nodes/route.ts',
    'app/api/workflow/bbx-tool-nodes/route.ts',
    'app/api/workflow/evidence-batch-proxy.ts',
    'app/api/workflow/import/dify/route.ts',
    'app/api/workflow/runs/[runId]/research-continuations/route.ts',
    'app/api/workflow/runs/[runId]/research-ledger/route.ts',
  ]
  const [headers, requestAuth, pluginCatalog, nodeCapabilities, imageBridge, ...proxies] =
    await Promise.all([
      read('lib/api/auth-headers.ts'),
      read('lib/workflow/request-auth.ts'),
      read('lib/plugins/backend-plugin-catalog.ts'),
      read('lib/plugins/backend-node-capabilities.ts'),
      read('features/image-studio/platform-canvas-host-bridge.ts'),
      ...proxyPaths.map(read),
    ])

  assert.match(headers, /'X-OpenCLI-CSRF': '1'/)
  assert.match(requestAuth, /request\.headers\.get\('cookie'\)/)
  assert.match(requestAuth, /request\.headers\.get\('x-opencli-csrf'\)/)
  assert.match(requestAuth, /Cookie: cookie/)
  assert.match(requestAuth, /'X-OpenCLI-CSRF': csrf/)

  for (const proxy of proxies) {
    assert.match(proxy, /forwardedRequestAuthHeaders\(req\)/)
    assert.doesNotMatch(proxy, /req\.headers\.get\(["']authorization["']\)/)
  }

  assert.match(pluginCatalog, /getApiAuthHeaders\(\)/)
  assert.match(nodeCapabilities, /getApiAuthHeaders\(\)/)
  assert.match(imageBridge, /getApiAuthHeaders\(\)/)
  assert.doesNotMatch(`${pluginCatalog}\n${nodeCapabilities}\n${imageBridge}`, /getApiAuthToken/)
})

test('Next-owned mutations authenticate server-side and require CSRF', async () => {
  const [guard, generateRoute, renderRoute, studioNew, palette, strip] = await Promise.all([
    read('lib/api/server-auth.ts'),
    read('app/api/generate-workflow/route.ts'),
    read('app/api/render/route.ts'),
    read('app/(app)/studio/new/page.tsx'),
    read('components/flow/command-palette.tsx'),
    read('components/flow/command-strip.tsx'),
  ])

  assert.match(guard, /\/api\/v1\/auth\/me/)
  assert.match(guard, /forwardedRequestAuthHeaders\(request\)/)
  assert.match(guard, /request\.headers\.get\('x-opencli-csrf'\) === '1'/)
  assert.match(guard, /process\.env\.NODE_ENV !== 'production'/)
  assert.match(guard, /'local-development'/)
  for (const route of [generateRoute, renderRoute]) {
    assert.match(route, /requireAuthenticatedMutation\(req\)/)
  }
  for (const caller of [studioNew, palette, strip]) {
    assert.match(caller, /\.\.\.getApiAuthHeaders\(\)/)
  }
})

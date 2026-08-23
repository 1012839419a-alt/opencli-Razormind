'use client'

import { Droplets, Grid3X3, KeyRound, LoaderCircle, ShieldCheck, SquareTerminal } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useState } from 'react'
import { toast } from 'sonner'

import FaultyTerminal from '@/components/FaultyTerminal'
import Dither from '@/components/Dither'
import { useAuth } from '@/components/auth/auth-provider'
import { PixelLiquidBg } from '@/components/unlumen-ui/pixel-liquid-bg'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import RevealText from '@/components/ui/smoothui/reveal-text'
import { sanitizeReturnTo } from '@/lib/auth/oidc'

type LoginBackdrop = 'liquid' | 'terminal' | 'pixel'

const BACKDROPS: Array<{ id: LoginBackdrop; label: string; icon: typeof Droplets }> = [
  { id: 'liquid', label: '流体', icon: Droplets },
  { id: 'terminal', label: '终端', icon: SquareTerminal },
  { id: 'pixel', label: '像素', icon: Grid3X3 },
]
const HEADLINE_WORDS = ['系统', '工作流', '数据产品']
const LIQUID_DARK_PALETTE = [
  '#050302',
  '#1a0805',
  '#351008',
  '#5b160c',
  '#8f2112',
  '#bd2d17',
  '#f0441f',
  '#ff6324',
  '#ff8a2b',
  '#ffad42',
  '#ffd36a',
  '#ffe596',
  '#fff0b0',
]
const LIQUID_LIGHT_PALETTE = [
  '#fff7d6',
  '#fff0b0',
  '#ffe596',
  '#ffd36a',
  '#ffad42',
  '#ff8a2b',
  '#ff6324',
  '#f0441f',
  '#bd2d17',
  '#8f2112',
]

function LoginBackground({ theme, reduceMotion }: { theme: LoginBackdrop; reduceMotion: boolean }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={theme}
        className="absolute inset-0"
        initial={reduceMotion ? false : { opacity: 0, filter: 'blur(6px)', scale: 1.01 }}
        animate={{ opacity: 1, filter: 'blur(0px)', scale: 1 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, filter: 'blur(3px)', scale: 0.995 }}
        transition={{ type: 'spring', duration: 0.45, bounce: 0 }}
      >
        {theme === 'liquid' ? (
          <div className="relative size-full overflow-hidden bg-[#070604]">
            <PixelLiquidBg
              className="absolute inset-0"
              darkPalette={LIQUID_DARK_PALETTE}
              lightPalette={LIQUID_LIGHT_PALETTE}
              pixelSize={11}
              resolution={0.34}
              mouseForce={5.5}
              cursorSize={150}
              viscosity={14}
              surfaceStrength={0.76}
              autoDemo={!reduceMotion}
            />
          </div>
        ) : theme === 'terminal' ? (
          <FaultyTerminal
            tint="#F97316"
            scale={1.35}
            gridMul={[2, 1]}
            digitSize={1.2}
            timeScale={0.22}
            pause={reduceMotion}
            scanlineIntensity={0.35}
            glitchAmount={0.65}
            flickerAmount={0.25}
            noiseAmp={0.85}
            chromaticAberration={0.5}
            curvature={0.08}
            mouseReact={!reduceMotion}
            mouseStrength={0.12}
            dpr={1}
            pageLoadAnimation={!reduceMotion}
            brightness={0.9}
          />
        ) : (
          <div className="relative size-full overflow-hidden bg-black">
            <div className="absolute inset-0 opacity-85">
              <Dither
                waveSpeed={0.1}
                waveFrequency={2.6}
                waveAmplitude={0.38}
                waveColor={[1, 0.27, 0.08]}
                colorNum={7}
                pixelSize={3}
                disableAnimation={reduceMotion}
                enableMouseInteraction={!reduceMotion}
                mouseRadius={0.72}
              />
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  )
}

function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const {
    status,
    serverStatus,
    oidcEnabled,
    developmentLoginEnabled,
    setupLocalAccount,
    signInWithLocal,
    signInWithOidc,
    enterDevelopmentMode,
  } = useAuth()
  const [claimCode, setClaimCode] = useState('')
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [rememberDevice, setRememberDevice] = useState(true)
  const [submitting, setSubmitting] = useState<
    'setup' | 'local' | 'oidc' | 'development' | null
  >(null)
  const [reduceMotion, setReduceMotion] = useState(true)
  const [backdrop, setBackdrop] = useState<LoginBackdrop>('liquid')
  const [headlineWord, setHeadlineWord] = useState(0)
  const returnTo = sanitizeReturnTo(searchParams.get('returnTo'))
  const requiresSetup = status === 'setup-required' || serverStatus?.initialized === false
  const claimAvailable = serverStatus?.claim_available ?? true
  const localLoginEnabled = serverStatus?.local_login_enabled ?? true

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const syncPreference = () => setReduceMotion(mediaQuery.matches)
    syncPreference()
    mediaQuery.addEventListener('change', syncPreference)
    return () => mediaQuery.removeEventListener('change', syncPreference)
  }, [])

  useEffect(() => {
    if (status === 'authenticated' && submitting !== 'development') router.replace(returnTo)
  }, [returnTo, router, status, submitting])

  useEffect(() => {
    router.prefetch(returnTo)
  }, [returnTo, router])

  useEffect(() => {
    if (reduceMotion) return
    const interval = window.setInterval(
      () => setHeadlineWord((current) => (current + 1) % HEADLINE_WORDS.length),
      2800,
    )
    return () => window.clearInterval(interval)
  }, [reduceMotion])

  async function startOidcLogin() {
    setSubmitting('oidc')
    try {
      await signInWithOidc(returnTo)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '无法启动 OIDC 登录')
      setSubmitting(null)
    }
  }

  async function handleSetup(event: React.FormEvent) {
    event.preventDefault()
    if (!claimCode.trim()) {
      toast.error('请输入设备认领码')
      return
    }
    if (!username.trim()) {
      toast.error('请输入管理员用户名')
      return
    }
    if (!password) {
      toast.error('请输入管理员密码')
      return
    }
    if (password.length < 10) {
      toast.error('管理员密码至少需要 10 个字符')
      return
    }
    if (password !== passwordConfirmation) {
      toast.error('两次输入的密码不一致')
      return
    }

    setSubmitting('setup')
    try {
      await setupLocalAccount({
        claim_code: claimCode.trim(),
        username: username.trim(),
        display_name: displayName.trim() || undefined,
        password,
        remember_device: rememberDevice,
      })
      toast.success('本机管理员已创建')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '无法完成设备设置')
      setSubmitting(null)
    }
  }

  async function handleLocalLogin(event: React.FormEvent) {
    event.preventDefault()
    if (!username.trim() || !password) {
      toast.error('请输入管理员用户名和密码')
      return
    }

    setSubmitting('local')
    try {
      await signInWithLocal({
        username: username.trim(),
        password,
        remember_device: rememberDevice,
      })
      toast.success('登录成功')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '用户名或密码不正确')
      setSubmitting(null)
    }
  }

  function handleDevelopmentLogin() {
    setSubmitting('development')
    try {
      enterDevelopmentMode()
      window.setTimeout(() => router.replace(returnTo), reduceMotion ? 0 : 285)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '无法进入本地开发模式')
      setSubmitting(null)
    }
  }

  return (
    <motion.main
      className="relative min-h-screen overflow-hidden bg-[#070604] text-white"
      animate={
        submitting === 'development' && !reduceMotion
          ? { x: '-100%' }
          : { x: 0 }
      }
      transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
    >
      <div className="absolute inset-0 opacity-90" aria-hidden="true">
        <LoginBackground theme={backdrop} reduceMotion={reduceMotion} />
      </div>
      <div
        className="absolute inset-0 bg-[linear-gradient(90deg,rgba(7,6,4,0.08),rgba(7,6,4,0.62)_52%,rgba(7,6,4,0.94)),linear-gradient(0deg,rgba(7,6,4,0.7),transparent_45%)]"
        aria-hidden="true"
      />

      <div className="absolute right-4 top-4 z-20 flex rounded-full border border-white/12 bg-black/45 p-1 backdrop-blur-xl sm:right-6 sm:top-6" aria-label="登录背景主题">
        {BACKDROPS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            aria-label={`${label}背景`}
            aria-pressed={backdrop === id}
            onClick={() => setBackdrop(id)}
            className="flex h-8 items-center gap-1.5 rounded-full px-2.5 text-xs text-white/55 transition-[color,background-color,transform] duration-200 [transition-timing-function:var(--motion-ease-settle)] hover:text-white active:scale-[0.94] aria-pressed:bg-white aria-pressed:text-black"
          >
            <Icon className="size-3.5" aria-hidden />
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>

      <div className="relative mx-auto grid min-h-screen w-full max-w-7xl items-center gap-12 px-4 py-10 sm:px-8 lg:grid-cols-[minmax(0,1fr)_26rem] lg:px-12">
        <section className="hidden max-w-2xl lg:block" aria-label="产品介绍">
          <div className="mb-10 flex items-start gap-5 font-mono text-orange-200">
            <motion.span
              className="grid size-14 shrink-0 place-items-center rounded-lg border border-orange-300/45 bg-orange-500/15 text-base font-bold tracking-[-0.06em] text-orange-100 shadow-[0_0_30px_rgba(255,99,36,0.14)]"
              initial={reduceMotion ? false : { opacity: 0, scale: 0.9, y: 8, filter: 'blur(5px)' }}
              animate={{ opacity: 1, scale: 1, y: 0, filter: 'blur(0px)' }}
              transition={{ type: 'spring', duration: 0.5, bounce: 0.08 }}
            >
              OC
            </motion.span>
            <div className="min-w-0 pt-0.5">
              <div className="flex overflow-hidden text-[clamp(2.8rem,4.5vw,4.4rem)] font-bold leading-[0.86] tracking-[-0.075em] text-white/95">
                {Array.from('OPENCLI').map((character, index) => (
                  <RevealText
                    key={`${character}-${index}`}
                    delay={80 + index * 45}
                    direction="up"
                  >
                    {character}
                  </RevealText>
                ))}
                <span className="sr-only">OPENCLI</span>
              </div>
              <motion.div
                className="mt-3 flex items-center gap-3 pl-[clamp(1rem,4vw,4rem)] text-[11px] tracking-[0.34em] text-orange-200/75"
                initial={reduceMotion ? false : { opacity: 0, x: -18, filter: 'blur(4px)' }}
                animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
                transition={{ type: 'spring', duration: 0.55, bounce: 0, delay: 0.42 }}
              >
                <span className="h-px w-10 bg-orange-300/55" aria-hidden="true" />
                CONTROL / PLANE
                <span className="text-orange-200">_</span>
              </motion.div>
            </div>
          </div>
          <p className="mb-4 font-mono text-xs tracking-[0.22em] text-orange-300/80">
            COLLECT · ORCHESTRATE · OPERATE
          </p>
          <h1 className="max-w-lg text-balance text-[clamp(2.25rem,3.5vw,3.5rem)] font-medium leading-[1.08] tracking-[-0.045em]">
            <RevealText delay={180} direction="up" className="block">
              把分散的数据能力，
            </RevealText>
            <span className="block">
              编排成持续运行的
              <span className="relative ml-[0.08em] inline-grid overflow-hidden align-bottom">
                <span className="invisible col-start-1 row-start-1">数据产品</span>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span
                    key={HEADLINE_WORDS[headlineWord]}
                    className="col-start-1 row-start-1 bg-[length:300%_100%] bg-clip-text text-transparent"
                    style={{
                      backgroundImage:
                        'linear-gradient(90deg,#ff8a48 0%,#ffb15c 28%,#f5a6d8 52%,#c9a7ff 72%,#ffd36a 100%)',
                    }}
                    initial={reduceMotion ? false : { opacity: 0, y: '48%', backgroundPosition: '100% 50%' }}
                    animate={{ opacity: 1, y: 0, backgroundPosition: '35% 50%' }}
                    exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: '-45%' }}
                    transition={{ duration: 0.62, ease: [0.22, 1, 0.36, 1] }}
                  >
                    {HEADLINE_WORDS[headlineWord]}
                  </motion.span>
                </AnimatePresence>
              </span>
            </span>
          </h1>
          <p className="mt-6 max-w-lg text-pretty text-base leading-7 text-white/60">
            从采集节点、自动化执行到交付与消费，在同一个运营控制台里观察、修复和扩展。
          </p>
        </section>

        <div className="mx-auto flex w-full max-w-md flex-col gap-6 lg:mx-0">
          <div className="flex items-center gap-3 lg:hidden">
            <span className="grid size-14 place-items-center rounded-lg border border-orange-400/40 bg-orange-500/15 font-mono text-base font-black tracking-[-0.06em] text-orange-100">
              OC
            </span>
            <div>
              <h1 className="text-xl font-black tracking-[-0.055em]">OPENCLI</h1>
              <p className="text-sm text-white/55">采集编排与运营控制台</p>
            </div>
          </div>

          <Card className="border-white/12 bg-background/92 shadow-2xl shadow-black/40 backdrop-blur-xl">
            <CardHeader>
              <CardTitle>{requiresSetup ? '设置此设备' : '登录控制台'}</CardTitle>
              <CardDescription>
                {requiresSetup
                  ? '这是此设备的首次设置。创建本机管理员后即可直接使用。'
                  : '使用本机管理员账号登录。'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {status === 'loading' ? (
                <div
                  className="flex min-h-40 items-center justify-center gap-3 text-sm text-muted-foreground"
                  role="status"
                >
                  <LoaderCircle className="size-5 animate-spin" />
                  正在检查设备状态…
                </div>
              ) : requiresSetup && claimAvailable ? (
                <form className="space-y-5" onSubmit={handleSetup}>
                  <FieldGroup>
                    <Field>
                      <FieldLabel htmlFor="claim-code">设备认领码</FieldLabel>
                      <Input
                        id="claim-code"
                        value={claimCode}
                        onChange={(event) => setClaimCode(event.target.value)}
                        placeholder="安装完成时显示的一次性认领码"
                        autoComplete="one-time-code"
                        autoFocus
                      />
                      <FieldDescription>
                        可在安装完成页或部署主机的首次启动输出中找到。
                      </FieldDescription>
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="setup-username">管理员用户名</FieldLabel>
                      <Input
                        id="setup-username"
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
                        autoComplete="username"
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="display-name">显示名称（可选）</FieldLabel>
                      <Input
                        id="display-name"
                        value={displayName}
                        onChange={(event) => setDisplayName(event.target.value)}
                        autoComplete="name"
                        placeholder="例如：家庭管理员"
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="setup-password">管理员密码</FieldLabel>
                      <Input
                        id="setup-password"
                        type="password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        autoComplete="new-password"
                        minLength={10}
                      />
                      <FieldDescription>至少 10 个字符；密码仅保存在本机。</FieldDescription>
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="password-confirmation">确认密码</FieldLabel>
                      <Input
                        id="password-confirmation"
                        type="password"
                        value={passwordConfirmation}
                        onChange={(event) => setPasswordConfirmation(event.target.value)}
                        autoComplete="new-password"
                        minLength={10}
                      />
                    </Field>
                  </FieldGroup>
                  <label className="flex cursor-pointer items-start gap-3 rounded-lg border bg-muted/30 p-3 text-sm">
                    <input
                      type="checkbox"
                      checked={rememberDevice}
                      onChange={(event) => setRememberDevice(event.target.checked)}
                      className="mt-0.5 size-4 accent-orange-500"
                    />
                    <span className="grid gap-0.5">
                      <span className="font-medium text-foreground">记住此设备</span>
                      <span className="text-xs text-muted-foreground">
                        仅在自己的电脑或手机上启用。
                      </span>
                    </span>
                  </label>
                  <Button
                    type="submit"
                    className={`w-full overflow-hidden transition-[height,border-radius,background-color] duration-300 ${submitting === 'setup' ? 'h-16 rounded-2xl' : 'h-10'}`}
                    data-triggered={submitting === 'setup'}
                    disabled={submitting !== null}
                  >
                    {submitting === 'setup' ? (
                      <span className="flex items-center gap-3 text-left">
                        <LoaderCircle className="size-5 animate-spin" />
                        <span className="grid">
                          <span>正在创建本机管理员</span>
                          <span className="text-xs font-normal opacity-65">
                            完成后将自动进入控制台
                          </span>
                        </span>
                      </span>
                    ) : (
                      <>
                        <KeyRound />
                        完成设置并进入控制台
                      </>
                    )}
                  </Button>
                </form>
              ) : requiresSetup ? (
                <div className="space-y-5">
                  <div className="rounded-lg border border-amber-500/35 bg-amber-500/10 p-4 text-sm">
                    <p className="font-medium text-foreground">设备认领码尚未配置</p>
                    <p className="mt-2 text-muted-foreground">
                      这是旧版本升级时的保护状态。请在部署主机的 <code>.env</code> 中设置
                      10 位 <code>DEVICE_CLAIM_CODE</code>，重启 API 后刷新本页；认领码只用于首次设置。
                    </p>
                  </div>
                  {oidcEnabled ? (
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full"
                      disabled={submitting !== null}
                      onClick={startOidcLogin}
                    >
                      <ShieldCheck />
                      使用原有组织账号登录
                    </Button>
                  ) : null}
                </div>
              ) : (
                <>
                  {localLoginEnabled ? (
                    <form className="space-y-5" onSubmit={handleLocalLogin}>
                      <FieldGroup>
                        <Field>
                          <FieldLabel htmlFor="login-username">管理员用户名</FieldLabel>
                          <Input
                            id="login-username"
                            value={username}
                            onChange={(event) => setUsername(event.target.value)}
                            autoComplete="username"
                            autoFocus
                          />
                        </Field>
                        <Field>
                          <FieldLabel htmlFor="login-password">密码</FieldLabel>
                          <Input
                            id="login-password"
                            type="password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            autoComplete="current-password"
                          />
                        </Field>
                      </FieldGroup>
                      <label className="flex cursor-pointer items-start gap-3 rounded-lg border bg-muted/30 p-3 text-sm">
                        <input
                          type="checkbox"
                          checked={rememberDevice}
                          onChange={(event) => setRememberDevice(event.target.checked)}
                          className="mt-0.5 size-4 accent-orange-500"
                        />
                        <span className="grid gap-0.5">
                          <span className="font-medium text-foreground">记住此设备</span>
                          <span className="text-xs text-muted-foreground">
                            仅在自己的电脑或手机上启用。
                          </span>
                        </span>
                      </label>
                      <Button
                        type="submit"
                        className={`w-full overflow-hidden transition-[height,border-radius,background-color] duration-300 ${submitting === 'local' ? 'h-16 rounded-2xl' : 'h-10'}`}
                        data-triggered={submitting === 'local'}
                        disabled={submitting !== null}
                      >
                        {submitting === 'local' ? (
                          <span className="flex items-center gap-3 text-left">
                            <LoaderCircle className="size-5 animate-spin" />
                            <span className="grid">
                              <span>正在登录</span>
                              <span className="text-xs font-normal opacity-65">
                                正在恢复设备会话
                              </span>
                            </span>
                          </span>
                        ) : (
                          <>
                            <KeyRound />
                            登录
                          </>
                        )}
                      </Button>
                    </form>
                  ) : null}

                  {oidcEnabled || developmentLoginEnabled ? (
                    <div className="space-y-3">
                      <div className="flex items-center gap-3">
                        <Separator className="flex-1" />
                        <span className="text-xs text-muted-foreground">其他登录方式</span>
                        <Separator className="flex-1" />
                      </div>
                      {oidcEnabled ? (
                        <Button
                          type="button"
                          variant="outline"
                          className={`w-full overflow-hidden transition-[height,border-radius,background-color] duration-300 ${submitting === 'oidc' ? 'h-16 rounded-2xl' : 'h-10'}`}
                          data-triggered={submitting === 'oidc'}
                          disabled={submitting !== null}
                          onClick={startOidcLogin}
                        >
                          {submitting === 'oidc' ? (
                            <span className="flex items-center gap-3 text-left">
                              <LoaderCircle className="size-5 animate-spin" />
                              <span className="grid">
                                <span>正在连接组织账号</span>
                                <span className="text-xs font-normal opacity-65">
                                  等待身份提供方响应
                                </span>
                              </span>
                            </span>
                          ) : (
                            <>
                              <ShieldCheck />
                              使用组织账号登录
                            </>
                          )}
                        </Button>
                      ) : null}
                      {developmentLoginEnabled ? (
                        <Button
                          type="button"
                          variant="ghost"
                          className={`w-full overflow-hidden text-muted-foreground transition-[height,border-radius,background-color] duration-300 ${submitting === 'development' ? 'h-16 rounded-2xl bg-muted' : 'h-10'}`}
                          data-triggered={submitting === 'development'}
                          disabled={submitting !== null}
                          onClick={handleDevelopmentLogin}
                        >
                          {submitting === 'development' ? (
                            <span className="flex items-center gap-3 text-left text-foreground">
                              <LoaderCircle className="size-5 animate-spin" />
                              <span className="grid">
                                <span>正在进入本地开发模式</span>
                                <span className="text-xs font-normal text-muted-foreground">
                                  正在建立开发会话
                                </span>
                              </span>
                            </span>
                          ) : (
                            '进入本地开发模式'
                          )}
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </>
              )}
            </CardContent>
            {!requiresSetup &&
            status !== 'loading' &&
            serverStatus?.recovery_enabled ? (
              <CardFooter>
                <details className="w-full rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
                  <summary className="cursor-pointer font-medium text-foreground">紧急恢复</summary>
                  <p className="mt-2 text-xs leading-5">
                    恢复操作需要直接访问部署主机。请在主机侧生成一次性恢复入口；此登录页不会接收长期管理员令牌。
                  </p>
                </details>
              </CardFooter>
            ) : null}
          </Card>
          <p className="text-center font-mono text-[11px] tracking-wide text-white/35">
            LOCAL-FIRST · AUDITABLE · NODE-NATIVE
          </p>
        </div>
      </div>
    </motion.main>
  )
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}

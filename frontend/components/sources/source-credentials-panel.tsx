'use client'

import { useState } from 'react'
import { Eye, EyeOff, KeyRound, Loader2, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { useDeleteSourceCredential, useSourceCredentials, useStoreSourceCredential } from '@/lib/api/hooks'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

// key_name presets that AuthManager.resolve_context() understands for the
// three declared auth_kind values (backend/auth/manager.py,
// backend/schemas/credential.py docstring): token=bearer, key=api_key,
// username/password=basic. Sources on a different auth_kind still work via
// the "自定义" (custom) fallback below — this is a UX hint, not validation;
// the backend accepts any key_name up to 64 chars.
const KEY_NAME_PRESETS = [
  { value: 'token', label: 'token', hint: 'Bearer 认证令牌' },
  { value: 'key', label: 'key', hint: 'API Key 认证' },
  { value: 'username', label: 'username', hint: 'Basic 认证 · 用户名' },
  { value: 'password', label: 'password', hint: 'Basic 认证 · 密码' },
] as const

const CUSTOM_PRESET = '__custom__'

function AddCredentialDialog({
  sourceId,
  existingKeyNames,
}: {
  sourceId: string
  existingKeyNames: string[]
}) {
  const [open, setOpen] = useState(false)
  const [preset, setPreset] = useState<string>('token')
  const [customKeyName, setCustomKeyName] = useState('')
  const [secret, setSecret] = useState('')
  const [showSecret, setShowSecret] = useState(false)
  const storeMutation = useStoreSourceCredential(sourceId)

  const keyName = (preset === CUSTOM_PRESET ? customKeyName : preset).trim()
  const isReplacing = keyName.length > 0 && existingKeyNames.includes(keyName)

  const reset = () => {
    setPreset('token')
    setCustomKeyName('')
    setSecret('')
    setShowSecret(false)
  }

  const handleOpenChange = (next: boolean) => {
    setOpen(next)
    if (!next) reset()
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!keyName) {
      toast.error('请填写凭证名称（key_name）')
      return
    }
    if (!secret.trim()) {
      toast.error('请填写密钥值')
      return
    }
    storeMutation.mutate(
      { key_name: keyName, secret: secret.trim() },
      {
        onSuccess: () => {
          toast.success(isReplacing ? `已更新凭证 "${keyName}"` : `已保存凭证 "${keyName}"`)
          handleOpenChange(false)
        },
        onError: (cause) => toast.error((cause as Error).message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button size="sm" />}>
        <Plus className="size-4" />
        添加凭证
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>添加凭证</DialogTitle>
            <DialogDescription>
              加密后写入 source_credentials，仅此表单可见明文 —— 保存后任何接口都不会再回显，需要更换时直接重新填写覆盖。
            </DialogDescription>
          </DialogHeader>

          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="credential-key-name">凭证名称</FieldLabel>
              <Select value={preset} onValueChange={(value) => setPreset(value as string)}>
                <SelectTrigger id="credential-key-name" className="w-full">
                  <SelectValue placeholder="选择凭证名称" />
                </SelectTrigger>
                <SelectContent>
                  {KEY_NAME_PRESETS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label} · {item.hint}
                    </SelectItem>
                  ))}
                  <SelectItem value={CUSTOM_PRESET}>自定义…</SelectItem>
                </SelectContent>
              </Select>
              <FieldDescription>
                需与数据源的认证方式匹配：token 对应 Bearer 认证，key 对应 API Key 认证，username /
                password 对应 Basic 认证。不确定时选择自定义并联系数据源负责人确认。
              </FieldDescription>
            </Field>

            {preset === CUSTOM_PRESET ? (
              <Field>
                <FieldLabel htmlFor="credential-custom-key-name">自定义名称</FieldLabel>
                <Input
                  id="credential-custom-key-name"
                  placeholder="例如 client_secret"
                  value={customKeyName}
                  onChange={(event) => setCustomKeyName(event.target.value)}
                  maxLength={64}
                />
              </Field>
            ) : null}

            {isReplacing ? (
              <p className="text-xs text-warning">
                “{keyName}” 已配置过凭证，保存将替换现有密钥值。
              </p>
            ) : null}

            <Field>
              <FieldLabel htmlFor="credential-secret">密钥值</FieldLabel>
              <InputGroup>
                <InputGroupInput
                  id="credential-secret"
                  type={showSecret ? 'text' : 'password'}
                  placeholder="粘贴密钥、令牌或密码"
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                  autoComplete="off"
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupButton
                    size="icon-xs"
                    type="button"
                    aria-label={showSecret ? '隐藏密钥值' : '显示密钥值'}
                    onClick={() => setShowSecret((current) => !current)}
                  >
                    {showSecret ? <EyeOff /> : <Eye />}
                  </InputGroupButton>
                </InputGroupAddon>
              </InputGroup>
              <FieldDescription>仅以加密形式存储（Fernet），仅在提交前的这个输入框里可见明文。</FieldDescription>
            </Field>
          </FieldGroup>

          <DialogFooter>
            <Button type="submit" disabled={storeMutation.isPending || !keyName || !secret.trim()}>
              {storeMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
              {storeMutation.isPending ? '保存中…' : isReplacing ? '替换凭证' : '保存凭证'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function SourceCredentialsPanel({ sourceId }: { sourceId: string }) {
  const { data, isLoading, isError, error } = useSourceCredentials(sourceId)
  const credentials = data ?? []
  const keyNames = credentials.map((cred) => cred.key_name)
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null)
  const deleteMutation = useDeleteSourceCredential(sourceId)

  const handleDelete = (keyName: string) => {
    if (confirmDeleteKey !== keyName) {
      setConfirmDeleteKey(keyName)
      return
    }
    deleteMutation.mutate(keyName, {
      onSuccess: () => {
        toast.success(`已删除凭证 "${keyName}"`)
        setConfirmDeleteKey(null)
      },
      onError: (cause) => toast.error((cause as Error).message),
    })
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div>
          <CardTitle className="text-base">凭证</CardTitle>
          <CardDescription>
            加密保存在 source_credentials 中；这里只显示凭证名称，密钥值一经保存即不再回显。
          </CardDescription>
        </div>
        <AddCredentialDialog sourceId={sourceId} existingKeyNames={keyNames} />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingState rows={2} />
        ) : isError ? (
          <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
        ) : credentials.length === 0 ? (
          <EmptyState title="尚未配置凭证" description="该数据源当前没有加密保存的密钥、令牌或密码。" />
        ) : (
          <div className="flex flex-col gap-2">
            {credentials.map((cred) => {
              const confirming = confirmDeleteKey === cred.key_name
              return (
                <div
                  key={cred.key_name}
                  className="flex flex-col gap-2 rounded-lg border bg-muted/15 px-3 py-2.5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <KeyRound className="size-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <p className="truncate font-mono text-sm">{cred.key_name}</p>
                        <p className="text-xs text-muted-foreground">•••••••• 已加密保存</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge variant="secondary">已配置</Badge>
                      <Button
                        size="xs"
                        variant={confirming ? 'destructive' : 'ghost'}
                        disabled={deleteMutation.isPending}
                        onClick={() => handleDelete(cred.key_name)}
                        className="gap-1"
                      >
                        <Trash2 className="size-3" />
                        {confirming ? '确认删除' : '删除'}
                      </Button>
                    </div>
                  </div>
                  {confirming ? (
                    <p className="text-xs text-destructive">
                      删除后，依赖 “{cred.key_name}” 凭证的采集将在下次运行时因认证失败而报错，请确认该数据源不再需要它。
                    </p>
                  ) : null}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

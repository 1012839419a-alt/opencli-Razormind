'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { useCreateSource } from '@/lib/api/hooks'
import type { DataSource } from '@/lib/api/types'
import { BACKEND_HINT, ErrorState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

type ChannelType = DataSource['channel_type']

const CHANNELS: Array<{ value: ChannelType; label: string }> = [
  { value: 'opencli', label: 'OpenCLI' },
  { value: 'web_scraper', label: '网页采集' },
  { value: 'api', label: 'API' },
  { value: 'rss', label: 'RSS' },
  { value: 'cli', label: 'CLI' },
  { value: 'skill', label: '技能' },
  { value: 'crawl4ai', label: 'Crawl4AI' },
  { value: 'browser_act', label: 'Browser Act' },
  { value: 'doubao_research', label: '豆包研究' },
  { value: 'douyin_detail', label: '抖音详情' },
]

export default function NewSourcePage() {
  const router = useRouter()
  const createSource = useCreateSource()
  const [name, setName] = useState('')
  const [channelType, setChannelType] = useState<ChannelType>('opencli')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState('{}')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      const parsed = JSON.parse(config)
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        throw new Error('channel_config 必须是 JSON 对象')
      }
      const source = await createSource.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
        channel_type: channelType,
        channel_config: parsed,
      })
      toast.success('数据源已创建')
      router.push(`/sources/${source.id}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建数据源失败')
    }
  }

  return (
    <PageContainer
      eyebrow="SOURCE SETUP"
      title="新建数据源"
      description="创建真实的后端数据源配置，凭据请在创建后单独加密保存。"
      actions={
        <Link href="/records" className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}>
          <ArrowLeft className="size-4" />
          返回数据
        </Link>
      }
    >
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle className="text-base">数据源配置</CardTitle>
          <CardDescription>保存后仍需完成凭据、连接测试和控制目标配置，不能直接视为可运行。</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={submit}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="source-name">名称</FieldLabel>
                <Input id="source-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={255} />
              </Field>
              <Field>
                <FieldLabel htmlFor="source-channel">渠道类型</FieldLabel>
                <Select value={channelType} onValueChange={(value) => value && setChannelType(value as ChannelType)}>
                  <SelectTrigger id="source-channel"><SelectValue /></SelectTrigger>
                  <SelectContent>{CHANNELS.map((channel) => <SelectItem key={channel.value} value={channel.value}>{channel.label}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="source-description">说明</FieldLabel>
                <Input id="source-description" value={description} onChange={(event) => setDescription(event.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="source-config">channel_config（JSON）</FieldLabel>
                <Textarea id="source-config" value={config} onChange={(event) => setConfig(event.target.value)} spellCheck={false} className="min-h-40 font-mono text-xs" required />
                <FieldDescription>只填写公开配置。Token、Key 等密钥请通过详情页的加密凭据面板保存。</FieldDescription>
              </Field>
            </FieldGroup>
            {createSource.isError ? <ErrorState message={(createSource.error as Error)?.message} hint={BACKEND_HINT} /> : null}
            <Button type="submit" disabled={createSource.isPending || !name.trim()}>
              <Plus className="size-4" />
              {createSource.isPending ? '创建中…' : '创建数据源'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </PageContainer>
  )
}

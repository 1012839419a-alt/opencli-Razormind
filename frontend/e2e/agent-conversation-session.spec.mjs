import { expect, test } from '@playwright/test'

const workspace = { id: 'workspace-a', name: 'Research', slug: 'research', active: true, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
const conversation = { id: 'conversation-a', workspace_id: workspace.id, title: null, status: 'active', context_binding: {}, revision: 0, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }

test('agent conversation session sends, restores, continues, and confirms a proposal', async ({ page }) => {
  const turns = []
  let created = false
  let confirmationCount = 0

  await page.addInitScript(() => {
    sessionStorage.setItem('opencli.bootstrapIdentityToken', 'test-token')
  })
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const reply = (data) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data }) })
    if (url.pathname.endsWith('/auth/me')) return reply({ subject: 'test-user', email: null, name: 'Test User', username: 'test', picture: null, is_platform_admin: true, auth_method: 'test' })
    if (url.pathname.endsWith('/workspaces')) return reply([workspace])
    if (url.pathname.endsWith('/chat/sessions') && route.request().method() === 'GET') return reply(created ? [conversation] : [])
    if (url.pathname.endsWith('/chat/sessions') && route.request().method() === 'POST') {
      created = true
      return reply(conversation)
    }
    if (url.pathname.endsWith('/chat/sessions/conversation-a') && route.request().method() === 'GET') return reply({ ...conversation, turns })
    if (url.pathname.endsWith('/chat/sessions/conversation-a/messages')) {
      const request = route.request().postDataJSON()
      const sequence = turns.length + 1
      const proposal = sequence === 2
        ? { type: 'proposal', proposal: { tool: 'update_provider', args: {}, summary: '更新模型连接', diff: 'enabled: false -> true', work_item_id: 'work-item-a', workspace_id: workspace.id, proposal_version: 'v1' } }
        : { type: 'message', content: '已恢复并继续处理。' }
      const turn = { sequence, request_id: request.request_id, status: proposal.type === 'proposal' ? 'proposal' : 'completed', user_content: request.content, response: proposal, context_binding: request.context, tool_trace: [], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }
      turns.push(turn)
      return reply({ conversation_id: conversation.id, turn })
    }
    if (url.pathname.endsWith('/chat/confirm')) {
      confirmationCount += 1
      return reply({ ok: true })
    }
    return reply({})
  })

  await page.goto('/dashboard?workspace=workspace-a')
  await page.getByRole('button', { name: 'Agent', exact: true }).click()
  await page.getByLabel('给全局 Agent 的消息').fill('恢复这个会话')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('已恢复并继续处理。')).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('opencli:agent-session:workspace-a'))).toBe('conversation-a')

  await page.reload()
  await page.getByRole('button', { name: 'Agent', exact: true }).click()
  await expect(page.getByText('恢复这个会话')).toBeVisible()
  await expect(page.getByText('已恢复并继续处理。')).toBeVisible()

  await page.getByLabel('给全局 Agent 的消息').fill('生成变更提案')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('待确认操作')).toBeVisible()
  await page.getByRole('button', { name: '确认执行' }).click()
  await expect.poll(() => confirmationCount).toBe(1)
})

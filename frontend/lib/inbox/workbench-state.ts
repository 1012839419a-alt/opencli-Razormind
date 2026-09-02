export type ApprovalAvailability =
  | 'loading'
  | 'ready'
  | 'no_workspace'
  | 'workspace_error'
  | 'inbox_error'

export type ApprovalAvailabilityInput = {
  workspaceLoading: boolean
  workspaceError: boolean
  workspaceCount: number
  workspaceId: string | null
  inboxLoading: boolean
  inboxError: boolean
}

export function resolveApprovalAvailability({
  workspaceLoading,
  workspaceError,
  workspaceCount,
  workspaceId,
  inboxLoading,
  inboxError,
}: ApprovalAvailabilityInput): ApprovalAvailability {
  if (workspaceError) return 'workspace_error'
  if (workspaceLoading) return 'loading'
  if (workspaceCount === 0 || !workspaceId) return 'no_workspace'
  if (inboxError) return 'inbox_error'
  if (inboxLoading) return 'loading'
  return 'ready'
}

const INTERACTIVE_TAGS: Record<string, true> = {
  A: true,
  BUTTON: true,
  INPUT: true,
  SELECT: true,
  SUMMARY: true,
  TEXTAREA: true,
}

export function shouldIgnoreInboxShortcut({
  tagName,
  isContentEditable,
  withinInteractive,
}: {
  tagName?: string
  isContentEditable?: boolean
  withinInteractive?: boolean
}): boolean {
  if (isContentEditable || withinInteractive) return true
  return tagName ? INTERACTIVE_TAGS[tagName.toUpperCase()] === true : false
}

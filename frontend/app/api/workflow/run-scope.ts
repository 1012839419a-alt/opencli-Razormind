export type WorkflowProxyScope = {
  workspaceId: string
  projectId: string
  workflowId: string
}

export function readWorkflowProxyScope(url: URL): WorkflowProxyScope | null {
  const workspaceId = url.searchParams.get("workspace")?.trim() ?? ""
  const projectId = url.searchParams.get("project")?.trim() ?? ""
  const workflowId = url.searchParams.get("workflow")?.trim() ?? ""
  if (!workspaceId && !projectId && !workflowId) return null
  if (!workspaceId || !projectId || !workflowId) {
    throw new Error("workspace, project, and workflow must be provided together")
  }
  return { workspaceId, projectId, workflowId }
}

export function backendWorkflowRunsRoot(scope: WorkflowProxyScope | null): string {
  if (!scope) return "/api/v1/workflows/runs"
  return [
    "/api/v1/workspaces",
    encodeURIComponent(scope.workspaceId),
    "projects",
    encodeURIComponent(scope.projectId),
    "workflows",
    encodeURIComponent(scope.workflowId),
    "runs",
  ].join("/")
}

import { backendWorkflowRunsRoot, readWorkflowProxyScope } from "../../../run-scope"
import { forwardedRequestAuthHeaders } from "@/lib/workflow/request-auth"

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8031"

export async function GET(req: Request, context: { params: Promise<{ runId: string }> }) {
  const { runId } = await context.params
  try {
    const url = new URL(req.url)
    const scope = readWorkflowProxyScope(url)
    url.searchParams.delete("workspace")
    url.searchParams.delete("project")
    url.searchParams.delete("workflow")
    const search = url.searchParams.toString()
    const response = await fetch(
      `${BACKEND_URL}${backendWorkflowRunsRoot(scope)}/${encodeURIComponent(runId)}/trace${search ? `?${search}` : ""}`,
      {
        headers: {
          ...forwardedRequestAuthHeaders(req),
        },
        cache: "no-store",
      },
    )
    const payload = await response.json().catch(() => null)
    return Response.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    })
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: "WORKFLOW_RUN_TRACE_FAILED",
        message: error instanceof Error ? error.message : "Unknown workflow run trace error",
      },
      { status: 502 },
    )
  }
}

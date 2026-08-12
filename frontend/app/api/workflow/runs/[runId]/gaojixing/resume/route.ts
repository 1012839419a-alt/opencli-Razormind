import { backendWorkflowRunsRoot, readWorkflowProxyScope } from "../../../../run-scope"
import { forwardedRequestAuthHeaders } from "@/lib/workflow/request-auth"

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8031"

export async function POST(req: Request, context: { params: Promise<{ runId: string }> }) {
  const { runId } = await context.params
  try {
    const scope = readWorkflowProxyScope(new URL(req.url))
    const response = await fetch(
      `${BACKEND_URL}${backendWorkflowRunsRoot(scope)}/${encodeURIComponent(runId)}/gaojixing/resume`,
      {
        method: "POST",
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
        error: "GAOJIXING_RUN_RESUME_FAILED",
        message: error instanceof Error ? error.message : "Unknown Gaojixing Run resume error",
      },
      { status: 502 },
    )
  }
}

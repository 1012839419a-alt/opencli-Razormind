import { forwardedRequestAuthHeaders } from "@/lib/workflow/request-auth"
import { backendWorkflowRunsRoot, readWorkflowProxyScope } from "../../run-scope"

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8031"
const MAX_QUESTION_BANK_MULTIPART_BYTES = 6 * 1024 * 1024

export async function POST(req: Request) {
  const contentType = req.headers.get("content-type") ?? ""
  if (!/^multipart\/form-data\s*;/i.test(contentType) || !/\bboundary=/i.test(contentType)) {
    return Response.json(
      {
        success: false,
        error: "QUESTION_BANK_RUN_CONTENT_TYPE_INVALID",
        message: "Question bank Runs require multipart/form-data.",
      },
      { status: 415 },
    )
  }
  const contentLength = Number(req.headers.get("content-length"))
  if (Number.isFinite(contentLength) && contentLength > MAX_QUESTION_BANK_MULTIPART_BYTES) {
    return Response.json(
      {
        success: false,
        error: "QUESTION_BANK_RUN_TOO_LARGE",
        message: "The question bank multipart request exceeds the 6 MiB limit.",
      },
      { status: 413 },
    )
  }

  try {
    const scope = readWorkflowProxyScope(new URL(req.url))
    const response = await fetch(`${BACKEND_URL}${backendWorkflowRunsRoot(scope)}/question-bank`, {
      method: "POST",
      headers: {
        ...forwardedRequestAuthHeaders(req),
        "Content-Type": contentType,
      },
      body: req.body,
      duplex: "half",
    } as RequestInit & { duplex: "half" })
    const payload = await response.json().catch(() => null)
    return Response.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    })
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: "QUESTION_BANK_RUN_FAILED",
        message: error instanceof Error ? error.message : "Unknown question bank Run error",
      },
      { status: 400 },
    )
  }
}

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8031"

export async function GET(req: Request, context: { params: Promise<{ runId: string }> }) {
  const { runId } = await context.params
  try {
    const response = await fetch(
      `${BACKEND_URL}/api/v1/workflows/runs/${encodeURIComponent(runId)}/research-ledger`,
      {
        headers: {
          ...(req.headers.get("authorization")
            ? { Authorization: req.headers.get("authorization") as string }
            : {}),
        },
        cache: "no-store",
      },
    )
    return Response.json(await response.json().catch(() => null), {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    })
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: "WORKFLOW_RESEARCH_LEDGER_FAILED",
        message: error instanceof Error ? error.message : "Unknown research ledger error",
      },
      { status: 502 },
    )
  }
}

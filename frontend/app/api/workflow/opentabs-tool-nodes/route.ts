export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8031"

export async function GET(req: Request) {
  try {
    const url = new URL(req.url)
    const response = await fetch(`${BACKEND_URL}/api/v1/workflows/opentabs-tool-nodes${url.search}`, {
      headers: {
        ...(req.headers.get("authorization")
          ? { Authorization: req.headers.get("authorization") as string }
          : {}),
      },
      cache: "no-store",
    })
    const payload = await response.json().catch(() => null)
    return Response.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    })
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: "WORKFLOW_OPENTABS_TOOL_NODES_FAILED",
        message: error instanceof Error ? error.message : "Unknown OpenTabs tool node error",
      },
      { status: 502 },
    )
  }
}

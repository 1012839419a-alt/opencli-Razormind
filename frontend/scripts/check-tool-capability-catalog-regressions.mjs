import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"
import { registerHooks, stripTypeScriptTypes } from "node:module"
import { test } from "node:test"
import { fileURLToPath, pathToFileURL } from "node:url"
import path from "node:path"

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

registerHooks({
  resolve(specifier, context, nextResolve) {
    const candidates = []
    if (specifier.startsWith("@/")) {
      candidates.push(path.join(frontendRoot, specifier.slice(2)))
    } else if (specifier.startsWith(".") && context.parentURL?.startsWith("file:")) {
      candidates.push(path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier))
    }
    for (const candidate of candidates) {
      for (const resolvedPath of [candidate, `${candidate}.ts`, `${candidate}.tsx`]) {
        if (existsSync(resolvedPath)) {
          return { url: pathToFileURL(resolvedPath).href, shortCircuit: true }
        }
      }
    }
    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".ts") || url.endsWith(".tsx")) {
      const source = stripTypeScriptTypes(readFileSync(fileURLToPath(url), "utf8"), {
        mode: "strip",
        sourceUrl: url,
      })
      return { format: "module", source, shortCircuit: true }
    }
    return nextLoad(url, context)
  },
})

test("backend tool capability becomes an executable catalog node", async () => {
  const { createWorkflowNodeFromCatalog, getWorkflowNodeCatalog } = await import(
    pathToFileURL(path.join(frontendRoot, "lib/workflow/node-catalog.ts")).href
  )
  const toolCapability = {
    id: "tool.osint.metasearch",
    versionPin: {
      package: "opencli-admin",
      packageVersion: "0.1.0",
      capabilityVersion: "1.0.0",
      provenance: "built-in",
    },
    executor: { mode: "fixture", params: { limit: 20 } },
  }
  const runtimeCapability = {
    id: "tool.osint.metasearch",
    label: "OSINT Metasearch",
    surface: "catalog",
    status: "runnable",
    backendAvailable: true,
    kind: "action",
    capability: "store",
    provider: "opencli-admin",
    runtimeBinding: "workflow.external-tool.capability",
    reason: "Search verified OSINT providers.",
    missing: [],
    tags: ["catalog", "tool-capability", "osint"],
    source: "backend.workflow.tool_capabilities",
    manifest: {
      canvas: { node: true },
      nodeCatalog: {
        authority: "backend",
        origin: "tool-capability",
        category: "processing",
      },
      presentation: {
        icon: "Search",
        parameters: [
          {
            name: "toolCapability",
            label: "Tool binding",
            type: "object",
            required: true,
            default: toolCapability,
          },
          {
            name: "toolParams",
            label: "Runtime parameters",
            type: "object",
            default: { limit: 20 },
          },
        ],
      },
    },
  }
  const capabilities = {
    version: "test",
    catalog: [runtimeCapability],
    primitives: [],
    channels: [],
    notifiers: [],
    triggers: [],
    resources: [],
  }

  const item = getWorkflowNodeCatalog("intelligence", capabilities).find(
    (candidate) => candidate.id === runtimeCapability.id,
  )
  assert.ok(item)
  assert.equal(item.kind, "action")
  assert.equal(item.capability, "store")
  assert.deepEqual(item.params.toolCapability, toolCapability)
  assert.deepEqual(item.params.toolParams, { limit: 20 })

  const node = createWorkflowNodeFromCatalog(item, "osint-search", { x: 80, y: 120 })
  assert.deepEqual(node.params.toolCapability, toolCapability)
  assert.deepEqual(node.params.toolParams, { limit: 20 })
  assert.equal(node.ui.catalogId, "tool.osint.metasearch")
})


test("backend source preset materializes its real adapter", async () => {
  const {
    addCatalogNodeToWorkflowProject,
    createWorkflowNodeFromCatalog,
    getWorkflowNodeCatalog,
  } = await import(
    pathToFileURL(path.join(frontendRoot, "lib/workflow/node-catalog.ts")).href
  )
  const sourceAdapter = {
    id: "source-searxng-http",
    type: "source",
    provider: "http",
    mode: "live",
    config: {
      channelType: "rest",
      method: "GET",
      query: { format: "json" },
    },
  }
  const runtimeCapability = {
    id: "intelligence.source.searxng",
    label: "SearXNG 元搜索 / Metasearch",
    surface: "catalog",
    status: "runnable",
    backendAvailable: true,
    kind: "source",
    capability: "fetch",
    provider: "http",
    runtimeBinding: "workflow.source.fetch",
    reason: "Runs the configured SearXNG JSON API.",
    missing: [],
    tags: ["source", "osint", "searxng"],
    source: "backend.workflow.http_source_executor",
    manifest: {
      canvas: { node: true },
      nodeCatalog: {
        authority: "backend",
        origin: "source-preset",
        category: "source",
        adapter: sourceAdapter,
      },
      presentation: {
        icon: "Search",
        parameters: [
          {
            name: "endpoint",
            label: "搜索地址 / Search endpoint",
            type: "string",
            required: true,
          },
          {
            name: "query",
            label: "查询参数 / Query parameters",
            type: "object",
            required: true,
            default: { q: "OpenCLI", format: "json" },
          },
        ],
      },
    },
  }
  const capabilities = {
    version: "test",
    catalog: [runtimeCapability],
    primitives: [],
    channels: [],
    notifiers: [],
    triggers: [],
    resources: [],
  }

  const item = getWorkflowNodeCatalog("intelligence", capabilities).find(
    (candidate) => candidate.id === runtimeCapability.id,
  )
  assert.ok(item)
  assert.equal(item.category, "source")
  assert.equal(item.adapter, sourceAdapter.id)
  assert.deepEqual(item.requiredAdapters, [sourceAdapter])

  const node = createWorkflowNodeFromCatalog(item, "searxng-source", { x: 80, y: 120 })
  assert.equal(node.adapter, sourceAdapter.id)
  assert.deepEqual(node.params.query, { q: "OpenCLI", format: "json" })

  const project = addCatalogNodeToWorkflowProject(
    {
      id: "source-preset-round-trip",
      name: "Source preset round trip",
      profile: "intelligence",
      version: 1,
      nodes: [
        {
          id: "start",
          kind: "schedule",
          capability: "trigger",
          params: {},
          ui: { label: "Start", position: { x: 0, y: 0 } },
        },
      ],
      edges: [],
      settings: {
        timezone: "Asia/Shanghai",
        deterministicSimulation: true,
        maxItemsPerRun: 20,
      },
      adapters: [],
      agentPermissions: {
        canFetchNetwork: true,
        canSendNotifications: false,
        canWriteInbox: true,
        allowedDomains: [],
      },
    },
    item,
    "searxng-source",
    { x: 80, y: 120 },
  )
  assert.deepEqual(project.adapters, [sourceAdapter])
  assert.equal(project.nodes.at(-1).adapter, sourceAdapter.id)

  const malformedCapability = {
    ...runtimeCapability,
    id: "intelligence.source.malformed",
    manifest: {
      ...runtimeCapability.manifest,
      nodeCatalog: {
        ...runtimeCapability.manifest.nodeCatalog,
        adapter: { id: "missing-required-fields" },
      },
    },
  }
  const malformedCatalog = getWorkflowNodeCatalog("intelligence", {
    ...capabilities,
    catalog: [malformedCapability],
  })
  assert.equal(
    malformedCatalog.some((candidate) => candidate.id === malformedCapability.id),
    false,
  )
})

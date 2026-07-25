import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"
import { fileURLToPath, pathToFileURL } from "node:url"
import { registerHooks, stripTypeScriptTypes } from "node:module"
import path from "node:path"

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "dagre") return { url: "dagre:test-stub", shortCircuit: true }
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
    if (url === "dagre:test-stub") {
      return {
        format: "module",
        source: "export default { graphlib: { Graph: class Graph {} }, layout() {} }",
        shortCircuit: true,
      }
    }
    if (url.endsWith(".ts") || url.endsWith(".tsx")) {
      return {
        format: "module",
        source: stripTypeScriptTypes(readFileSync(fileURLToPath(url), "utf8"), {
          mode: "strip",
        }),
        shortCircuit: true,
      }
    }
    if (url.endsWith(".json")) {
      return {
        format: "module",
        source: `export default ${readFileSync(fileURLToPath(url), "utf8")}`,
        shortCircuit: true,
      }
    }
    return nextLoad(url, context)
  },
})

const {
  dataOperatorsForCapability,
} = await import("../lib/workflow/capabilities.ts")
const {
  createDataOperatorParameterInterface,
  dataOperatorSelectionValue,
  parseJsonParameterValue,
  setParameterInterfaceFieldValue,
} = await import("../lib/workflow/parameter-interface.ts")
const {
  getWorkflowNodeCatalog,
  createWorkflowNodeFromCatalog,
} = await import("../lib/workflow/node-catalog.ts")
const {
  validateNodeContract,
} = await import("../lib/workflow/node-contracts.ts")
const {
  clearParameterDraftEntry,
  useFlowStore,
} = await import("../lib/flow/store.ts")

const operators = [
  operator("text.clean", "refine", "Clean Text"),
  operator("text.rule-filter", "filter", "Rule Filter"),
  operator("text.deduplicate", "filter", "Deduplicate"),
  operator("text.statistics", "evaluate", "Text Statistics"),
  operator("data.project", "refine", "Project Fields"),
  operator("data.chunk", "generate", "Chunk Data"),
  operator("data.chunk", "generate", "Chunk Data Next", "1.1.0"),
  operator("data.qa-extract", "generate", "Extract QA"),
  operator("data.training-format", "refine", "Training Format"),
]

const generateCapability = capability("intelligence.data.generate", operators)
assert.deepEqual(
  dataOperatorsForCapability(generateCapability, "generate").map((entry) => [entry.id, entry.version]),
  [
    ["data.chunk", "1.0.0"],
    ["data.chunk", "1.1.0"],
    ["data.qa-extract", "1.0.0"],
  ],
)

const interfaceProjection = createDataOperatorParameterInterface(
  "generate-1",
  "intelligence.data.generate",
  { operatorId: "data.chunk", packVersion: "1.0.0", config: { chunkSize: 600 } },
  generateCapability,
)
assert.ok(interfaceProjection)
const operatorField = interfaceProjection.fields.find((field) => field.binding.fieldId === "operatorId")
const configField = interfaceProjection.fields.find((field) => field.binding.fieldId === "config")
assert.equal(operatorField.type, "select")
assert.equal(operatorField.value, dataOperatorSelectionValue("data.chunk", "1.0.0"))
assert.deepEqual(operatorField.options.map((option) => option.value), [
  dataOperatorSelectionValue("data.chunk", "1.0.0"),
  dataOperatorSelectionValue("data.chunk", "1.1.0"),
  dataOperatorSelectionValue("data.qa-extract", "1.0.0"),
])
assert.match(operatorField.options[0].label, /builtin\.dataflow-deterministic@1\.0\.0 · runnable/)
assert.deepEqual(configField.value, { chunkSize: 600 })

const parsed = parseJsonParameterValue('{"chunkSize":800,"overlap":80}')
assert.equal(parsed.ok, true)
assert.deepEqual(parsed.value, { chunkSize: 800, overlap: 80 })
assert.equal(parseJsonParameterValue("[]").ok, false)
assert.equal(parseJsonParameterValue("{broken").ok, false)

const updatedInterface = setParameterInterfaceFieldValue(
  interfaceProjection,
  "operator.config",
  parsed.value,
)
assert.deepEqual(
  updatedInterface.fields.find((field) => field.id === "operator.config").value,
  { chunkSize: 800, overlap: 80 },
)

const catalogCapabilities = {
  version: "data-operator-test",
  catalog: ["generate", "filter", "evaluate", "refine"].map((kind) =>
    capability(`intelligence.data.${kind}`, operators),
  ),
  primitives: [],
  channels: [],
  notifiers: [],
  triggers: [],
  resources: [],
}
const catalog = getWorkflowNodeCatalog("intelligence", catalogCapabilities)
const dataNodes = catalog.filter((item) => item.id.startsWith("intelligence.data."))
assert.deepEqual(
  dataNodes.map((item) => item.id),
  [
    "intelligence.data.generate",
    "intelligence.data.filter",
    "intelligence.data.evaluate",
    "intelligence.data.refine",
  ],
)

const generated = createWorkflowNodeFromCatalog(
  dataNodes.find((item) => item.id === "intelligence.data.generate"),
  "generated-node",
  { x: 100, y: 200 },
)
assert.equal(generated.params.operatorId, "core.generate.instruction-pairs")
assert.equal(generated.params.packVersion, "1.0.0")
assert.deepEqual(generated.params.config, {})
const generatedOperatorField = generated.parameterInterface.fields
  .find((field) => field.binding.fieldId === "operatorId")
assert.equal(
  generatedOperatorField.value,
  dataOperatorSelectionValue("core.generate.instruction-pairs", "1.0.0"),
)
assert.deepEqual(
  generatedOperatorField.options.map((option) => option.value),
  [
    dataOperatorSelectionValue("core.generate.instruction-pairs", "1.0.0"),
    dataOperatorSelectionValue("data.chunk", "1.0.0"),
    dataOperatorSelectionValue("data.chunk", "1.1.0"),
    dataOperatorSelectionValue("data.qa-extract", "1.0.0"),
  ],
)

const validNode = {
  ...generated,
  params: {
    ...generated.params,
    operatorId: "data.chunk",
    packVersion: "1.0.0",
    config: parsed.value,
  },
}
assert.deepEqual(validateNodeContract(validNode), [])
assert.match(
  validateNodeContract({ ...validNode, params: { ...validNode.params, config: "{bad" } })[0].summary,
  /should be object/,
)

const baseProject = useFlowStore.getState().workflowProject
useFlowStore.getState().importWorkflowProject({
  ...baseProject,
  nodes: [{
    ...generated,
    params: {
      operatorId: "data.chunk",
      packVersion: "1.0.0",
      config: { chunkSize: 400 },
      fields: ["content"],
      chunkSize: 500,
      overlap: 50,
      legacyUnknownKey: true,
    },
  }],
  edges: [],
  adapters: [],
})
useFlowStore.getState().applyWorkflowCapabilities(catalogCapabilities)
assert.equal(
  useFlowStore.getState().workflowProject.nodes[0].params.packVersion,
  "1.0.0",
  "applying a manifest with a newer version must not upgrade a saved node",
)
useFlowStore.getState().updateParameterInterfaceField("generated-node", "operator.config", parsed.value)
assert.deepEqual(
  useFlowStore.getState().workflowProject.nodes[0].params.config,
  { chunkSize: 800, overlap: 80 },
)
useFlowStore.getState().updateParameterInterfaceField(
  "generated-node",
  "operator.operatorId",
  dataOperatorSelectionValue("data.chunk", "1.1.0"),
)
const switchedNode = useFlowStore.getState().workflowProject.nodes[0]
assert.deepEqual(switchedNode.params, {
  operatorId: "data.chunk",
  packVersion: "1.1.0",
  config: {},
})
assert.deepEqual(
  switchedNode.parameterInterface.fields.find((field) => field.id === "operator.config").value,
  {},
)
assert.equal(
  useFlowStore.getState().nodes[0].data.fields.find((field) => field.id === "operatorId").value,
  "data.chunk",
  "Canvas debug fields must not persist the composite selector value as the operator id",
)
useFlowStore.getState().updateParameterInterfaceField("generated-node", "operator.config", parsed.value)
useFlowStore.getState().updateParameterInterfaceField(
  "generated-node",
  "operator.operatorId",
  dataOperatorSelectionValue("data.qa-extract", "1.0.0"),
)
assert.deepEqual(useFlowStore.getState().workflowProject.nodes[0].params, {
  operatorId: "data.qa-extract",
  packVersion: "1.0.0",
  config: {},
})

const draftState = {
  "generated-node:operator.config": '{"chunkSize":400}',
  "other-node:operator.config": '{"keep":true}',
}
assert.deepEqual(
  clearParameterDraftEntry(draftState, "generated-node", "operator.config"),
  { "other-node:operator.config": '{"keep":true}' },
)
assert.deepEqual(draftState, {
  "generated-node:operator.config": '{"chunkSize":400}',
  "other-node:operator.config": '{"keep":true}',
})
const inspectorSource = readFileSync(
  path.join(frontendRoot, "components/flow/inspector.tsx"),
  "utf8",
)
assert.match(
  inspectorSource,
  /setJsonDrafts\(\(drafts\) => clearParameterDraftEntry\(drafts, configurationNodeId, configField\.id\)\)/,
)
assert.match(
  inspectorSource,
  /setJsonErrors\(\(errors\) => clearParameterDraftEntry\(errors, configurationNodeId, configField\.id\)\)/,
)
assert.match(inspectorSource, /field\.allowCustom/)
assert.match(inspectorSource, /field\.optional && !e\.target\.value/)

console.log("Data operator Canvas projection: OK")

function operator(id, kind, label, version = "1.0.0") {
  return {
    id,
    kind,
    label,
    pack: "builtin.dataflow-deterministic",
    version,
    status: "runnable",
    readiness: "runnable",
    configKeys: kind === "generate" ? ["chunkSize", "overlap"] : ["fields"],
  }
}

function capability(id, entries) {
  return {
    id,
    label: id,
    surface: "catalog",
    status: "runnable",
    backendAvailable: true,
    kind: "agent",
    capability: "normalize",
    missing: [],
    tags: ["data", "operator"],
    manifest: { operators: entries },
  }
}

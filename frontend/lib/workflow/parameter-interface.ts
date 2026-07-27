import type {
  ParameterInterface,
  ParameterInterfaceField,
  ParameterInterfaceGroup,
  WorkflowNode,
} from "@/lib/flow/types"
import type { AdapterBinding, WorkflowProjectNode } from "./schema"
import { getNodeInternals, type NodeInternals } from "./node-internals"
import { getNodeTemplate, readTemplateFieldValue, type NodeTemplate, type NodeTemplateField } from "./node-templates"
import {
  dataOperatorsForCapability,
  isUserFacingRuntimeParam,
  type DataOperatorKind,
  type WorkflowRuntimeCapability,
} from "./capabilities"

export type ParameterInterfaceMode = "template" | "exposed" | "summary"

export type ParameterInterfaceViewField = ParameterInterfaceField & {
  value: unknown
  readonly: boolean
}

export type ParameterInterfaceView = {
  mode: ParameterInterfaceMode
  title: string
  summary: string
  groups: ParameterInterfaceGroup[]
  fields: ParameterInterfaceViewField[]
}

const DATA_OPERATOR_KIND_BY_CATALOG_ID: Record<string, DataOperatorKind> = {
  "intelligence.data.generate": "generate",
  "intelligence.data.filter": "filter",
  "intelligence.data.evaluate": "evaluate",
  "intelligence.data.refine": "refine",
}

export function dataOperatorSelectionValue(operatorId: string, packVersion: string): string {
  return `${encodeURIComponent(operatorId)}@${encodeURIComponent(packVersion)}`
}

export function parseDataOperatorSelectionValue(
  value: unknown,
): { operatorId: string; packVersion: string } | undefined {
  if (typeof value !== "string") return undefined
  const separator = value.lastIndexOf("@")
  if (separator <= 0 || separator === value.length - 1) return undefined
  try {
    const operatorId = decodeURIComponent(value.slice(0, separator))
    const packVersion = decodeURIComponent(value.slice(separator + 1))
    return operatorId && packVersion ? { operatorId, packVersion } : undefined
  } catch {
    return undefined
  }
}

export function createDataOperatorParameterInterface(
  parentNodeId: string,
  catalogId: string,
  params: Record<string, unknown>,
  runtimeCapability?: WorkflowRuntimeCapability,
): ParameterInterface | undefined {
  const kind = DATA_OPERATOR_KIND_BY_CATALOG_ID[catalogId]
  if (!kind) return undefined
  const operators = dataOperatorsForCapability(runtimeCapability, kind)
  const configuredOperatorId = typeof params.operatorId === "string" ? params.operatorId : ""
  const configuredPackVersion = typeof params.packVersion === "string" ? params.packVersion : ""
  const selected =
    operators.find(
      (operator) =>
        operator.id === configuredOperatorId &&
        (!configuredPackVersion || operator.version === configuredPackVersion),
    ) ??
    operators[0]
  const operatorId = configuredOperatorId || selected?.id || ""
  const packVersion = configuredPackVersion || selected?.version || ""
  const config = isJsonRecord(params.config) ? params.config : {}
  const options = Array.from(
    new Map(operators.map((operator) => [
      dataOperatorSelectionValue(operator.id, operator.version),
      {
        value: dataOperatorSelectionValue(operator.id, operator.version),
        label: `${operator.label} · ${operator.pack}@${operator.version} · ${operator.readiness}`,
      },
    ])).values(),
  )
  const selectionValue = dataOperatorSelectionValue(operatorId, packVersion)
  if (
    operatorId &&
    packVersion &&
    !operators.some((operator) => operator.id === operatorId && operator.version === packVersion)
  ) {
    options.unshift({ value: selectionValue, label: `${operatorId} · ${packVersion} · unavailable` })
  }
  const configFields = selected
    ? dataOperatorConfigFields(parentNodeId, selected.configKeys, selected.configSchema, config)
    : []

  return {
    groups: [
      { id: "operator", label: "Data Operator", order: 1 },
      ...(configFields.length > 0 ? [{ id: "operator-config", label: "Configuration", order: 2 }] : []),
    ],
    fields: [
      {
        id: "operator.operatorId",
        label: "Operator",
        groupId: "operator",
        type: options.length > 0 ? "select" : "text",
        binding: { nodeId: parentNodeId, source: "params", fieldId: "operatorId" },
        description: options.length > 0
          ? "Versioned operators projected by the backend manifest. Each option shows pack, version, and readiness."
          : "Backend operator id.",
        order: 1,
        value: selectionValue,
        options,
      },
      ...configFields,
    ],
  }
}

function dataOperatorConfigFields(
  parentNodeId: string,
  configKeys: string[],
  configSchema: Record<string, unknown> | undefined,
  config: Record<string, unknown>,
): ParameterInterfaceField[] {
  const properties = isJsonRecord(configSchema?.properties)
    ? configSchema.properties
    : configSchema && !("type" in configSchema)
      ? Object.fromEntries(
          (configKeys.length > 0 ? configKeys : Object.keys(configSchema))
            .filter((key) => isJsonRecord(configSchema[key]))
            .map((key) => [key, configSchema[key]]),
        )
      : {}
  const schemaKeys = Object.keys(properties)
  const keys = Array.from(new Set([...configKeys, ...schemaKeys]))
  const required = new Set(Array.isArray(configSchema?.required)
    ? configSchema.required.filter((value): value is string => typeof value === "string")
    : [])

  return keys.map((key, order) => {
    const schema = isJsonRecord(properties[key]) ? properties[key] : {}
    const enumValues = Array.isArray(schema.enum)
      ? schema.enum.filter((value): value is string | number | boolean =>
          typeof value === "string" || typeof value === "number" || typeof value === "boolean",
        )
      : []
    const itemSchema = isJsonRecord(schema.items) ? schema.items : {}
    const itemEnum = Array.isArray(itemSchema.enum)
      ? itemSchema.enum.filter((value): value is string => typeof value === "string")
      : []
    const schemaType = typeof schema.type === "string" ? schema.type : undefined
    const fieldType: ParameterInterfaceField["type"] =
      enumValues.length > 0 ? "select"
        : schemaType === "boolean" ? "boolean"
          : schemaType === "integer" || schemaType === "number" ? "number"
            : schemaType === "array" && itemEnum.length > 0 ? "tokens"
              : schemaType === "object" || schemaType === "array" ? "json"
                : "text"
    const value = config[key] ?? schema.default ?? (
      fieldType === "boolean" ? false
        : fieldType === "tokens" ? []
          : fieldType === "json" ? (schemaType === "array" ? [] : {})
            : ""
    )

    return {
      id: `operator.config.${key}`,
      label: typeof schema.title === "string" ? schema.title : humanizeConfigKey(key),
      groupId: "operator-config",
      type: fieldType,
      binding: { nodeId: parentNodeId, source: "params", fieldId: `config.${key}` },
      description: typeof schema.description === "string"
        ? schema.description
        : `Operator configuration key: ${key}`,
      order,
      optional: !required.has(key),
      value,
      placeholder: typeof schema.placeholder === "string" ? schema.placeholder : undefined,
      min: typeof schema.minimum === "number" ? schema.minimum : undefined,
      max: typeof schema.maximum === "number" ? schema.maximum : undefined,
      step: schemaType === "integer" ? 1 : undefined,
      options: enumValues.length > 0
        ? enumValues.map((option) => ({ value: String(option), label: String(option) }))
        : itemEnum.map((option) => ({ value: option, label: option })),
    }
  })
}

function humanizeConfigKey(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export function parseJsonParameterValue(value: string): { ok: true; value: Record<string, unknown> | unknown[] } | { ok: false; error: string } {
  try {
    const parsed: unknown = JSON.parse(value)
    if (!isJsonRecord(parsed) && !Array.isArray(parsed)) {
      return { ok: false, error: "Value must be a JSON object or array." }
    }
    return { ok: true, value: parsed }
  } catch {
    return { ok: false, error: "Invalid JSON." }
  }
}

export function buildParameterInterfaceView({
  node,
  adapter,
  nodes = [],
  allowedParamIds,
  runtimeCapability,
}: {
  node: WorkflowProjectNode | undefined
  adapter?: AdapterBinding
  nodes?: WorkflowNode[]
  allowedParamIds?: string[]
  runtimeCapability?: WorkflowRuntimeCapability
}): ParameterInterfaceView | undefined {
  if (!node) return undefined
  const restrict = (view: ParameterInterfaceView) => restrictParameterInterface(view, allowedParamIds)
  const template = getNodeTemplate(node)
  if (template && prefersTemplateInterface(node)) {
    return restrict(templateInterfaceView(node, adapter, template))
  }

  const catalogId = typeof node.ui?.catalogId === "string" ? node.ui.catalogId : ""
  const parameterInterface =
    createDataOperatorParameterInterface(node.id, catalogId, node.params, runtimeCapability) ??
    node.parameterInterface ??
    createParameterInterfaceFromInternals(node.id, getNodeInternals(node))

  if (parameterInterface && parameterInterface.fields.length > 0) {
    const isPackage = typeof node.ui?.catalogId === "string" && node.ui.catalogId.startsWith("package.")
    return restrict({
      mode: "exposed",
      title: isPackage ? "Package Parameters" : "Node Parameters",
      summary: "Public parameters promoted from node internals.",
      groups: sortedGroups(parameterInterface.groups),
      fields: parameterInterface.fields
        .map((field) => ({
          ...field,
          readonly: field.readonly === true,
          value: readParameterFieldValue(node, field, adapter, nodes),
        }))
        .sort(compareFields),
    })
  }

  if (template) {
    return restrict(templateInterfaceView(node, adapter, template))
  }

  const internals = getNodeInternals(node)
  if (!internals) return undefined
  return restrict(internalsSummaryView(node, internals))
}

function restrictParameterInterface(
  view: ParameterInterfaceView,
  allowedParamIds: string[] | undefined,
): ParameterInterfaceView {
  const allowed = allowedParamIds ? new Set(allowedParamIds.filter(isUserFacingRuntimeParam)) : null
  return {
    ...view,
    fields: view.fields.filter((field) =>
      isUserFacingRuntimeParam(field.id) &&
      (
        !allowed ||
        allowed.has(field.id) ||
        allowed.has(field.binding.fieldId) ||
        (field.binding.fieldId.startsWith("config.") && allowed.has("params"))
      ),
    ),
  }
}

function prefersTemplateInterface(node: WorkflowProjectNode): boolean {
  return isCollectionNeedNode(node)
}

export function createParameterInterfaceFromInternals(
  parentNodeId: string,
  internals: NodeInternals | undefined,
): ParameterInterface | undefined {
  if (!internals) return undefined
  const fields = internals.steps.flatMap((step) =>
    (step.exposedParams ?? []).map((param): ParameterInterfaceField => ({
      id: `${step.id}.${param.id}`,
      label: param.label,
      groupId: param.groupId,
      type: param.type,
      binding: {
        nodeId: `${parentNodeId}__${step.id}`,
        source: param.binding?.source ?? "params",
        fieldId: param.binding?.fieldId ?? param.id,
      },
      description: param.description,
      order: param.order,
      readonly: param.readonly,
      optional: param.optional,
      allowCustom: param.allowCustom,
      value: param.value,
      placeholder: param.placeholder,
      min: param.min,
      max: param.max,
      step: param.step,
      options: param.options,
    })),
  )
  if (fields.length === 0) return undefined

  const groupsById = new Map<string, ParameterInterfaceGroup>()
  for (const step of internals.steps) {
    for (const param of step.exposedParams ?? []) {
      if (!groupsById.has(param.groupId)) {
        groupsById.set(param.groupId, {
          id: param.groupId,
          label: param.groupLabel,
          order: param.groupOrder,
        })
      }
    }
  }

  return {
    groups: sortedGroups(Array.from(groupsById.values())),
    fields: fields.sort(compareFields),
  }
}

export function setParameterInterfaceFieldValue(
  parameterInterface: ParameterInterface,
  fieldId: string,
  value: unknown,
): ParameterInterface {
  const target = parameterInterface.fields.find((field) => field.id === fieldId)
  const resetOperatorConfig =
    target?.binding.source === "params" &&
    target.binding.fieldId === "operatorId" &&
    parameterInterface.fields.some(
      (field) => field.binding.source === "params" && field.binding.fieldId.startsWith("config."),
    )
  return {
    ...parameterInterface,
    groups: [...parameterInterface.groups],
    fields: parameterInterface.fields.map((field) => {
      if (field.id === fieldId) return { ...field, value }
      if (resetOperatorConfig && field.binding.source === "params" && field.binding.fieldId.startsWith("config.")) {
        return { ...field, value: undefined }
      }
      return field
    }),
  }
}

function readParameterFieldValue(
  node: WorkflowProjectNode,
  field: ParameterInterfaceField,
  adapter: AdapterBinding | undefined,
  nodes: WorkflowNode[],
): unknown {
  const boundNode = nodes.find((candidate) => candidate.id === field.binding.nodeId)
  if (boundNode) {
    if (field.binding.source === "params") {
      return boundNode.data.fields?.find((candidate) => candidate.id === field.binding.fieldId)?.value ?? field.value ?? ""
    }
    if (field.binding.source === "data") {
      return boundNode.data[field.binding.fieldId] ?? field.value ?? ""
    }
  }

  if (field.binding.nodeId === node.id || field.binding.nodeId.startsWith(`${node.id}__`)) {
    if (field.binding.source === "params") {
      if (field.binding.fieldId === "operatorId" && field.id === "operator.operatorId") {
        const operatorId = typeof node.params.operatorId === "string" ? node.params.operatorId : ""
        const packVersion = typeof node.params.packVersion === "string" ? node.params.packVersion : ""
        return operatorId && packVersion
          ? dataOperatorSelectionValue(operatorId, packVersion)
          : field.value ?? ""
      }
      if (field.binding.fieldId.startsWith("config.")) {
        const config = isJsonRecord(node.params.config) ? node.params.config : {}
        return config[field.binding.fieldId.slice("config.".length)] ?? field.value ?? ""
      }
      return node.params[field.binding.fieldId] ?? field.value ?? ""
    }
    if (field.binding.source === "adapter") {
      if (field.binding.fieldId === "mode") return adapter?.mode ?? field.value ?? ""
      return adapter?.config[field.binding.fieldId] ?? field.value ?? ""
    }
    if (field.binding.source === "data") return node.ui?.[field.binding.fieldId] ?? field.value ?? ""
  }

  return field.value ?? ""
}

function templateFieldToParameterField(
  node: WorkflowProjectNode,
  adapter: AdapterBinding | undefined,
  field: NodeTemplateField,
  groupId: string,
  order: number,
): ParameterInterfaceViewField {
  return {
    id: field.id,
    label: field.label,
    groupId,
    type: field.type === "tokens" ? "tokens" : field.type,
    binding: {
      nodeId: node.id,
      source: field.source,
      fieldId: field.id,
    },
    description: field.description,
    order,
    readonly: false,
    optional: false,
    allowCustom: false,
    value: readTemplateFieldValue(node, adapter, field),
    placeholder: "placeholder" in field ? field.placeholder : undefined,
    min: "min" in field ? field.min : undefined,
    max: "max" in field ? field.max : undefined,
    step: "step" in field ? field.step : undefined,
    options: "options" in field ? field.options : undefined,
  }
}

function templateInterfaceView(
  node: WorkflowProjectNode,
  adapter: AdapterBinding | undefined,
  template: NodeTemplate,
): ParameterInterfaceView {
  const group = templateGroup(node)
  return {
    mode: "template",
    title: template.title,
    summary: template.summary,
    groups: [group],
    fields: template.fields.map((field, index) => templateFieldToParameterField(node, adapter, field, group.id, index)),
  }
}

function internalsSummaryView(node: WorkflowProjectNode, internals: NodeInternals): ParameterInterfaceView {
  return {
    mode: "summary",
    title: internals.title,
    summary: "No public parameters are declared. Internal steps are shown as readonly evidence.",
    groups: [{ id: "internals", label: "Internals", order: 1 }],
    fields: internals.steps.map((step, index) => ({
      id: step.id,
      label: step.label,
      groupId: "internals",
      type: "text",
      binding: { nodeId: node.id, source: "data", fieldId: step.id },
      description: step.description,
      order: index,
      readonly: true,
      value: step.evidence,
    })),
  }
}

function templateGroup(node: WorkflowProjectNode): ParameterInterfaceGroup {
  if (isCollectionNeedNode(node)) {
    return { id: "input", label: "Input", order: 1 }
  }
  if (node.kind === "source") return { id: "source", label: "Source", order: 1 }
  if (node.kind === "schedule") return { id: "transform", label: "Transform", order: 1 }
  if (node.kind === "notify" || node.kind === "inbox") return { id: "render", label: "Render", order: 1 }
  return { id: "parameters", label: "Parameters", order: 1 }
}

function sortedGroups(groups: ParameterInterfaceGroup[]): ParameterInterfaceGroup[] {
  return [...groups].sort((left, right) => (left.order ?? 0) - (right.order ?? 0) || left.label.localeCompare(right.label))
}

function compareFields(left: { groupId: string; order?: number; label: string }, right: { groupId: string; order?: number; label: string }) {
  return left.groupId.localeCompare(right.groupId) || (left.order ?? 0) - (right.order ?? 0) || left.label.localeCompare(right.label)
}

function isCollectionNeedNode(node: WorkflowProjectNode): boolean {
  if (node.ui?.catalogId === "intelligence.input.collection-need") return true
  if (node.kind !== "schedule" || node.capability !== "trigger") return false
  if (node.params.mode === "demand-draft") return true
  return hasNeedShape(node.params) && !hasScheduleShape(node.params)
}

function hasNeedShape(params: Record<string, unknown>): boolean {
  return typeof params.text === "string" || typeof params.locale === "string"
}

function hasScheduleShape(params: Record<string, unknown>): boolean {
  return typeof params.interval === "string" || typeof params.timezone === "string"
}

function isJsonRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

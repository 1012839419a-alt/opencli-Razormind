import type { WorkflowPrimitive, WorkflowPrimitiveCategory } from "./node-primitives"
import type { WorkflowLanguage } from "./node-i18n"

export const PRIMITIVE_MENU_ORDER: WorkflowPrimitiveCategory[] = [
  "input",
  "transform",
  "ai",
  "logic",
  "state",
  "output",
  "verify",
  "business",
  "ops",
  "core",
  "map",
]

export const PRIMITIVE_MENU_LABELS: Record<WorkflowPrimitiveCategory, Record<WorkflowLanguage, string>> = {
  input: { "zh-CN": "输入", "en-US": "Input" },
  transform: { "zh-CN": "数据处理", "en-US": "Data processing" },
  ai: { "zh-CN": "AI", "en-US": "AI" },
  logic: { "zh-CN": "逻辑", "en-US": "Logic" },
  state: { "zh-CN": "状态", "en-US": "State" },
  output: { "zh-CN": "输出", "en-US": "Output" },
  verify: { "zh-CN": "验证", "en-US": "Verification" },
  business: { "zh-CN": "业务", "en-US": "Business" },
  ops: { "zh-CN": "运维", "en-US": "Operations" },
  core: { "zh-CN": "核心", "en-US": "Core" },
  map: { "zh-CN": "知识映射", "en-US": "Knowledge mapping" },
}

export type PrimitiveMenuGroup = {
  category: WorkflowPrimitiveCategory
  label: string
  items: WorkflowPrimitive[]
}

export function groupPrimitivesForNodeMenu(
  primitives: WorkflowPrimitive[],
  language: WorkflowLanguage = "zh-CN",
): PrimitiveMenuGroup[] {
  return PRIMITIVE_MENU_ORDER.map((category) => ({
    category,
    label: PRIMITIVE_MENU_LABELS[category][language],
    items: primitives.filter((item) => item.category === category),
  })).filter((group) => group.items.length > 0)
}

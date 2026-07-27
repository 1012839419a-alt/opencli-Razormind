import type { WorkflowCapability, WorkflowNodeKind } from "./schema"
import type { WorkflowLanguage } from "./node-i18n"

export type BusinessNodeNamingInput = {
  label: string
  kind: WorkflowNodeKind
  capability: WorkflowCapability
  params?: Record<string, unknown>
  language?: WorkflowLanguage
}

/**
 * Names at L1 state the business action and object.  The persisted label is
 * never changed here: this is a display-only translation for older templates
 * and native package names that were written for implementers.
 */
export function businessNodeName({
  label,
  kind,
  capability,
  params,
  language = "zh-CN",
}: BusinessNodeNamingInput): string {
  const sourceLabel = label.trim()
  const template = typeof params?.template === "string" ? params.template : ""

  if (kind === "schedule") {
    return /^(采集调度|定时触发|Schedule|设置运行计划)$/i.test(sourceLabel)
      ? language === "zh-CN" ? "设置运行计划" : "Set run schedule"
      : sourceLabel
  }

  if (template === "opencli-multi-source" || Array.isArray(params?.sources)) {
    return isLegacyMultiSourceName(sourceLabel)
      ? language === "zh-CN"
        ? `采集 ${collectionSubject(sourceLabel, params?.sources)}`
        : `Collect ${collectionSubjectEn(sourceLabel, params?.sources)}`
      : sourceLabel
  }

  if (template === "record-hygiene" || capability === "accept" || /清洗|准入|去重|核验/.test(sourceLabel)) {
    return isLegacyHygieneName(sourceLabel)
      ? language === "zh-CN" ? "核验并准入数据" : "Validate and accept data"
      : sourceLabel
  }

  if (kind === "sink") {
    return isLegacyDatasetName(sourceLabel)
      ? language === "zh-CN" ? `更新 ${datasetSubject(sourceLabel)}` : "Update dataset"
      : sourceLabel
  }
  if (kind === "inbox") return language === "zh-CN" ? "提交人工复核" : "Submit for human review"
  if (kind === "notify") {
    return language === "zh-CN"
      ? `交付 ${deliverySubject(sourceLabel)}`
      : `Deliver ${deliverySubjectEn(sourceLabel)}`
  }
  if (capability === "summarize") return language === "zh-CN" ? "生成研判摘要" : "Generate analysis summary"
  if (capability === "score") return language === "zh-CN" ? "评估信息优先级" : "Score information priority"
  if (capability === "tag") return language === "zh-CN" ? "分类标注数据" : "Classify and tag data"
  if (capability === "route") return language === "zh-CN" ? "按规则分流结果" : "Route results by rule"

  return sourceLabel
}

function isLegacyMultiSourceName(label: string): boolean {
  return /OpenCLI|HDA|多源|多站点|multi[- ]site|multi[- ]source/i.test(label) ||
    /^(A\s*股)?市场数据采集$/i.test(label)
}

function isLegacyHygieneName(label: string): boolean {
  return /^(记录)?(数据)?清洗(与|和)?准入$|^(核验并准入数据)$/u.test(label) ||
    /^Record Hygiene(?: & Acceptance)?$/i.test(label)
}

function isLegacyDatasetName(label: string): boolean {
  return /^(A\s*股)?金融数据集$|^数据集$|^Records?$|^Record Sink$/i.test(label)
}

function collectionSubject(label: string, sources?: unknown): string {
  if (/A\s*股/i.test(label)) return "A 股市场数据"
  if (hasAShareSource(sources)) return "A 股市场数据"
  const subject = label
    .replace(/真实|多源|数据|信息|采集|HDA/gi, "")
    .trim()
  return subject ? `${subject}数据` : "多源数据"
}

function hasAShareSource(sources?: unknown): boolean {
  if (!Array.isArray(sources)) return false
  return /A\s*股|hs-a|沪深京/i.test(JSON.stringify(sources))
}

function collectionSubjectEn(label: string, sources?: unknown): string {
  if (/A\s*股/i.test(label) || hasAShareSource(sources)) return "A-share market data"
  return "multi-source data"
}

function datasetSubject(label: string): string {
  const subject = label.replace(/^更新\s*/u, "").trim()
  return subject || "数据集"
}

function deliverySubject(label: string): string {
  const subject = label.replace(/^(发送|交付)\s*/u, "").trim()
  return subject || "结果"
}

function deliverySubjectEn(label: string): string {
  const subject = label.replace(/^(send|deliver)\s*/iu, "").trim()
  return subject || "results"
}

import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import path from "node:path"

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const readSource = (relativePath) => readFile(path.join(frontendRoot, relativePath), "utf8")

const operators = {
  generate: { operatorId: "core.generate.instruction-pairs", params: ["instructionTemplate"], catalogParams: ["instructionTemplate"] },
  filter: {
    operatorId: "core.filter.quality",
    params: ["requiredFields", "minLength", "maxLength", "blocklist", "textField"],
    catalogParams: ["requiredFields", "minLength", "blocklist", "textField"],
  },
  evaluate: { operatorId: "core.evaluate.quality", params: ["minLength", "maxLength"], catalogParams: ["minLength"] },
  refine: {
    operatorId: "core.refine.text",
    params: ["fields", "unicodeForm", "redactEmail", "redactPhone"],
    catalogParams: ["fields", "unicodeForm", "redactEmail", "redactPhone"],
  },
}

const [catalog, contracts, internals, i18n, types, parameterInterface, inspector, store] = await Promise.all([
  readSource("lib/workflow/node-catalog.ts"),
  readSource("lib/workflow/node-contracts.ts"),
  readSource("lib/workflow/node-internals.ts"),
  readSource("lib/workflow/node-i18n.ts"),
  readSource("lib/flow/types.ts"),
  readSource("lib/workflow/parameter-interface.ts"),
  readSource("components/flow/inspector.tsx"),
  readSource("lib/flow/store.ts"),
])

for (const [name, { operatorId, params, catalogParams }] of Object.entries(operators)) {
  const catalogId = `intelligence.data.${name}`
  for (const source of [catalog, contracts, internals, i18n]) assert.match(source, new RegExp(catalogId.replaceAll(".", "\\.")))
  const catalogSection = sourceSection(catalog, `id: "${catalogId}"`, "keywords:")
  const contractSection = sourceSection(contracts, `"${catalogId}": contract(`, "runtime projection owns operator execution")
  const internalsSection = sourceSection(internals, `"${catalogId}": dataOperatorInternals(`, "),\n  \"intelligence.")
  assert.match(catalogSection, new RegExp(`operatorId: "${operatorId.replaceAll(".", "\\.")}"`))
  assert.match(contracts, new RegExp(`"${catalogId.replaceAll(".", "\\.")}":[\\s\\S]{0,700}"recordCandidate\\[\\] -> recordCandidate\\[\\]"`))
  for (const param of params) {
    assert.match(contractSection, new RegExp(`param\\("${param}"`), `${catalogId} contract is missing ${param}`)
    assert.match(internalsSection, new RegExp(`id: "${param}"`), `${catalogId} internals are missing ${param}`)
  }
  for (const param of catalogParams) assert.match(catalogSection, new RegExp(`\\b${param}:`), `${catalogId} catalog is missing ${param}`)
}

for (const name of ["filter", "evaluate"]) {
  const catalogId = `intelligence.data.${name}`
  const catalogSection = sourceSection(catalog, `id: "${catalogId}"`, "keywords:")
  const contractSection = sourceSection(contracts, `"${catalogId}": contract(`, "runtime projection owns operator execution")
  assert.doesNotMatch(catalogSection, /\bmaxLength:/, `${catalogId} must not persist a maxLength sentinel`)
  assert.match(contractSection, /param\("maxLength", "params", "number", false, undefined,/, `${catalogId} maxLength must be optional without a default`)
}

const filterInternals = sourceSection(internals, '"intelligence.data.filter": dataOperatorInternals(', '),\n  "intelligence.data.evaluate"')
assert.match(filterInternals, /id: "maxLength"[\s\S]{0,160}optional: true/)
assert.match(filterInternals, /id: "blocklist"[\s\S]{0,180}allowCustom: true/)
assert.match(types, /optional\?: boolean/)
assert.match(types, /allowCustom\?: boolean/)
assert.match(parameterInterface, /allowCustom: param\.allowCustom/)
assert.match(parameterInterface, /optional: param\.optional/)
assert.match(inspector, /field\.allowCustom/)
assert.match(inspector, /event\.key !== "Enter" && event\.key !== ","/)
assert.match(inspector, /e\.target\.value === "" && field\.optional \? undefined/)
assert.match(store, /if \(value === undefined\) delete next\[key\]/)
assert.match(store, /applyParamsPatch\(node\.params, \{ \[binding\.fieldId\]: value \}\)/)

console.log("data operator contracts: ok")

function sourceSection(source, start, end) {
  const startIndex = source.indexOf(start)
  assert.notEqual(startIndex, -1, `missing source section: ${start}`)
  const endIndex = source.indexOf(end, startIndex + start.length)
  assert.notEqual(endIndex, -1, `missing source section terminator: ${end}`)
  return source.slice(startIndex, endIndex)
}

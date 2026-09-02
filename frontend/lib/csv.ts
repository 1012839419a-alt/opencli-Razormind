const NEGATIVE_NUMBER = /^-(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$/

function neutralizeSpreadsheetFormula(text: string) {
  const significantIndex = text.search(/[^\s\u0000-\u001F\u007F]/)
  if (significantIndex === -1) return text

  const marker = text[significantIndex]
  if (
    (marker !== '=' && marker !== '+' && marker !== '@' && marker !== '-')
    || (marker === '-' && NEGATIVE_NUMBER.test(text.slice(significantIndex)))
  ) {
    return text
  }

  return `'${text}`
}

export function serializeCsvCell(value: unknown) {
  const text = neutralizeSpreadsheetFormula(value == null ? '' : String(value))
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

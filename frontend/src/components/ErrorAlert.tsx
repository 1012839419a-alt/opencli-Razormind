import { AlertCircle } from 'lucide-react'

interface Props {
  error: Error | string
  onRetry?: () => void
}

export default function ErrorAlert({ error, onRetry }: Props) {
  const message = error instanceof Error ? error.message : error
  return (
    <div className="telemetry-panel flex items-start gap-3 border-primary-500/40 bg-primary-500/10 p-4">
      <AlertCircle className="mt-0.5 shrink-0 text-primary-400" size={18} />
      <div className="flex-1">
        <p className="text-sm text-primary-100">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-2 font-telemetry text-xs font-semibold uppercase tracking-[0.14em] text-primary-200 underline hover:no-underline"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

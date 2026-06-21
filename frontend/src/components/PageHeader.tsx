interface Props {
  title: string
  description?: string
  action?: React.ReactNode
}

export default function PageHeader({ title, description, action }: Props) {
  return (
    <div className="mb-5 flex items-start justify-between border-l-2 border-primary-500 pl-3">
      <div className="min-w-0">
        <p className="telemetry-label mb-1">OPS CONSOLE</p>
        <h1 className="truncate text-2xl font-semibold uppercase text-zinc-50">{title}</h1>
        {description && (
          <p className="mt-1 max-w-3xl text-sm text-zinc-400">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

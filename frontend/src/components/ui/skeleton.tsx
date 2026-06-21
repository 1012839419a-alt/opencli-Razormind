import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-[2px] border border-white/8 bg-white/[0.055]", className)}
      {...props}
    />
  )
}

export { Skeleton }

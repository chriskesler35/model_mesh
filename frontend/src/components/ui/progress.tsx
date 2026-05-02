import * as React from 'react'

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number
}

export const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(function Progress(
  { className = '', value = 0, ...props },
  ref,
) {
  const safeValue = Math.max(0, Math.min(100, value))
  return (
    <div
      ref={ref}
      className={['relative h-4 w-full overflow-hidden rounded-full bg-slate-200', className].filter(Boolean).join(' ')}
      {...props}
    >
      <div
        className="h-full bg-slate-900 transition-all"
        style={{ width: `${safeValue}%` }}
      />
    </div>
  )
})
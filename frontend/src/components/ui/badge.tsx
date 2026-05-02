import * as React from 'react'

type BadgeVariant = 'default' | 'secondary' | 'outline'

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: BadgeVariant
}

const variantClasses: Record<BadgeVariant, string> = {
  default: 'bg-slate-900 text-white',
  secondary: 'bg-slate-100 text-slate-800',
  outline: 'border border-slate-200 text-slate-700',
}

export function Badge({ className = '', variant = 'default', ...props }: BadgeProps) {
  const classes = [
    'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
    variantClasses[variant],
    className,
  ].filter(Boolean).join(' ')

  return <div className={classes} {...props} />
}
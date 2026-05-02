import * as React from 'react'

type ButtonVariant = 'default' | 'outline' | 'secondary' | 'ghost'
type ButtonSize = 'default' | 'sm' | 'lg'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

const variantClasses: Record<ButtonVariant, string> = {
  default: 'bg-slate-900 text-white hover:bg-slate-800',
  outline: 'border border-slate-300 bg-white text-slate-900 hover:bg-slate-50',
  secondary: 'bg-slate-100 text-slate-900 hover:bg-slate-200',
  ghost: 'text-slate-700 hover:bg-slate-100',
}

const sizeClasses: Record<ButtonSize, string> = {
  default: 'h-10 px-4 py-2',
  sm: 'h-9 px-3 text-sm',
  lg: 'h-11 px-8',
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className = '', variant = 'default', size = 'default', type = 'button', ...props },
  ref,
) {
  const classes = [
    'inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 disabled:pointer-events-none disabled:opacity-50',
    variantClasses[variant],
    sizeClasses[size],
    className,
  ].filter(Boolean).join(' ')

  return <button ref={ref} type={type} className={classes} {...props} />
})
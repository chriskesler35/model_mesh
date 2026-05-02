import * as React from 'react'

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange'> {
  onCheckedChange?: (checked: boolean) => void
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { className = '', checked, onCheckedChange, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={!!checked}
      onChange={(event) => onCheckedChange?.(event.target.checked)}
      className={[
        'h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400',
        className,
      ].filter(Boolean).join(' ')}
      {...props}
    />
  )
})
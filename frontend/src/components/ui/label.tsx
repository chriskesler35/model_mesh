import * as React from 'react'

export type LabelProps = React.LabelHTMLAttributes<HTMLLabelElement>

export const Label = React.forwardRef<HTMLLabelElement, LabelProps>(function Label(
  { className = '', ...props },
  ref,
) {
  return <label ref={ref} className={['text-sm font-medium leading-none', className].filter(Boolean).join(' ')} {...props} />
})
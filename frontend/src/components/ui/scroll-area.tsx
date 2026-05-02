import * as React from 'react'

export interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {}

export const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(function ScrollArea(
  { className = '', ...props },
  ref,
) {
  return <div ref={ref} className={['overflow-auto', className].filter(Boolean).join(' ')} {...props} />
})
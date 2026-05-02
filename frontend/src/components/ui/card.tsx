import * as React from 'react'

type DivProps = React.HTMLAttributes<HTMLDivElement>
type HeadingProps = React.HTMLAttributes<HTMLHeadingElement>
type ParagraphProps = React.HTMLAttributes<HTMLParagraphElement>

export const Card = React.forwardRef<HTMLDivElement, DivProps>(function Card(
  { className = '', ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={['rounded-xl border bg-white text-slate-950 shadow-sm', className].filter(Boolean).join(' ')}
      {...props}
    />
  )
})

export const CardHeader = React.forwardRef<HTMLDivElement, DivProps>(function CardHeader(
  { className = '', ...props },
  ref,
) {
  return <div ref={ref} className={['flex flex-col space-y-1.5 p-6', className].filter(Boolean).join(' ')} {...props} />
})

export const CardTitle = React.forwardRef<HTMLParagraphElement, ParagraphProps>(function CardTitle(
  { className = '', ...props },
  ref,
) {
  return <h3 ref={ref} className={['font-semibold leading-none tracking-tight', className].filter(Boolean).join(' ')} {...props} />
})

export const CardDescription = React.forwardRef<HTMLParagraphElement, ParagraphProps>(function CardDescription(
  { className = '', ...props },
  ref,
) {
  return <p ref={ref} className={['text-sm text-slate-500', className].filter(Boolean).join(' ')} {...props} />
})

export const CardContent = React.forwardRef<HTMLDivElement, DivProps>(function CardContent(
  { className = '', ...props },
  ref,
) {
  return <div ref={ref} className={['p-6 pt-0', className].filter(Boolean).join(' ')} {...props} />
})

export const CardFooter = React.forwardRef<HTMLDivElement, DivProps>(function CardFooter(
  { className = '', ...props },
  ref,
) {
  return <div ref={ref} className={['flex items-center p-6 pt-0', className].filter(Boolean).join(' ')} {...props} />
})
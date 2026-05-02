import * as React from 'react'

interface DialogContextValue {
  open: boolean
  onOpenChange?: (open: boolean) => void
}

const DialogContext = React.createContext<DialogContextValue>({ open: false })

export interface DialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

export function Dialog({ open = false, onOpenChange, children }: DialogProps) {
  return <DialogContext.Provider value={{ open, onOpenChange }}>{children}</DialogContext.Provider>
}

export interface DialogContentProps extends React.HTMLAttributes<HTMLDivElement> {}

export const DialogContent = React.forwardRef<HTMLDivElement, DialogContentProps>(function DialogContent(
  { className = '', children, ...props },
  ref,
) {
  const { open, onOpenChange } = React.useContext(DialogContext)

  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => onOpenChange?.(false)}>
      <div
        ref={ref}
        className={['w-full rounded-xl border bg-white p-6 shadow-xl', className].filter(Boolean).join(' ')}
        onClick={(event) => event.stopPropagation()}
        {...props}
      >
        {children}
      </div>
    </div>
  )
})

export const DialogHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(function DialogHeader(
  { className = '', ...props },
  ref,
) {
  return <div ref={ref} className={['flex flex-col space-y-2 text-left', className].filter(Boolean).join(' ')} {...props} />
})

export const DialogTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(function DialogTitle(
  { className = '', ...props },
  ref,
) {
  return <h2 ref={ref} className={['text-lg font-semibold text-slate-900', className].filter(Boolean).join(' ')} {...props} />
})

export const DialogDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(function DialogDescription(
  { className = '', ...props },
  ref,
) {
  return <p ref={ref} className={['text-sm text-slate-500', className].filter(Boolean).join(' ')} {...props} />
})
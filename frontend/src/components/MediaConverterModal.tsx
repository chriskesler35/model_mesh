'use client'

import { Dialog, DialogContent } from '@/components/ui/dialog'
import MediaConverterTab from '@/components/MediaConverterTab'

interface MediaConverterModalProps {
  open: boolean
  onClose: () => void
}

export default function MediaConverterModal({ open, onClose }: MediaConverterModalProps) {
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto dark:bg-gray-900 dark:border-gray-700 relative">
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xl leading-none"
        >
          ✕
        </button>
        <MediaConverterTab />
      </DialogContent>
    </Dialog>
  )
}

'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback, useRef } from 'react'
import Link from 'next/link'


interface Image {
  id: string
  url: string
  revised_prompt?: string
  width: number
  height: number
  format: string
  prompt?: string
  model?: string
  created_at?: string
  variation_of?: string
}

interface ImageModel {
  id: string
  name: string
  available: boolean
  description: string
}

interface Workflow {
  id: string
  name: string
  description?: string
  category?: string
  default_checkpoint?: string
}

interface LocalComfyJob {
  id: string
  kind: 'variation' | 'edit'
  startedAt: number
}

const PAGE_SIZE = 50
const DEFAULT_MASK_BRUSH_SIZE = 40
const DEFAULT_LOCAL_DENOISE = 0.45
const DEFAULT_MASK_GROW = 8
const DEFAULT_MASK_FEATHER = 6

function hasPaintedMask(canvas: HTMLCanvasElement | null): boolean {
  if (!canvas) return false
  const ctx = canvas.getContext('2d')
  if (!ctx) return false
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data
  for (let index = 3; index < data.length; index += 4) {
    if (data[index] > 0) return true
  }
  return false
}

export default function GalleryPage() {
  const [images, setImages] = useState<Image[]>([])
  const [totalImages, setTotalImages] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedImage, setSelectedImage] = useState<Image | null>(null)
  const [generatingIds, setGeneratingIds] = useState<string[]>([])
  const [editingImage, setEditingImage] = useState<Image | null>(null)
  const [editPrompt, setEditPrompt] = useState('')
  const [editing, setEditing] = useState(false)
  const [uploadDragging, setUploadDragging] = useState(false)
  // Variation model selection (applies to all variation buttons)
  const [availableModels, setAvailableModels] = useState<ImageModel[]>([])
  const [variationModel, setVariationModel] = useState<string>('gemini-imagen')
  // ComfyUI img2img workflow selection (only relevant when variationModel === "comfyui-local")
  const [img2imgWorkflows, setImg2imgWorkflows] = useState<Workflow[]>([])
  const [variationWorkflow, setVariationWorkflow] = useState<string>('sdxl-img2img')
  const [localComfyJobs, setLocalComfyJobs] = useState<LocalComfyJob[]>([])
  const [localQueueElapsed, setLocalQueueElapsed] = useState(0)
  const [protectMaskEnabled, setProtectMaskEnabled] = useState(false)
  const [maskBrushSize, setMaskBrushSize] = useState(DEFAULT_MASK_BRUSH_SIZE)
  const [localDenoise, setLocalDenoise] = useState(DEFAULT_LOCAL_DENOISE)
  const [maskGrow, setMaskGrow] = useState(DEFAULT_MASK_GROW)
  const [maskFeather, setMaskFeather] = useState(DEFAULT_MASK_FEATHER)
  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const lightboxImageRef = useRef<HTMLImageElement | null>(null)
  const maskDrawingRef = useRef(false)
  const lastMaskPointRef = useRef<{ x: number; y: number } | null>(null)
  const isGenerating = useCallback((imageId: string) => generatingIds.includes(imageId), [generatingIds])

  const beginLocalComfyJob = useCallback((kind: 'variation' | 'edit') => {
    const jobId = `${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    setLocalComfyJobs(prev => [...prev, { id: jobId, kind, startedAt: Date.now() }])
    return jobId
  }, [])

  const finishLocalComfyJob = useCallback((jobId: string | null) => {
    if (!jobId) return
    setLocalComfyJobs(prev => prev.filter(job => job.id !== jobId))
  }, [])

  useEffect(() => {
    if (localComfyJobs.length === 0) {
      setLocalQueueElapsed(0)
      return
    }

    const updateElapsed = () => {
      const oldestStartedAt = Math.min(...localComfyJobs.map(job => job.startedAt))
      setLocalQueueElapsed(Math.max(0, Math.floor((Date.now() - oldestStartedAt) / 1000)))
    }

    updateElapsed()
    const intervalId = window.setInterval(updateElapsed, 500)
    return () => window.clearInterval(intervalId)
  }, [localComfyJobs])

  // Moved to component scope so all handlers can call it
  const fetchImages = useCallback(async (pageNum: number = 0) => {
    setLoading(true)
    setError(null)
    try {
      const offset = pageNum * PAGE_SIZE
      const res = await fetch(`${API_BASE}/v1/images/?limit=${PAGE_SIZE}&offset=${offset}`, {
        headers: AUTH_HEADERS
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
      const data = await res.json()
      setImages(data.data || [])
      setTotalImages(data.total || 0)
    } catch (e: any) {
      console.error('Failed to fetch images:', e)
      setError(e.message || 'Failed to load images')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchImages(page)
  }, [fetchImages, page])

  // Fetch available image generation models (for variation selector)
  useEffect(() => {
    fetch(`${API_BASE}/v1/images/models/available`, {
      headers: AUTH_HEADERS
    })
      .then(r => r.ok ? r.json() : { data: [] })
      .then(d => {
        const models: ImageModel[] = d.data || []
        setAvailableModels(models)
        // Default to first available model
        const firstAvailable = models.find(m => m.available)
        if (firstAvailable) setVariationModel(firstAvailable.id)
      })
      .catch(() => {})
  }, [])

  // Fetch ALL workflows (used when user picks ComfyUI for variation).
  // The backend auto-injects LoadImage/VAEEncode into txt2img workflows so
  // ANY workflow can be used for variations — including uncensored ones.
  useEffect(() => {
    fetch(`${API_BASE}/v1/workflows`, {
      headers: AUTH_HEADERS
    })
      .then(r => r.ok ? r.json() : { data: [] })
      .then(d => {
        const all: Workflow[] = d.data || []
        // Sort: img2img workflows first, then the rest alphabetically
        all.sort((a, b) => {
          const aImg = a.category === 'img2img' ? 0 : 1
          const bImg = b.category === 'img2img' ? 0 : 1
          if (aImg !== bImg) return aImg - bImg
          return (a.name || a.id).localeCompare(b.name || b.id)
        })
        setImg2imgWorkflows(all)
        // Default to sdxl-img2img if present, else the first workflow
        const preferred = all.find(w => w.id === 'sdxl-img2img') || all[0]
        if (preferred) setVariationWorkflow(preferred.id)
      })
      .catch(() => {})
  }, [])

  const totalPages = Math.ceil(totalImages / PAGE_SIZE)

  const clearProtectionMask = useCallback(() => {
    const canvas = maskCanvasRef.current
    const ctx = canvas?.getContext('2d')
    if (canvas && ctx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    }
    maskDrawingRef.current = false
    lastMaskPointRef.current = null
  }, [])

  const syncMaskCanvas = useCallback(() => {
    const canvas = maskCanvasRef.current
    const image = lightboxImageRef.current
    if (!canvas || !image) return

    const width = Math.max(1, Math.round(image.clientWidth))
    const height = Math.max(1, Math.round(image.clientHeight))
    if (width === 0 || height === 0) return

    if (canvas.width === width && canvas.height === height) return

    const snapshot = document.createElement('canvas')
    snapshot.width = canvas.width || width
    snapshot.height = canvas.height || height
    const snapshotCtx = snapshot.getContext('2d')
    if (snapshotCtx && canvas.width > 0 && canvas.height > 0) {
      snapshotCtx.drawImage(canvas, 0, 0)
    }

    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, width, height)
    if (snapshot.width > 0 && snapshot.height > 0) {
      ctx.drawImage(snapshot, 0, 0, width, height)
    }
  }, [])

  useEffect(() => {
    syncMaskCanvas()
    const handleResize = () => syncMaskCanvas()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [selectedImage, editingImage, syncMaskCanvas])

  useEffect(() => {
    clearProtectionMask()
    setProtectMaskEnabled(false)
  }, [selectedImage?.id, clearProtectionMask])

  const drawProtectionStroke = useCallback((start: { x: number; y: number }, end: { x: number; y: number }) => {
    const canvas = maskCanvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.save()
    ctx.strokeStyle = 'rgba(239, 68, 68, 0.8)'
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.lineWidth = maskBrushSize
    ctx.beginPath()
    ctx.moveTo(start.x, start.y)
    ctx.lineTo(end.x, end.y)
    ctx.stroke()
    ctx.restore()
  }, [maskBrushSize])

  const getCanvasPoint = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = maskCanvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    if (!rect.width || !rect.height) return null
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height),
    }
  }, [])

  const handleMaskPointerDown = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!protectMaskEnabled) return
    const point = getCanvasPoint(event)
    if (!point) return
    maskDrawingRef.current = true
    lastMaskPointRef.current = point
    event.currentTarget.setPointerCapture(event.pointerId)
    drawProtectionStroke(point, point)
  }, [drawProtectionStroke, getCanvasPoint, protectMaskEnabled])

  const handleMaskPointerMove = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!maskDrawingRef.current) return
    const point = getCanvasPoint(event)
    const lastPoint = lastMaskPointRef.current
    if (!point || !lastPoint) return
    drawProtectionStroke(lastPoint, point)
    lastMaskPointRef.current = point
  }, [drawProtectionStroke, getCanvasPoint])

  const handleMaskPointerUp = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    maskDrawingRef.current = false
    lastMaskPointRef.current = null
  }, [])

  const exportProtectionMask = useCallback(() => {
    const visibleCanvas = maskCanvasRef.current
    const image = lightboxImageRef.current
    if (!visibleCanvas || !image || !hasPaintedMask(visibleCanvas)) return null

    const naturalWidth = image.naturalWidth || selectedImage?.width || visibleCanvas.width
    const naturalHeight = image.naturalHeight || selectedImage?.height || visibleCanvas.height
    const scaledCanvas = document.createElement('canvas')
    scaledCanvas.width = naturalWidth
    scaledCanvas.height = naturalHeight
    const scaledCtx = scaledCanvas.getContext('2d')
    if (!scaledCtx) return null
    scaledCtx.drawImage(visibleCanvas, 0, 0, naturalWidth, naturalHeight)

    const imageData = scaledCtx.getImageData(0, 0, naturalWidth, naturalHeight)
    const pixels = imageData.data
    for (let index = 0; index < pixels.length; index += 4) {
      const alpha = pixels[index + 3]
      const editableValue = alpha > 0 ? 0 : 255
      pixels[index] = editableValue
      pixels[index + 1] = editableValue
      pixels[index + 2] = editableValue
      pixels[index + 3] = 255
    }
    scaledCtx.putImageData(imageData, 0, 0)
    return scaledCanvas.toDataURL('image/png').split(',')[1]
  }, [selectedImage])

  // Lightbox navigation — go to prev/next image (crosses page boundaries)
  const navigateLightbox = useCallback((direction: 'prev' | 'next') => {
    if (!selectedImage || images.length === 0) return
    const idx = images.findIndex(img => img.id === selectedImage.id)
    if (idx < 0) return
    if (direction === 'next') {
      if (idx < images.length - 1) {
        setSelectedImage(images[idx + 1])
      } else if (page < totalPages - 1) {
        // Load next page, then select first image of that page
        setPage(p => p + 1)
        // selectedImage stays the same until new images load; the effect below re-syncs
      }
    } else {
      if (idx > 0) {
        setSelectedImage(images[idx - 1])
      } else if (page > 0) {
        // Load previous page, then select last image of that page
        setPage(p => p - 1)
      }
    }
  }, [selectedImage, images, page, totalPages])

  // After loading a new page from lightbox navigation, jump to the appropriate edge image
  const pendingLightboxEdgeRef = useRef<'first' | 'last' | null>(null)
  useEffect(() => {
    if (!selectedImage || images.length === 0) return
    const stillExists = images.some(img => img.id === selectedImage.id)
    if (stillExists) {
      pendingLightboxEdgeRef.current = null
      return
    }
    // Selected image not on current page — pick edge based on pending intent
    if (pendingLightboxEdgeRef.current === 'first') {
      setSelectedImage(images[0])
    } else if (pendingLightboxEdgeRef.current === 'last') {
      setSelectedImage(images[images.length - 1])
    }
    pendingLightboxEdgeRef.current = null
  }, [images, selectedImage])

  // Mark the expected edge before page change when navigating across pages
  const navigateLightboxWrapped = useCallback((direction: 'prev' | 'next') => {
    if (!selectedImage || images.length === 0) return
    const idx = images.findIndex(img => img.id === selectedImage.id)
    if (direction === 'next' && idx === images.length - 1 && page < totalPages - 1) {
      pendingLightboxEdgeRef.current = 'first'
    } else if (direction === 'prev' && idx === 0 && page > 0) {
      pendingLightboxEdgeRef.current = 'last'
    }
    navigateLightbox(direction)
  }, [selectedImage, images, page, totalPages, navigateLightbox])

  // Keyboard navigation — arrow keys + Escape
  useEffect(() => {
    if (!selectedImage) return
    const handler = (e: KeyboardEvent) => {
      // Don't hijack keys when user is typing in the edit prompt input
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowRight') { e.preventDefault(); navigateLightboxWrapped('next') }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); navigateLightboxWrapped('prev') }
      else if (e.key === 'Escape') { setSelectedImage(null) }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [selectedImage, navigateLightboxWrapped])

  // Current lightbox index for UI display
  const lightboxIdx = selectedImage ? images.findIndex(img => img.id === selectedImage.id) : -1
  const canGoPrev = selectedImage && (lightboxIdx > 0 || page > 0)
  const canGoNext = selectedImage && (lightboxIdx >= 0 && (lightboxIdx < images.length - 1 || page < totalPages - 1))

  const downloadImage = async (image: Image) => {
    try {
      const response = await fetch(`${API_BASE}${image.url}`, {
        headers: AUTH_HEADERS
      })
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `devforgeai-${image.id}.${image.format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (e) {
      console.error('Failed to download image:', e)
    }
  }

  const editImage = async (image: Image, prompt: string) => {
    if (!prompt.trim()) return
    const maskBase64 = exportProtectionMask()
    if (variationModel === 'comfyui-local' && image.format.toLowerCase() !== 'png') {
      alert('ComfyUI edits currently require a PNG source image. Re-upload or convert this image to PNG, or switch to Gemini.')
      return
    }
    if (maskBase64 && variationModel !== 'comfyui-local') {
      alert('Protected-area masking currently requires the ComfyUI (Local) model.')
      return
    }
    const isLocal = variationModel === 'comfyui-local'
    const localJobId = isLocal ? beginLocalComfyJob('edit') : null
    setEditing(true)
    try {
      const body: any = {
        source_image_id: image.id,
        prompt: prompt.trim(),
        model: variationModel,
      }
      if (variationModel === 'comfyui-local') {
        body.workflow_id = variationWorkflow
        body.denoise = localDenoise
        if (maskBase64) {
          body.mask_grow = maskGrow
          body.mask_feather = maskFeather
        }
      }
      if (maskBase64) {
        body.mask_base64 = maskBase64
        body.mask_mime = 'image/png'
      }
      const response = await fetch(`${API_BASE}/v1/images/edit`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify(body)
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Edit failed')
      if (data.data?.[0]) {
        clearProtectionMask()
        setProtectMaskEnabled(false)
        setEditingImage(null)
        setEditPrompt('')
        setSelectedImage(null)
        setPage(0)
        await fetchImages(0)
      }
    } catch (e: any) {
      alert('Edit failed: ' + e.message)
    } finally {
      finishLocalComfyJob(localJobId)
      setEditing(false)
    }
  }

  const handleUpload = async (file: File) => {
    const reader = new FileReader()
    reader.onload = async () => {
      const base64 = (reader.result as string).split(',')[1]
      try {
        const response = await fetch(`${API_BASE}/v1/images/upload`, {
          method: 'POST',
          headers: AUTH_HEADERS,
          body: JSON.stringify({ base64, filename: file.name, mime_type: file.type || 'image/png' })
        })
        if (response.ok) {
          setPage(0)
          await fetchImages(0)
        } else {
          const data = await response.json()
          alert('Upload failed: ' + (data.detail || response.status))
        }
      } catch (e: any) {
        alert('Upload failed: ' + e.message)
      }
    }
    reader.readAsDataURL(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setUploadDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) handleUpload(file)
  }

  const deleteImage = async (imageId: string) => {
    if (!confirm('Are you sure you want to delete this image?')) return
    try {
      await fetch(`${API_BASE}/v1/images/${imageId}`, {
        method: 'DELETE',
        headers: AUTH_HEADERS
      })
      setImages(images.filter(img => img.id !== imageId))
      if (selectedImage?.id === imageId) setSelectedImage(null)
    } catch (e) {
      console.error('Failed to delete image:', e)
    }
  }

  const generateVariation = async (imageId: string, modelId?: string) => {
    setGeneratingIds(prev => prev.includes(imageId) ? prev : [...prev, imageId])
    const chosenModel = modelId || variationModel
    const isLocal = chosenModel === 'comfyui-local'
    const maskBase64 = selectedImage?.id === imageId ? exportProtectionMask() : null
    const sourceImage = images.find((image) => image.id === imageId) || selectedImage

    if (isLocal && sourceImage?.format.toLowerCase() !== 'png') {
      alert('ComfyUI variations currently require a PNG source image. Re-upload or convert this image to PNG, or switch to Gemini.')
      setGeneratingIds(prev => prev.filter(id => id !== imageId))
      return
    }

    if (maskBase64 && !isLocal) {
      alert('Protected-area masking currently requires the ComfyUI (Local) model.')
      setGeneratingIds(prev => prev.filter(id => id !== imageId))
      return
    }

    const localJobId = isLocal ? beginLocalComfyJob('variation') : null

    try {
      const body: any = { model: chosenModel }
      // Include workflow_id only when using ComfyUI (Gemini ignores it)
      if (isLocal && variationWorkflow) {
        body.workflow_id = variationWorkflow
        body.denoise = localDenoise
        if (maskBase64) {
          body.mask_grow = maskGrow
          body.mask_feather = maskFeather
        }
      }
      if (maskBase64) {
        body.mask_base64 = maskBase64
        body.mask_mime = 'image/png'
      }
      const response = await fetch(`${API_BASE}/v1/images/${imageId}/variations`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify(body)
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Failed to generate variation')
      if (data.data?.[0]) {
        // Variations are saved to data/images/ — refresh to pull in the new file + keep sort order
        clearProtectionMask()
        setProtectMaskEnabled(false)
        setPage(0)
        await fetchImages(0)
        setSelectedImage(null)
      }
    } catch (e: any) {
      console.error('Failed to generate variation:', e)
      alert('Variation failed: ' + e.message)
    } finally {
      finishLocalComfyJob(localJobId)
      setGeneratingIds(prev => prev.filter(id => id !== imageId))
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500 dark:text-gray-400">Loading images...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
        <div className="text-red-500 dark:text-red-400">Error: {error}</div>
        <button
          onClick={() => fetchImages(page)}
          className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 text-sm"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Image Gallery</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {totalImages} image{totalImages !== 1 ? 's' : ''} · newest first
            {totalPages > 1 && (
              <span> · page {page + 1} of {totalPages}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {availableModels.length > 0 && (
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Variation model:</label>
              <select
                value={variationModel}
                onChange={(e) => setVariationModel(e.target.value)}
                className="px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white rounded-md focus:outline-none focus:ring-1 focus:ring-orange-400"
                title="Model used for variations"
              >
                {availableModels.map(m => (
                  <option key={m.id} value={m.id} disabled={!m.available}>
                    {m.name}{!m.available ? ' (unavailable)' : ''}
                  </option>
                ))}
              </select>
              {variationModel === 'comfyui-local' && (
                img2imgWorkflows.length > 0 ? (
                  <select
                    value={variationWorkflow}
                    onChange={(e) => setVariationWorkflow(e.target.value)}
                    className="px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white rounded-md focus:outline-none focus:ring-1 focus:ring-orange-400"
                    title="ComfyUI workflow — non-img2img workflows will be auto-converted"
                  >
                    {img2imgWorkflows.map(w => {
                      const isImg = w.category === 'img2img'
                      const suffix = isImg ? '' : ' (txt2img → auto-img2img)'
                      return (
                        <option key={w.id} value={w.id}>{w.name || w.id}{suffix}</option>
                      )
                    })}
                  </select>
                ) : (
                  <span className="text-[10px] text-amber-600 dark:text-amber-400" title="No workflows found in data/workflows/">
                    no workflows
                  </span>
                )
              )}
            </div>
          )}
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-2 py-1 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-md disabled:opacity-40 disabled:cursor-not-allowed"
                title="Previous page"
              >
                ←
              </button>
              <span className="text-xs text-gray-500 dark:text-gray-400 min-w-[60px] text-center">
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-2 py-1 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-md disabled:opacity-40 disabled:cursor-not-allowed"
                title="Next page"
              >
                →
              </button>
            </div>
          )}
          <button
            onClick={() => fetchImages(page)}
            className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-md"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Queue-aware status for local ComfyUI work */}
      {localComfyJobs.length > 0 && (() => {
        const steps = [
          { label: 'Uploading source image to ComfyUI', hint: 'Sending your image to the local ComfyUI instance' },
          { label: 'Loading workflow & model', hint: 'Loading the checkpoint, LoRA, and VAE (slowest on first run — model has to load into VRAM)' },
          { label: 'Running local generation', hint: 'ComfyUI is processing one job at a time on the GPU. Additional requests wait in its queue.' },
          { label: 'Decoding & saving image', hint: 'VAE decode → PNG → saved to data/images/' },
        ]
        let activeStep = 0
        if (localQueueElapsed >= 3) activeStep = 1
        if (localQueueElapsed >= 15) activeStep = 2
        if (localQueueElapsed >= 45) activeStep = 3
        const queuedCount = Math.max(0, localComfyJobs.length - 1)
        const editCount = localComfyJobs.filter(job => job.kind === 'edit').length
        const variationCount = localComfyJobs.filter(job => job.kind === 'variation').length
        return (
          <div className="mb-4 rounded-xl border-2 border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-900/20 p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  {[0,1,2].map(i => (
                    <span key={i} className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />
                  ))}
                </div>
                <span className="text-sm font-semibold text-indigo-900 dark:text-indigo-100">
                  Local ComfyUI queue active
                </span>
              </div>
              <span className="text-xs text-indigo-700 dark:text-indigo-300 font-mono">
                {localQueueElapsed}s elapsed
              </span>
            </div>
            <p className="text-xs text-indigo-700 dark:text-indigo-300 mb-3">
              {variationCount > 0 && editCount > 0
                ? `${variationCount} variation${variationCount === 1 ? '' : 's'} and ${editCount} edit${editCount === 1 ? '' : 's'} are in flight from this browser session.`
                : variationCount > 0
                  ? `${variationCount} local variation${variationCount === 1 ? '' : 's'} are in flight from this browser session.`
                  : `${editCount} local edit${editCount === 1 ? '' : 's'} are in flight from this browser session.`}
              {' '}
              {queuedCount > 0
                ? `ComfyUI is processing one now and has ${queuedCount} additional request${queuedCount === 1 ? '' : 's'} queued. Results will arrive one at a time as each job finishes.`
                : 'ComfyUI is processing this request now. Any additional local edits or variations you start will be queued and delivered over time.'}
            </p>
            <div className="space-y-1.5">
              {steps.map((s, i) => {
                const done = i < activeStep
                const active = i === activeStep
                return (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className={`flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold mt-0.5 ${
                      done ? 'bg-green-500 text-white' :
                      active ? 'bg-indigo-500 text-white animate-pulse' :
                      'bg-gray-200 dark:bg-gray-700 text-gray-400'
                    }`}>
                      {done ? '✓' : i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className={`font-medium ${
                        done ? 'text-green-700 dark:text-green-400 line-through opacity-70' :
                        active ? 'text-indigo-900 dark:text-indigo-100' :
                        'text-gray-400 dark:text-gray-500'
                      }`}>
                        {s.label}
                      </div>
                      {active && (
                        <div className="text-[11px] text-indigo-600 dark:text-indigo-400 mt-0.5 italic">{s.hint}</div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })()}

      {/* Upload Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setUploadDragging(true) }}
        onDragLeave={() => setUploadDragging(false)}
        className={`mb-6 border-2 border-dashed rounded-2xl p-6 text-center transition-colors cursor-pointer ${
          uploadDragging
            ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/10'
            : 'border-gray-200 dark:border-gray-700 hover:border-orange-300'
        }`}
        onClick={() => {
          const input = document.createElement('input')
          input.type = 'file'
          input.accept = 'image/*'
          input.onchange = (e: any) => { if (e.target.files[0]) handleUpload(e.target.files[0]) }
          input.click()
        }}
      >
        <div className="text-2xl mb-1">🖼️</div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Drop an image here or click to upload
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          Upload a photo, then edit it with AI
        </p>
      </div>

      {images.length === 0 ? (
        <div className="text-center py-12">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">No images yet</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Generate images in the chat to see them here.
          </p>
          <Link
            href="/chat"
            className="mt-4 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-orange-600 hover:bg-orange-700"
          >
            Start Chatting
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {images.map((image) => (
            <div
              key={image.id}
              className="group relative bg-white dark:bg-gray-800 rounded-lg shadow-sm overflow-hidden cursor-pointer"
              onClick={() => setSelectedImage(image)}
            >
              <div className="aspect-square">
                <img
                  src={`${API_BASE}/v1/img/${image.id}`}
                  alt={image.revised_prompt || 'Generated image'}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = '/favicon.svg'
                  }}
                />
              </div>
              <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-50 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100">
                <div className="flex gap-2">
                  <button
                    onClick={(e) => { e.stopPropagation(); downloadImage(image) }}
                    className="p-2 bg-white rounded-full text-gray-900 hover:bg-gray-100"
                    title="Download"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); generateVariation(image.id) }}
                    className="p-2 bg-white rounded-full text-orange-600 hover:bg-gray-100 disabled:opacity-50"
                    title={`Generate Variation (${availableModels.find(m => m.id === variationModel)?.name || variationModel})`}
                    disabled={isGenerating(image.id)}
                  >
                    <svg className={`w-5 h-5 ${isGenerating(image.id) ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteImage(image.id) }}
                    className="p-2 bg-white rounded-full text-red-600 hover:bg-gray-100"
                    title="Delete"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {selectedImage && (
        <div
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedImage(null)}
        >
          {/* Prev arrow — outside the modal so clicking it doesn't bubble to close */}
          {canGoPrev && (
            <button
              onClick={(e) => { e.stopPropagation(); navigateLightboxWrapped('prev') }}
              className="fixed left-4 top-1/2 -translate-y-1/2 z-10 p-3 bg-black/50 hover:bg-black/70 text-white rounded-full transition-colors"
              title="Previous image (←)"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}
          {canGoNext && (
            <button
              onClick={(e) => { e.stopPropagation(); navigateLightboxWrapped('next') }}
              className="fixed right-4 top-1/2 -translate-y-1/2 z-10 p-3 bg-black/50 hover:bg-black/70 text-white rounded-full transition-colors"
              title="Next image (→)"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          )}
          {/* Position indicator */}
          <div className="fixed top-4 left-1/2 -translate-x-1/2 z-10 px-3 py-1 bg-black/50 text-white text-xs rounded-full">
            {lightboxIdx >= 0 ? `${page * PAGE_SIZE + lightboxIdx + 1} / ${totalImages}` : ''}
          </div>

          <div className="max-w-4xl w-full max-h-[92vh] bg-white dark:bg-gray-800 rounded-lg overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="relative flex items-center justify-center bg-black/5 dark:bg-black/20 px-2 pt-2">
              <img
                ref={lightboxImageRef}
                src={`${API_BASE}/v1/img/${selectedImage.id}`}
                alt={selectedImage.revised_prompt || 'Generated image'}
                className="max-w-full max-h-[68vh] object-contain block"
                onLoad={() => syncMaskCanvas()}
              />
              {protectMaskEnabled && (
                <canvas
                  ref={maskCanvasRef}
                  className="absolute inset-0 h-full w-full cursor-crosshair"
                  onPointerDown={handleMaskPointerDown}
                  onPointerMove={handleMaskPointerMove}
                  onPointerUp={handleMaskPointerUp}
                  onPointerLeave={handleMaskPointerUp}
                />
              )}
            </div>
            <div className="shrink-0 overflow-y-auto p-4 border-t border-gray-200 dark:border-gray-700">
              {selectedImage.revised_prompt && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  {selectedImage.revised_prompt}
                </p>
              )}
              <div className="mb-3 rounded-md border border-gray-200 dark:border-gray-700 p-3">
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <input
                      type="checkbox"
                      checked={protectMaskEnabled}
                      onChange={(e) => {
                        setProtectMaskEnabled(e.target.checked)
                        if (!e.target.checked) clearProtectionMask()
                      }}
                    />
                    Protect painted areas
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    Brush
                    <input
                      type="range"
                      min="8"
                      max="120"
                      step="2"
                      value={maskBrushSize}
                      onChange={(e) => setMaskBrushSize(Number(e.target.value))}
                      disabled={!protectMaskEnabled}
                    />
                    <span className="w-8 text-right">{maskBrushSize}</span>
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    Denoise
                    <input
                      type="range"
                      min="0.1"
                      max="1"
                      step="0.05"
                      value={localDenoise}
                      onChange={(e) => setLocalDenoise(Number(e.target.value))}
                    />
                    <span className="w-10 text-right">{localDenoise.toFixed(2)}</span>
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    Grow
                    <input
                      type="range"
                      min="0"
                      max="64"
                      step="1"
                      value={maskGrow}
                      onChange={(e) => setMaskGrow(Number(e.target.value))}
                      disabled={!protectMaskEnabled}
                    />
                    <span className="w-8 text-right">{maskGrow}</span>
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    Feather
                    <input
                      type="range"
                      min="0"
                      max="24"
                      step="0.5"
                      value={maskFeather}
                      onChange={(e) => setMaskFeather(Number(e.target.value))}
                      disabled={!protectMaskEnabled}
                    />
                    <span className="w-10 text-right">{maskFeather.toFixed(1)}</span>
                  </label>
                  <button
                    onClick={clearProtectionMask}
                    className="px-2 py-1 text-xs rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 disabled:opacity-50"
                    disabled={!protectMaskEnabled}
                  >
                    Clear mask
                  </button>
                </div>
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  Paint the regions you want to keep unchanged. This protection mask is used only with ComfyUI-local edits and variations.
                </p>
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                  Grow expands the protected edge before compositing. Feather softens that edge to avoid cutout seams.
                </p>
              </div>
              {/* Edit prompt */}
              {editingImage?.id === selectedImage.id ? (
                <div className="mb-3 flex gap-2">
                  <input
                    type="text"
                    value={editPrompt}
                    onChange={e => setEditPrompt(e.target.value)}
                    placeholder="Describe your edit..."
                    className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    onKeyDown={e => { if (e.key === 'Enter') editImage(selectedImage, editPrompt) }}
                    autoFocus
                  />
                  <button
                    onClick={() => editImage(selectedImage, editPrompt)}
                    disabled={editing}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50"
                  >
                    {editing ? 'Editing...' : 'Apply'}
                  </button>
                  <button
                    onClick={() => { setEditingImage(null); setEditPrompt('') }}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600"
                  >
                    Cancel
                  </button>
                </div>
              ) : null}
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500 dark:text-gray-500">
                  {selectedImage.width > 0 ? `${selectedImage.width} × ${selectedImage.height}` : 'uploaded'} · {selectedImage.format.toUpperCase()}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setEditingImage(selectedImage); setEditPrompt('') }}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700"
                  >
                    Edit with AI
                  </button>
                  <button
                    onClick={() => generateVariation(selectedImage.id)}
                    disabled={isGenerating(selectedImage.id)}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50"
                    title={`Using ${availableModels.find(m => m.id === variationModel)?.name || variationModel}`}
                  >
                    {isGenerating(selectedImage.id) ? 'Generating...' : `Variation (${availableModels.find(m => m.id === variationModel)?.name.split(' ')[0] || variationModel})`}
                  </button>
                  <button
                    onClick={() => downloadImage(selectedImage)}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
                  >
                    Download
                  </button>
                  <button
                    onClick={() => { deleteImage(selectedImage.id); setSelectedImage(null) }}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

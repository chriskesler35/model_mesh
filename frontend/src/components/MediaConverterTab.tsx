'use client'

import { useEffect, useRef, useState } from 'react'
import { getAuthToken, probeAndCacheApiBase } from '@/lib/config'

// ─── Types ────────────────────────────────────────────────────────────────────

type TargetFormat = 'png' | 'jpg' | 'jpeg' | 'webp' | 'bmp' | 'tiff' | 'gif'

interface FormatOption {
  value: TargetFormat
  label: string
  description: string
}

// ─── Constants ────────────────────────────────────────────────────────────────

const MAX_FILE_MB = 200
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024

const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'mkv', 'avi', 'webm', 'm4v', 'wmv', 'flv'])
const IMAGE_EXTENSIONS = new Set(['heic', 'heif', 'jpg', 'jpeg', 'png', 'webp', 'bmp', 'tiff', 'tif', 'gif'])

const ACCEPTED_EXTENSIONS = [...VIDEO_EXTENSIONS, ...IMAGE_EXTENSIONS]
const ACCEPT_ATTR = [
  ...Array.from(VIDEO_EXTENSIONS).map(e => `.${e}`),
  ...Array.from(IMAGE_EXTENSIONS).map(e => `.${e}`),
].join(',')

const IMAGE_FORMATS: FormatOption[] = [
  { value: 'png',  label: 'PNG',  description: 'Best for transparency & screenshots' },
  { value: 'jpg',  label: 'JPG',  description: 'Smaller size, great for photos' },
  { value: 'webp', label: 'WEBP', description: 'Modern format, great quality & size' },
  { value: 'gif',  label: 'GIF',  description: 'Animated loops from video clips' },
  { value: 'tiff', label: 'TIFF', description: 'High quality, large file size' },
  { value: 'bmp',  label: 'BMP',  description: 'Uncompressed bitmap image' },
]

const VIDEO_FORMATS: FormatOption[] = [
  { value: 'gif',  label: 'GIF',  description: 'Animated loop from video' },
]

const FRIENDLY_ERRORS: Array<[RegExp, string]> = [
  [/ffmpeg/i,                   'Video conversion requires FFmpeg to be installed on the server. Ask your administrator to install it.'],
  [/pillow.heif|pillow-heif/i,  'HEIC conversion requires an extra package on the server. Ask your administrator to install pillow-heif.'],
  [/Source file not found/i,    'The file could not be found on the server after uploading. Please try again.'],
  [/unsupported.*format/i,      'This file format is not supported yet. Try a different format or file type.'],
  [/content too large/i,        `The file is too large. Maximum supported size is ${MAX_FILE_MB} MB.`],
  [/Internal Server Error/i,    'Server error during conversion. Please retry, and if it continues ask your admin to check backend logs.'],
]

function friendlyError(raw: string): string {
  for (const [pattern, msg] of FRIENDLY_ERRORS) {
    if (pattern.test(raw)) return msg
  }
  return raw
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function fileExtension(filename: string): string {
  return filename.split('.').pop()?.toLowerCase() ?? ''
}

function isVideoFile(filename: string): boolean {
  return VIDEO_EXTENSIONS.has(fileExtension(filename))
}

function suggestFormat(filename: string): TargetFormat {
  const ext = fileExtension(filename)
  if (VIDEO_EXTENSIONS.has(ext)) return 'gif'
  if (ext === 'heic' || ext === 'heif') return 'png'
  return 'png'
}

function estimatedTime(file: File, isVideo: boolean): string {
  if (isVideo) {
    const mb = file.size / (1024 * 1024)
    if (mb < 10) return 'about 10–30 seconds'
    if (mb < 50) return 'about 30–90 seconds'
    return 'a few minutes'
  }
  const mb = file.size / (1024 * 1024)
  if (mb < 5) return 'a few seconds'
  return 'about 10–20 seconds'
}

type DependencyState = {
  ready: boolean
  ffmpeg: { ready: boolean; path?: string; error?: string | null }
  pillow: { ready: boolean; error?: string | null }
  heif: { ready: boolean; error?: string | null }
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function MediaConverterTab() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [targetFormat, setTargetFormat] = useState<TargetFormat>('png')
  const [fps, setFps] = useState('12')
  const [width, setWidth] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [progressLabel, setProgressLabel] = useState('')
  const [resultFilename, setResultFilename] = useState<string | null>(null)
  const [error, setError] = useState<string>('')
  const [dependencyState, setDependencyState] = useState<DependencyState | null>(null)
  const [dependencyError, setDependencyError] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const isGif = targetFormat === 'gif'
  const isVideo = selectedFile ? isVideoFile(selectedFile.name) : false
  const availableFormats = isVideo ? VIDEO_FORMATS : IMAGE_FORMATS
  const fileSizeWarning =
    selectedFile && selectedFile.size > 50 * 1024 * 1024
      ? `Large file (${formatBytes(selectedFile.size)}) — conversion may take longer.`
      : null
  const fileSizeError =
    selectedFile && selectedFile.size > MAX_FILE_BYTES
      ? `File is too large (${formatBytes(selectedFile.size)}). Maximum is ${MAX_FILE_MB} MB.`
      : null

  useEffect(() => {
    let cancelled = false

    const loadDependencyState = async () => {
      try {
        const base = await probeAndCacheApiBase()
        const response = await fetch(`${base}/v1/tools/convert_media/status`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
        })
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const payload = (await response.json()) as DependencyState
        if (!cancelled) {
          setDependencyState(payload)
          setDependencyError('')
        }
      } catch (err: any) {
        if (!cancelled) {
          setDependencyError(err?.message || 'Unable to check media conversion dependencies')
        }
      }
    }

    loadDependencyState()
    return () => {
      cancelled = true
    }
  }, [])

  const selectFile = (file?: File | null) => {
    if (!file) return
    const ext = fileExtension(file.name)
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setError(`"${ext.toUpperCase()}" files are not supported. Accepted: images (HEIC, JPG, PNG, WEBP…) and videos (MP4, MOV, MKV…).`)
      return
    }
    setSelectedFile(file)
    setTargetFormat(suggestFormat(file.name))
    setResultFilename(null)
    setError('')
  }

  const reset = () => {
    setSelectedFile(null)
    setResultFilename(null)
    setError('')
    setProgressLabel('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  const parseDownloadFilename = (headerValue: string | null, fallback: string): string => {
    if (!headerValue) return fallback
    const utf8Match = headerValue.match(/filename\*=UTF-8''([^;]+)/i)
    if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1])
    const asciiMatch = headerValue.match(/filename="?([^";]+)"?/i)
    if (asciiMatch?.[1]) return asciiMatch[1]
    return fallback
  }

  const onConvert = async () => {
    if (!selectedFile) {
      setError('Please choose a file before converting.')
      return
    }
    if (fileSizeError) {
      setError(fileSizeError)
      return
    }

    setIsSubmitting(true)
    setError('')
    setResultFilename(null)
    setProgressLabel('Uploading file…')

    try {
      const base = await probeAndCacheApiBase()
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('target_format', targetFormat)
      if (isGif) {
        formData.append('fps', String(Math.max(1, Number(fps) || 12)))
        if (width.trim()) formData.append('width', String(Math.max(1, Number(width) || 1)))
      }

      setProgressLabel('Converting…')

      const endpoints = [
        `${base}/v1/tools/convert_media/upload`,
        '/v1/tools/convert_media/upload',
      ]

      let response: Response | null = null
      let lastError: Error | null = null
      for (const endpoint of endpoints) {
        try {
          response = await fetch(endpoint, {
            method: 'POST',
            headers: { Authorization: `Bearer ${getAuthToken()}` },
            body: formData,
          })
          // If route doesn't exist on this base URL, try the next endpoint.
          if (response.status === 404) continue
          break
        } catch (err: any) {
          lastError = err instanceof Error ? err : new Error(String(err))
        }
      }

      if (!response) {
        throw new Error(lastError?.message || 'Unable to reach media conversion service')
      }

      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        try {
          const payload = await response.json()
          detail = payload?.detail || detail
        } catch {
          // Some proxies/backends return plain text for errors.
          try {
            const text = (await response.text()).trim()
            if (text) detail = text
          } catch {
            // keep default detail
          }
        }
        throw new Error(detail)
      }

      setProgressLabel('Downloading…')
      const blob = await response.blob()
      const fallbackName = `${selectedFile.name.replace(/\.[^.]+$/, '')}.${targetFormat}`
      const filename = parseDownloadFilename(response.headers.get('content-disposition'), fallbackName)
      triggerDownload(blob, filename)
      setResultFilename(filename)
    } catch (e: any) {
      setError(friendlyError(e?.message || 'Conversion failed'))
    } finally {
      setIsSubmitting(false)
      setProgressLabel('')
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">

      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Media Converter</h2>
        <p className="text-sm text-gray-500 mt-1">
          Convert photos (including iPhone HEIC), images, and short video clips — no software needed.
          Just drop your file and click Convert.
        </p>
      </div>

      {dependencyState && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${dependencyState.ready ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-900/20' : 'border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20'}`}>
          <p className={`font-medium ${dependencyState.ready ? 'text-emerald-800 dark:text-emerald-300' : 'text-amber-800 dark:text-amber-300'}`}>
            {dependencyState.ready ? 'Media conversion backend is ready.' : 'Media conversion backend needs attention.'}
          </p>
          <p className={`mt-1 text-xs ${dependencyState.ready ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}`}>
            FFmpeg: {dependencyState.ffmpeg.ready ? `ready${dependencyState.ffmpeg.path ? ` at ${dependencyState.ffmpeg.path}` : ''}` : dependencyState.ffmpeg.error || 'not ready'}
          </p>
          <p className={`mt-1 text-xs ${dependencyState.heif.ready ? 'text-emerald-700 dark:text-emerald-400' : 'text-gray-600 dark:text-gray-400'}`}>
            HEIC support: {dependencyState.heif.ready ? 'ready' : dependencyState.heif.error || 'optional dependency not available'}
          </p>
        </div>
      )}

      {dependencyError && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          Unable to confirm backend media dependencies. {dependencyError}
        </div>
      )}

      {/* Success state */}
      {resultFilename ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-700 p-5 space-y-3">
          <div className="flex items-start gap-3">
            <div className="text-2xl">✅</div>
            <div>
              <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">Conversion complete!</p>
              <p className="text-sm text-emerald-700 dark:text-emerald-400 mt-0.5">
                <span className="font-medium">{resultFilename}</span> was downloaded to your Downloads folder.
              </p>
              <p className="text-xs text-emerald-600 dark:text-emerald-500 mt-1">
                If the download didn&apos;t start automatically, check your browser&apos;s download bar.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={reset}
            className="text-sm font-medium text-emerald-700 dark:text-emerald-400 underline hover:no-underline"
          >
            Convert another file
          </button>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-5">

          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
            onDragLeave={(e) => { e.preventDefault(); setIsDragging(false) }}
            onDrop={(e) => { e.preventDefault(); setIsDragging(false); selectFile(e.dataTransfer.files?.[0]) }}
            onClick={() => fileInputRef.current?.click()}
            className={`rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all select-none ${
              isDragging
                ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/20 scale-[1.01]'
                : selectedFile
                ? 'border-orange-300 bg-orange-50/50 dark:bg-orange-900/10'
                : 'border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900/40 hover:border-orange-300 hover:bg-orange-50/30'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_ATTR}
              onChange={(e) => selectFile(e.target.files?.[0])}
              className="hidden"
            />
            {selectedFile ? (
              <div className="space-y-1">
                <div className="text-3xl">{isVideo ? '🎬' : '🖼️'}</div>
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">{selectedFile.name}</p>
                <p className="text-xs text-gray-500">{formatBytes(selectedFile.size)} · {fileExtension(selectedFile.name).toUpperCase()}</p>
                <p className="text-xs text-orange-500 mt-1">Click or drop to change file</p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-4xl">📂</div>
                <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">Drop your file here</p>
                <p className="text-xs text-gray-400">or click to browse your computer</p>
                <p className="text-xs text-gray-400 mt-1">
                  Images: HEIC, JPG, PNG, WEBP, BMP, TIFF · Videos: MP4, MOV, MKV, AVI, WEBM
                </p>
              </div>
            )}
          </div>

          {/* File size warning */}
          {fileSizeError && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-xs text-red-700 dark:text-red-400">
              <span>⚠️</span>
              <span>{fileSizeError}</span>
            </div>
          )}
          {!fileSizeError && fileSizeWarning && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              <span>⏱</span>
              <span>{fileSizeWarning} Estimated time: {selectedFile ? estimatedTime(selectedFile, isVideo) : '—'}</span>
            </div>
          )}

          {/* Format picker */}
          {selectedFile && (
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Convert to
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {availableFormats.map((fmt) => (
                  <button
                    type="button"
                    key={fmt.value}
                    onClick={() => setTargetFormat(fmt.value)}
                    className={`text-left rounded-lg border px-3 py-2.5 transition-colors ${
                      targetFormat === fmt.value
                        ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/20'
                        : 'border-gray-200 dark:border-gray-700 hover:border-orange-200 hover:bg-orange-50/30'
                    }`}
                  >
                    <div className="text-sm font-semibold text-gray-900 dark:text-white">{fmt.label}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{fmt.description}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* GIF options */}
          {selectedFile && isGif && (
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide">GIF Options</p>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Frame rate (FPS)
                    <span className="ml-1 font-normal text-gray-400">Higher = smoother but larger file</span>
                  </label>
                  <input
                    value={fps}
                    onChange={(e) => setFps(e.target.value)}
                    type="number"
                    min={1}
                    max={30}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Width in pixels
                    <span className="ml-1 font-normal text-gray-400">Optional. Height auto-scales.</span>
                  </label>
                  <input
                    value={width}
                    onChange={(e) => setWidth(e.target.value)}
                    type="number"
                    min={1}
                    placeholder="e.g. 720"
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Convert button */}
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={onConvert}
              disabled={isSubmitting || !selectedFile || !!fileSizeError}
              className="px-5 py-2.5 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? (
                <span className="flex items-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  {progressLabel || 'Converting…'}
                </span>
              ) : (
                'Convert & Download'
              )}
            </button>
            {!isSubmitting && selectedFile && !fileSizeError && (
              <span className="text-xs text-gray-400">
                {isVideo || fileSizeWarning
                  ? `⏱ ${estimatedTime(selectedFile, isVideo)}`
                  : 'Ready in a few seconds'}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3">
          <span className="text-lg">❌</span>
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-300">Conversion failed</p>
            <p className="text-sm text-red-700 dark:text-red-400 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* How-it-works */}
      {!selectedFile && !resultFilename && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 px-5 py-4 space-y-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">How it works</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-start gap-2">
              <span>1️⃣</span>
              <span>Drop or choose your file — iPhone photos (HEIC), JPG, PNG, video clips, and more.</span>
            </div>
            <div className="flex items-start gap-2">
              <span>2️⃣</span>
              <span>Pick your target format. The best option is auto-suggested based on your file.</span>
            </div>
            <div className="flex items-start gap-2">
              <span>3️⃣</span>
              <span>Click Convert. Your file downloads automatically — nothing is stored on the server.</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

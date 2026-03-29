'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'

const API_BASE = 'http://localhost:19000'
const API_KEY = 'modelmesh_local_dev_key'

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
}

export default function GalleryPage() {
  const [images, setImages] = useState<Image[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedImage, setSelectedImage] = useState<Image | null>(null)
  const [generating, setGenerating] = useState<string | null>(null)
  const [editingImage, setEditingImage] = useState<Image | null>(null)
  const [editPrompt, setEditPrompt] = useState('')
  const [editing, setEditing] = useState(false)
  const [uploadDragging, setUploadDragging] = useState(false)

  // Moved to component scope so all handlers can call it
  const fetchImages = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/v1/images/`, {
        headers: { 'Authorization': `Bearer ${API_KEY}` }
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
      const data = await res.json()
      setImages(data.data || [])
    } catch (e: any) {
      console.error('Failed to fetch images:', e)
      setError(e.message || 'Failed to load images')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchImages()
  }, [fetchImages])

  const downloadImage = async (image: Image) => {
    try {
      const response = await fetch(`${API_BASE}${image.url}`, {
        headers: { 'Authorization': `Bearer ${API_KEY}` }
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
    setEditing(true)
    try {
      const response = await fetch(`${API_BASE}/v1/images/edit`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_image_id: image.id, prompt: prompt.trim() })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Edit failed')
      if (data.data?.[0]) {
        setImages(prev => [data.data[0], ...prev])
        setEditingImage(null)
        setEditPrompt('')
        setSelectedImage(null)
      }
    } catch (e: any) {
      alert('Edit failed: ' + e.message)
    } finally {
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
          headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ base64, filename: file.name, mime_type: file.type || 'image/png' })
        })
        if (response.ok) {
          await fetchImages() // now in scope
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
        headers: { 'Authorization': `Bearer ${API_KEY}` }
      })
      setImages(images.filter(img => img.id !== imageId))
      if (selectedImage?.id === imageId) setSelectedImage(null)
    } catch (e) {
      console.error('Failed to delete image:', e)
    }
  }

  const generateVariation = async (imageId: string) => {
    setGenerating(imageId)
    try {
      const response = await fetch(`${API_BASE}/v1/images/${imageId}/variations`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      if (!response.ok) throw new Error('Failed to generate variation')
      const data = await response.json()
      if (data.data?.[0]) setImages(prev => [data.data[0], ...prev])
    } catch (e) {
      console.error('Failed to generate variation:', e)
      alert('Failed to generate variation. Make sure the backend is running.')
    } finally {
      setGenerating(null)
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
          onClick={fetchImages}
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
            {images.length} image{images.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={fetchImages}
          className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-md"
        >
          Refresh
        </button>
      </div>

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
                    className="p-2 bg-white rounded-full text-orange-600 hover:bg-gray-100"
                    title="Generate Variation"
                    disabled={generating === image.id}
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
          <div className="max-w-4xl max-h-full bg-white dark:bg-gray-800 rounded-lg overflow-hidden" onClick={e => e.stopPropagation()}>
            <img
              src={`${API_BASE}/v1/img/${selectedImage.id}`}
              alt={selectedImage.revised_prompt || 'Generated image'}
              className="max-w-full max-h-[80vh] object-contain"
            />
            <div className="p-4 border-t border-gray-200 dark:border-gray-700">
              {selectedImage.revised_prompt && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  {selectedImage.revised_prompt}
                </p>
              )}
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
                    disabled={generating === selectedImage.id}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50"
                  >
                    {generating === selectedImage.id ? 'Generating...' : 'Variation'}
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

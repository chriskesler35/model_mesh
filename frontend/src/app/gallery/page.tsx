'use client'

import { useState, useEffect } from 'react'
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
}

export default function GalleryPage() {
  const [images, setImages] = useState<Image[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedImage, setSelectedImage] = useState<Image | null>(null)

  useEffect(() => {
    async function fetchImages() {
      try {
        const res = await fetch('http://localhost:19000/v1/images/', {
          headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
        })
        const data = await res.json()
        setImages(data.data || [])
      } catch (e) {
        console.error('Failed to fetch images:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchImages()
  }, [])

  const downloadImage = async (image: Image) => {
    try {
      const response = await fetch(`http://localhost:19000${image.url}`, {
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
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

  const deleteImage = async (imageId: string) => {
    if (!confirm('Are you sure you want to delete this image?')) return
    
    try {
      await fetch(`http://localhost:19000/v1/images/${imageId}`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
      })
      setImages(images.filter(img => img.id !== imageId))
      if (selectedImage?.id === imageId) {
        setSelectedImage(null)
      }
    } catch (e) {
      console.error('Failed to delete image:', e)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Image Gallery</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          View and manage generated images
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
            className="mt-4 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700"
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
                  src={`http://localhost:19000${image.url}`}
                  alt={image.revised_prompt || 'Generated image'}
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-50 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100">
                <div className="flex gap-2">
                  <button
                    onClick={(e) => { e.stopPropagation(); downloadImage(image); }}
                    className="p-2 bg-white rounded-full text-gray-900 hover:bg-gray-100"
                    title="Download"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteImage(image.id); }}
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
              src={`http://localhost:19000${selectedImage.url}`}
              alt={selectedImage.revised_prompt || 'Generated image'}
              className="max-w-full max-h-[80vh] object-contain"
            />
            <div className="p-4 border-t border-gray-200 dark:border-gray-700">
              {selectedImage.revised_prompt && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  {selectedImage.revised_prompt}
                </p>
              )}
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500 dark:text-gray-500">
                  {selectedImage.width} × {selectedImage.height} • {selectedImage.format.toUpperCase()}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => downloadImage(selectedImage)}
                    className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700"
                  >
                    Download
                  </button>
                  <button
                    onClick={() => { deleteImage(selectedImage.id); setSelectedImage(null); }}
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
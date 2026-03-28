'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  image_url?: string
  image_id?: string
}

interface Persona {
  id: string
  name: string
  system_prompt?: string
  primary_model_id?: string
  fallback_model_id?: string
  memory_enabled?: boolean
  max_memory_messages?: number
}

interface Model {
  id: string
  model_id: string
  display_name?: string
  provider_name?: string
  capabilities?: Record<string, boolean>
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function ChatPage() {
  const params = useParams()
  const conversationId = params?.id as string
  
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [persona, setPersona] = useState<Persona | null>(null)
  const [models, setModels] = useState<Model[]>([])
  const [showImageGen, setShowImageGen] = useState(false)
  const [imagePrompt, setImagePrompt] = useState('')
  const [generatingImage, setGeneratingImage] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    async function fetchData() {
      try {
        const [personasRes, modelsRes] = await Promise.all([
          fetch('http://localhost:19000/v1/personas', {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json()),
          fetch('http://localhost:19000/v1/models', {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json())
        ])
        
        setModels(modelsRes.data || [])
        
        // Get default persona
        const defaultPersona = personasRes.data?.find((p: Persona) => p.name === 'quick-helper') || personasRes.data?.[0]
        setPersona(defaultPersona)
      } catch (e) {
        console.error('Failed to fetch:', e)
      }
    }
    fetchData()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || loading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      created_at: new Date().toISOString()
    }
    
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await api.chat(
        messages.concat(userMessage).map(m => ({ role: m.role, content: m.content })),
        persona?.name || 'quick-helper'
      )
      
      setMessages(prev => [...prev, { 
        id: (Date.now() + 1).toString(),
        role: 'assistant', 
        content: response,
        created_at: new Date().toISOString()
      }])
    } catch (err) {
      console.error('Chat error:', err)
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Failed to get response'}`,
        created_at: new Date().toISOString()
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleGenerateImage = async () => {
    if (!imagePrompt.trim() || generatingImage) return
    
    setGeneratingImage(true)
    
    try {
      // Use ComfyUI by default (free), fallback to Gemini
      const model = models.find(m => m.model_id === 'comfyui-local') ? 'comfyui-local' : 'gemini-imagen'
      
      const result = await api.generateImage(imagePrompt, model, {
        size: '1024x1024',
        format: 'png'
      })
      
      if (result.data && result.data.length > 0) {
        const img = result.data[0]
        
        // Add image message
        setMessages(prev => [...prev, {
          id: img.id,
          role: 'assistant',
          content: img.revised_prompt || imagePrompt,
          created_at: new Date().toISOString(),
          image_url: `http://localhost:19000${img.url}`,
          image_id: img.id
        }])
        
        setImagePrompt('')
        setShowImageGen(false)
      }
    } catch (err) {
      console.error('Image generation error:', err)
      alert(`Failed to generate image: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setGeneratingImage(false)
    }
  }

  const downloadImage = async (imageId: string, prompt: string) => {
    try {
      const blob = await api.getImage(imageId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `devforgeai-${imageId}.png`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Download error:', err)
    }
  }

  const hasImageCapabilities = models.some(m => m.capabilities?.image_generation)

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
              Chat with {persona?.name || 'AI'}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {persona?.description || 'Chat with an AI assistant'}
            </p>
          </div>
          {hasImageCapabilities && (
            <button
              onClick={() => setShowImageGen(!showImageGen)}
              className="inline-flex items-center px-3 py-1.5 border border-transparent text-sm font-medium rounded-md text-indigo-600 bg-indigo-100 hover:bg-indigo-200 dark:bg-indigo-900 dark:text-indigo-200 dark:hover:bg-indigo-800"
            >
              <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              Generate Image
            </button>
          )}
        </div>
      </div>

      {/* Image Generation Panel */}
      {showImageGen && (
        <div className="bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600 p-4">
          <div className="max-w-2xl mx-auto">
            <div className="flex gap-2">
              <input
                type="text"
                value={imagePrompt}
                onChange={(e) => setImagePrompt(e.target.value)}
                placeholder="Describe the image you want to create..."
                className="flex-1 rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm"
              />
              <button
                onClick={handleGenerateImage}
                disabled={generatingImage || !imagePrompt.trim()}
                className="px-4 py-2 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {generatingImage ? 'Generating...' : 'Generate'}
              </button>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Powered by ComfyUI (local) or Gemini Imagen (cloud)
            </p>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-500 dark:text-gray-400">
              <svg className="mx-auto h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="text-lg font-medium">Start a conversation</p>
              <p className="text-sm">Type a message below or generate an image</p>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 ${
                message.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white border border-gray-200 dark:border-gray-700'
              }`}
            >
              {message.image_url ? (
                <div className="space-y-2">
                  <img
                    src={message.image_url}
                    alt={message.content}
                    className="rounded-lg max-w-full"
                    style={{ maxHeight: '400px' }}
                  />
                  <p className="text-sm opacity-75">{message.content}</p>
                  <button
                    onClick={() => downloadImage(message.image_id!, message.content)}
                    className="inline-flex items-center px-2 py-1 text-xs font-medium rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download
                  </button>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{message.content}</p>
              )}
              <p className={`text-xs mt-1 ${message.role === 'user' ? 'text-indigo-200' : 'text-gray-500 dark:text-gray-400'}`}>
                {formatDate(message.created_at)}
              </p>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-gray-800 rounded-lg px-4 py-2 border border-gray-200 dark:border-gray-700">
              <p className="text-gray-500 dark:text-gray-400">Thinking...</p>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 p-4">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
              className="flex-1 rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
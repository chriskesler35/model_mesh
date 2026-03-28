'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'

interface Message {
  id: string
  role: string
  content: string
  created_at: string
}

interface Conversation {
  id: string
  persona_id?: string
  external_id?: string
  created_at: string
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

export default function ConversationDetailPage() {
  const params = useParams()
  const conversationId = params?.id as string
  
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      try {
        const [convRes, msgRes] = await Promise.all([
          fetch(`http://localhost:19000/v1/conversations/${conversationId}`, {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json()).catch(() => null),
          fetch(`http://localhost:19000/v1/conversations/${conversationId}/messages`, {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json()).catch(() => ({ data: [] }))
        ])
        
        setConversation(convRes)
        setMessages(msgRes.data || [])
      } catch (e) {
        console.error('Failed to fetch:', e)
      } finally {
        setLoading(false)
      }
    }
    
    if (conversationId) {
      fetchData()
    }
  }, [conversationId])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (!conversation) {
    return (
      <div className="text-center py-12">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Conversation not found</h3>
        <Link href="/conversations" className="mt-4 text-indigo-600 hover:text-indigo-500">
          Back to Conversations
        </Link>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8">
        <Link href="/conversations" className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400">
          ← Back to Conversations
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
          Conversation {conversation.id.substring(0, 8)}
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Created: {formatDate(conversation.created_at)}
        </p>
        {conversation.persona_id && (
          <p className="text-sm text-purple-600 dark:text-purple-400">
            Persona: {conversation.persona_id}
          </p>
        )}
      </div>

      {messages.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 shadow sm:rounded-lg p-6">
          <p className="text-gray-500 dark:text-gray-400 text-center">
            No messages in this conversation yet.
          </p>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 shadow sm:rounded-lg overflow-hidden">
          <ul className="divide-y divide-gray-200 dark:divide-gray-700">
            {messages.map((message) => (
              <li key={message.id} className={`p-4 ${message.role === 'user' ? 'bg-gray-50 dark:bg-gray-700' : 'bg-white dark:bg-gray-800'}`}>
                <div className="flex items-start gap-3">
                  <div className={`px-2 py-1 text-xs font-medium rounded ${
                    message.role === 'user' 
                      ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                      : 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                  }`}>
                    {message.role}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-gray-900 dark:text-white whitespace-pre-wrap">
                      {message.content}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {formatDate(message.created_at)}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
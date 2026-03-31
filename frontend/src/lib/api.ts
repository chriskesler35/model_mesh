import { API_BASE, API_KEY, AUTH_HEADERS } from '@/lib/config'

// API_URL uses the shared dynamic config (auto-detects hostname for remote access)
const API_URL = API_BASE


class ApiClient {
  private baseUrl: string
  private apiKey: string

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl
    this.apiKey = apiKey
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
        ...options?.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`)
    }

    return response.json()
  }

  // Personas
  async getPersonas(limit = 20, offset = 0) {
    return this.request<import('./types').PaginatedResponse<import('./types').Persona>>(
      `/v1/personas?limit=${limit}&offset=${offset}`
    )
  }

  async getPersona(id: string) {
    return this.request<import('./types').Persona>(`/v1/personas/${id}`)
  }

  async createPersona(data: Partial<import('./types').Persona>) {
    return this.request<import('./types').Persona>('/v1/personas', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updatePersona(id: string, data: Partial<import('./types').Persona>) {
    return this.request<import('./types').Persona>(`/v1/personas/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deletePersona(id: string) {
    return this.request(`/v1/personas/${id}`, { method: 'DELETE' })
  }

  // Models
  async getModels(limit = 50, offset = 0) {
    return this.request<import('./types').PaginatedResponse<import('./types').Model>>(
      `/v1/models?limit=${limit}&offset=${offset}`
    )
  }

  // Conversations
  async getConversations(limit = 20, offset = 0) {
    return this.request<import('./types').PaginatedResponse<import('./types').Conversation>>(
      `/v1/conversations?limit=${limit}&offset=${offset}`
    )
  }

  async getMessages(conversationId: string, limit = 50, offset = 0) {
    return this.request<import('./types').PaginatedResponse<import('./types').Message>>(
      `/v1/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`
    )
  }

  // Stats
  async getCosts(days = 7): Promise<import('./types').CostSummary> {
    return this.request(`/v1/stats/costs?days=${days}`)
  }

  async getUsage(days = 7): Promise<import('./types').UsageSummary> {
    return this.request(`/v1/stats/usage?days=${days}`)
  }

  // Chat
  async chat(messages: Array<{ role: string; content: string }>, persona: string): Promise<string> {
    const response = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        model: persona,
        messages,
        stream: false,
      }),
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Chat error: ${error}`)
    }

    const data = await response.json()
    return data.choices[0]?.message?.content || ''
  }

  newConversation(): void {
    // Reset conversation state if tracking
  }

  // Image Generation
  async generateImage(prompt: string, model: string = 'comfyui-local', options?: {
    size?: string
    format?: string
    negative_prompt?: string
  }): Promise<{ data: Array<{ id: string; url: string; revised_prompt?: string }> }> {
    const response = await fetch(`${this.baseUrl}/v1/images/generations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        model,
        prompt,
        size: options?.size || '1024x1024',
        format: options?.format || 'png',
        negative_prompt: options?.negative_prompt,
      }),
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Image generation error: ${error}`)
    }

    return response.json()
  }

  async getImage(imageId: string): Promise<Blob> {
    const response = await fetch(`${this.baseUrl}/v1/images/${imageId}`, {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
      },
    })

    if (!response.ok) {
      throw new Error(`Failed to get image: ${response.status}`)
    }

    return response.blob()
  }

  async listImages(limit = 50, offset = 0): Promise<{ data: Array<{
    id: string
    url: string
    revised_prompt?: string
    width: number
    height: number
    format: string
  }>; total: number }> {
    return this.request(`/v1/images/?limit=${limit}&offset=${offset}`)
  }

  async deleteImage(imageId: string): Promise<void> {
    await this.request(`/v1/images/${imageId}`, { method: 'DELETE' })
  }

  // Agents
  async getAgents(agentType?: string): Promise<{ data: Array<import('./types').Agent>; total: number }> {
    const params = agentType ? `?agent_type=${agentType}` : ''
    return this.request(`/v1/agents${params}`)
  }

  async getAgent(id: string): Promise<import('./types').Agent> {
    return this.request(`/v1/agents/${id}`)
  }

  async createAgent(data: Partial<import('./types').Agent>): Promise<import('./types').Agent> {
    return this.request('/v1/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateAgent(id: string, data: Partial<import('./types').Agent>): Promise<import('./types').Agent> {
    return this.request(`/v1/agents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  async deleteAgent(id: string): Promise<void> {
    await this.request(`/v1/agents/${id}`, { method: 'DELETE' })
  }
}

export const api = new ApiClient(API_URL, API_KEY)
import { getConfig, Config } from '../utils/config';

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface ChatRequest {
  model: string;
  messages: Message[];
  stream?: boolean;
  conversation_id?: string;
  temperature?: number;
  max_tokens?: number;
}

interface ChatResponse {
  id: string;
  model: string;
  choices: Array<{
    message: Message;
    finish_reason: string;
  }>;
  modelmesh?: {
    persona_used: string;
    actual_model: string;
    estimated_cost: number;
    provider: string;
  };
}

export class ModelMeshClient {
  private config: Config;
  private conversationId: string | null = null;

  constructor() {
    this.config = getConfig();
  }

  async chat(messages: Message[], persona?: string): Promise<string> {
    const request: ChatRequest = {
      model: persona || this.config.defaultPersona,
      messages,
      stream: false,
      conversation_id: this.conversationId || undefined,
    };

    const response = await fetch(`${this.config.apiUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.config.apiKey}`,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ModelMesh API error: ${error}`);
    }

    const data: ChatResponse = await response.json();
    
    // Store conversation ID for memory continuity
    if (data.id) {
      this.conversationId = data.id;
    }

    return data.choices[0]?.message?.content || '';
  }

  async *streamChat(messages: Message[], persona?: string): AsyncGenerator<string> {
    const request: ChatRequest = {
      model: persona || this.config.defaultPersona,
      messages,
      stream: true,
      conversation_id: this.conversationId || undefined,
    };

    const response = await fetch(`${this.config.apiUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.config.apiKey}`,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ModelMesh API error: ${error}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            return;
          }
          try {
            const parsed = JSON.parse(data);
            const content = parsed.choices?.[0]?.delta?.content;
            if (content) {
              yield content;
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }
    }
  }

  newConversation(): void {
    this.conversationId = null;
  }

  async getPersonas(): Promise<Array<{ id: string; name: string }>> {
    const response = await fetch(`${this.config.apiUrl}/personas`, {
      headers: {
        'Authorization': `Bearer ${this.config.apiKey}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to fetch personas');
    }

    const data = await response.json();
    return data.data.map((p: any) => ({ id: p.id, name: p.name }));
  }
}
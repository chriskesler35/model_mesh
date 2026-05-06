export interface Persona {
  id: string;
  name: string;
  description?: string;
  system_prompt?: string;
  primary_model_id?: string;
  fallback_model_id?: string;
  routing_rules: RoutingRules;
  memory_enabled: boolean;
  max_memory_messages: number;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoutingRules {
  max_cost?: number;
  prefer_local?: boolean;
  timeout_seconds?: number;
  max_tokens?: number;
}

export interface Model {
  id: string;
  provider_id: string;
  model_id: string;
  display_name?: string;
  cost_per_1m_input: number;
  cost_per_1m_output: number;
  context_window?: number;
  capabilities: Record<string, boolean>;
  is_active: boolean;
  provider_name?: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  persona_id?: string;
  external_id?: string;
  extra_data: Record<string, unknown>;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  model_used?: string;
  tokens_in?: number;
  tokens_out?: number;
  latency_ms?: number;
  estimated_cost?: number;
  created_at: string;
}

export interface CostSummary {
  total_cost: number;
  by_model: Record<string, number>;
  by_provider: Record<string, number>;
  period_start: string;
  period_end: string;
}

export interface UsageSummary {
  total_input_tokens: number;
  total_output_tokens: number;
  total_requests: number;
  success_rate: number;
  by_model: Record<string, { input_tokens: number; output_tokens: number; requests: number }>;
  by_provider: Record<string, { input_tokens: number; output_tokens: number; requests: number }>;
  period_start: string;
  period_end: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface Agent {
  id: string;
  name: string;
  agent_type: string;
  description?: string;
  system_prompt: string;
  model_id?: string;
  persona_id?: string;
  persona_name?: string;
  resolved_model_name?: string;
  resolved_via?: string;
  method_phase?: string;
  tools: string[];
  memory_enabled: boolean;
  max_iterations: number;
  timeout_seconds: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MethodPhase {
  name: string;
  role: string;
  methods: string[];
  default_model?: string;
}

export const AGENT_TYPES = [
  'coder',
  'researcher',
  'designer',
  'reviewer',
  'planner',
  'executor',
  'writer'
] as const

export const AGENT_TOOLS = [
  'read_file',
  'write_file',
  'run_tests',
  'git_commit',
  'shell_execute',
  'http_request',
  'web_search',
  'generate_image',
  'image_variation'
] as const

export interface ConvertMediaRequest {
  source_path: string;
  target_format: string;
  output_path?: string;
  fps?: number;
  width?: number;
}

export interface ConvertMediaResponse {
  success: boolean;
  output: string;
  source_path?: string;
  output_path?: string;
}
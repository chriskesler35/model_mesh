-- Add OpenRouter models
INSERT INTO models (id, provider_id, model_id, display_name, cost_per_1m_input, cost_per_1m_output, context_window, capabilities, is_active, created_at) 
VALUES 
  (gen_random_uuid(), '02b07b9f-49da-4d10-8d96-0b9d268985b8', 'anthropic/claude-sonnet-4', 'Claude Sonnet 4 (OpenRouter)', 3.0, 15.0, 200000, '{"streaming": true, "vision": true}', true, NOW()),
  (gen_random_uuid(), '02b07b9f-49da-4d10-8d96-0b9d268985b8', 'openai/gpt-4o', 'GPT-4o (OpenRouter)', 2.5, 10.0, 128000, '{"streaming": true, "vision": true}', true, NOW()),
  (gen_random_uuid(), '02b07b9f-49da-4d10-8d96-0b9d268985b8', 'google/gemini-2.5-pro-preview', 'Gemini 2.5 Pro (OpenRouter)', 1.25, 5.0, 1000000, '{"streaming": true, "vision": true}', true, NOW());

-- Update python-architect persona to use OpenRouter models
UPDATE personas 
SET primary_model_id = (SELECT id FROM models WHERE model_id = 'anthropic/claude-sonnet-4' LIMIT 1),
    fallback_model_id = (SELECT id FROM models WHERE model_id = 'google/gemini-2.5-pro-preview' LIMIT 1)
WHERE name = 'python-architect';

-- Create a new quick-helper persona using OpenRouter
INSERT INTO personas (id, name, description, system_prompt, primary_model_id, fallback_model_id, routing_rules, memory_enabled, max_memory_messages, is_default, created_at, updated_at)
SELECT 
  gen_random_uuid(),
  'quick-helper-or',
  'Quick helper using OpenRouter',
  'You are a helpful assistant. Be concise and direct.',
  (SELECT id FROM models WHERE model_id = 'openai/gpt-4o' LIMIT 1),
  (SELECT id FROM models WHERE model_id = 'anthropic/claude-sonnet-4' LIMIT 1),
  '{"max_cost": 0.01}',
  true,
  5,
  false,
  NOW(),
  NOW()
WHERE NOT EXISTS (SELECT 1 FROM personas WHERE name = 'quick-helper-or');
import { Page } from '@playwright/test';
import { apiRequest } from './helpers';

export interface RegressionRoute {
  name: string
  path: string
  expectedTextAny?: string[]
  ignoredFailedRequests?: Array<string | RegExp>
}

export interface SkippedRoute {
  name: string
  reason: string
}

export const STATIC_ROUTE_INVENTORY: RegressionRoute[] = [
  { name: 'Dashboard', path: '/', expectedTextAny: ['Dashboard', 'DevForgeAI'] },
  { name: 'Chat', path: '/chat', expectedTextAny: ['Chat', 'New Chat', 'DevForgeAI'] },
  { name: 'Gallery', path: '/gallery', expectedTextAny: ['Gallery', 'image', 'Images'] },
  { name: 'Agents', path: '/agents', expectedTextAny: ['Agents', 'agent', 'Coder'] },
  { name: 'Agent Sessions', path: '/agents/sessions', expectedTextAny: ['Sessions', 'Workbench', 'Agent'] },
  { name: 'Workbench', path: '/workbench', expectedTextAny: ['Workbench', 'Session', 'Pipeline'] },
  { name: 'Workflow Builder', path: '/workbench/builder', expectedTextAny: ['Workflow Builder', 'Builder', 'Workbench'] },
  { name: 'Projects', path: '/projects', expectedTextAny: ['Projects', 'Project'] },
  { name: 'Methods', path: '/methods', expectedTextAny: ['Methods', 'Method', 'stack'] },
  { name: 'Marketplace', path: '/marketplace', expectedTextAny: ['Marketplace', 'Skills', 'Install'] },
  { name: 'Installed Skills', path: '/skills/installed', expectedTextAny: ['Installed Skills', 'Marketplace', 'Skills'] },
  { name: 'Collaborate', path: '/collaborate', expectedTextAny: ['Collaborate', 'Users', 'Workspaces'] },
  { name: 'Personas', path: '/personas', expectedTextAny: ['Personas', 'Persona'] },
  {
    name: 'New Persona',
    path: '/personas/new',
    expectedTextAny: ['Persona', 'Create', 'New'],
    ignoredFailedRequests: ['/v1/models/sync'],
  },
  { name: 'Models', path: '/models', expectedTextAny: ['Models', 'Model'] },
  { name: 'Conversations', path: '/conversations', expectedTextAny: ['Conversations', 'Conversation'] },
  { name: 'Stats', path: '/stats', expectedTextAny: ['Stats', 'Usage', 'Cost'] },
  { name: 'Settings', path: '/settings', expectedTextAny: ['Settings', 'Preferences', 'Identity'] },
  { name: 'Help', path: '/help', expectedTextAny: ['Help', 'Docs', 'Guide'] },
  { name: 'Legacy Login', path: '/login', expectedTextAny: ['Login', 'Sign in', 'Welcome'] },
  { name: 'Auth Login', path: '/auth/login', expectedTextAny: ['Login', 'Sign in', 'Welcome'] },
  { name: 'Register', path: '/auth/register', expectedTextAny: ['Register', 'Sign up', 'Create account'] },
  { name: 'GitHub Callback', path: '/auth/github/callback?code=regression&state=regression', expectedTextAny: ['GitHub', 'Login', 'Sign in', 'error'] },
  { name: 'OpenRouter Callback', path: '/auth/openrouter/callback?code=regression&state=regression', expectedTextAny: ['OpenRouter', 'Settings', 'error', 'connected'] },
  { name: 'Shared Conversation Fallback', path: '/share/regression-invalid-token', expectedTextAny: ['Share', 'invalid', 'expired', 'not found'] },
];

export const LINK_SOURCE_PAGES = [
  '/',
  '/help',
  '/settings',
  '/workbench',
  '/personas',
  '/projects',
  '/agents',
  '/conversations',
  '/marketplace',
  '/gallery',
];

async function resolveFirstCollectionRoute(
  page: Page,
  name: string,
  apiPath: string,
  buildPath: (item: Record<string, any>) => string,
  expectedTextAny?: string[],
): Promise<RegressionRoute | SkippedRoute> {
  const response = await apiRequest(page, 'GET', apiPath);
  const items = Array.isArray(response.data?.data) ? response.data.data : [];
  if (!items.length) {
    return { name, reason: `No data returned from ${apiPath}` };
  }

  return {
    name,
    path: buildPath(items[0]),
    expectedTextAny,
  };
}

export async function getRegressionRouteInventory(page: Page): Promise<{
  requiredRoutes: RegressionRoute[]
  skippedRoutes: SkippedRoute[]
}> {
  const resolvedRoutes: RegressionRoute[] = [...STATIC_ROUTE_INVENTORY];
  const skippedRoutes: SkippedRoute[] = [];

  const dynamicCandidates = await Promise.all([
    resolveFirstCollectionRoute(page, 'Persona Detail', '/v1/personas?limit=1&offset=0', item => `/personas/${item.id}`, ['Persona', 'Memory', 'Default']),
    resolveFirstCollectionRoute(page, 'Project Detail', '/v1/projects?limit=1&offset=0', item => `/projects/${item.id}`, ['Project', 'Files', 'Sandbox']),
    resolveFirstCollectionRoute(page, 'Agent Detail', '/v1/agents', item => `/agents/${item.id}`, ['Agent', 'Model', 'Prompt']),
    resolveFirstCollectionRoute(page, 'Conversation Detail', '/v1/conversations?limit=1&offset=0', item => `/conversations/${item.id}`, ['Conversation', 'Messages', 'Chat']),
    resolveFirstCollectionRoute(page, 'Workbench Session Detail', '/v1/workbench/sessions', item => `/workbench/${item.id}`, ['Session', 'Agent', 'Workbench']),
    resolveFirstCollectionRoute(page, 'Workbench Pipeline Detail', '/v1/workbench/pipelines', item => `/workbench/pipelines/${item.id}`, ['Pipeline', 'Phase', 'Workbench']),
  ]);

  for (const candidate of dynamicCandidates) {
    if ('path' in candidate) {
      resolvedRoutes.push(candidate);
    } else {
      skippedRoutes.push(candidate);
    }
  }

  return { requiredRoutes: resolvedRoutes, skippedRoutes };
}
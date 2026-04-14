'use client'

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { getApiBase, getAuthToken } from '@/lib/config'
import { useToast } from '@/app/ToastProvider'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface WorkflowNode {
  id: string
  type: string
  label: string
  x: number
  y: number
  config: {
    model?: string
    systemPrompt?: string
    tools?: string[]
    maxIterations?: number
    timeout?: number
    artifactType?: string
    condition?: string
  }
}

interface CustomAgent {
  id: string
  name: string
  agent_type: string
  description?: string | null
  resolved_model_name?: string | null
  is_active: boolean
}

interface WorkflowEdge {
  id: string
  source: string
  target: string
}

// ---------------------------------------------------------------------------
// Agent palette definitions
// ---------------------------------------------------------------------------
const AGENT_TYPES = [
  { type: 'coder',      label: 'Coder',      icon: '\u{1F4BB}', description: 'Write, debug, review code' },
  { type: 'researcher', label: 'Researcher',  icon: '\u{1F50D}', description: 'Search, summarize, analyze' },
  { type: 'designer',   label: 'Designer',    icon: '\u{1F3A8}', description: 'Create images, logos, banners' },
  { type: 'reviewer',   label: 'Reviewer',    icon: '\u2705',    description: 'Quality check, suggest improvements' },
  { type: 'planner',    label: 'Planner',     icon: '\u{1F4CB}', description: 'Break down complex tasks' },
  { type: 'executor',   label: 'Executor',    icon: '\u26A1',    description: 'Run tools, API calls' },
  { type: 'writer',     label: 'Writer',      icon: '\u270D\uFE0F', description: 'Create content, documentation' },
] as const

// ---------------------------------------------------------------------------
// Colour mapping for type badges
// ---------------------------------------------------------------------------
const TYPE_COLORS: Record<string, string> = {
  coder:      'bg-blue-600',
  researcher: 'bg-purple-600',
  designer:   'bg-pink-600',
  reviewer:   'bg-green-600',
  planner:    'bg-amber-600',
  executor:   'bg-red-600',
  writer:     'bg-teal-600',
}

// ---------------------------------------------------------------------------
// Node geometry constants (must match Tailwind classes on node cards)
// ---------------------------------------------------------------------------
const NODE_W = 176 // w-44
const NODE_H = 68

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------
export default function WorkflowBuilderPage() {
  const router = useRouter()
  const [nodes, setNodes] = useState<WorkflowNode[]>([])
  const [edges, setEdges] = useState<WorkflowEdge[]>([])
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null)
  const [draggingType, setDraggingType] = useState<string | null>(null)
  const [edgeSource, setEdgeSource] = useState<string | null>(null)
  const canvasRef = useRef<HTMLDivElement>(null)

  // Save / Load state
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string | null>(null)
  const [workflowName, setWorkflowName] = useState('')
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [showLoadModal, setShowLoadModal] = useState(false)
  const [savedWorkflows, setSavedWorkflows] = useState<any[]>([])
  const [loadingWorkflows, setLoadingWorkflows] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Palette state
  const [paletteSearch, setPaletteSearch] = useState('')
  const [customAgents, setCustomAgents] = useState<CustomAgent[]>([])
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null)
  const [handleDragSource, setHandleDragSource] = useState<string | null>(null)
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null)
  const [availableModels, setAvailableModels] = useState<string[]>([])

  // Run workflow state
  const [showRunModal, setShowRunModal] = useState(false)
  const [runTask, setRunTask] = useState('')
  const [runError, setRunError] = useState<string | null>(null)
  const [runLoading, setRunLoading] = useState(false)
  const { addToast } = useToast()

  const apiHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${getAuthToken()}`,
  }), [])

  // ------ Fetch custom agents from API -----------------------------------
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${getApiBase()}/v1/agents`, { headers: apiHeaders() })
        if (!res.ok) return
        const body = await res.json()
        const agents: CustomAgent[] = (body.data ?? [])
        if (!cancelled) {
          // Exclude default agent types — they already appear in AGENT_TYPES
          const defaultTypes = new Set<string>(AGENT_TYPES.map((a) => a.type))
          setCustomAgents(agents.filter((a) => !defaultTypes.has(a.agent_type) || !a.id.startsWith('default-')))
        }
      } catch { /* silent — palette still shows defaults */ }
    })()
    return () => { cancelled = true }
  }, [apiHeaders])

  // ------ Fetch available models from API --------------------------------
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(
          `${getApiBase()}/v1/models?active_only=true&usable_only=true&validated_only=true&chat_only=true`,
          { headers: apiHeaders() },
        )
        if (!res.ok) return
        const body = await res.json()
        const models: string[] = (body.data ?? body.models ?? [])
          .map((m: any) => typeof m === 'string' ? m : m.model_id || m.name)
          .filter(Boolean)
        if (!cancelled) setAvailableModels(models)
      } catch { /* silent — model dropdown shows only Default */ }
    })()
    return () => { cancelled = true }
  }, [apiHeaders])

  // ------ Palette filtering ----------------------------------------------
  const filteredDefaults = useMemo(() => {
    const q = paletteSearch.toLowerCase()
    if (!q) return [...AGENT_TYPES]
    return AGENT_TYPES.filter(
      (a) =>
        a.label.toLowerCase().includes(q) ||
        a.type.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q),
    )
  }, [paletteSearch])

  const filteredCustom = useMemo(() => {
    const q = paletteSearch.toLowerCase()
    if (!q) return customAgents
    return customAgents.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.agent_type.toLowerCase().includes(q) ||
        (a.description ?? '').toLowerCase().includes(q),
    )
  }, [paletteSearch, customAgents])

  // ------ DAG cycle detection (DFS) --------------------------------------
  const wouldCreateCycle = useCallback(
    (source: string, target: string): boolean => {
      // Adding source→target: walk forward from target; if we reach source it's a cycle
      const visited = new Set<string>()
      const stack = [target]
      while (stack.length > 0) {
        const current = stack.pop()!
        if (current === source) return true
        if (visited.has(current)) continue
        visited.add(current)
        for (const edge of edges) {
          if (edge.source === current) stack.push(edge.target)
        }
      }
      return false
    },
    [edges],
  )

  // ------ Connect two nodes (with cycle + duplicate guard) ---------------
  const connectNodes = useCallback(
    (source: string, target: string) => {
      if (source === target) return
      // Duplicate check
      const exists = edges.some((e) => e.source === source && e.target === target)
      if (exists) return
      // Cycle check
      if (wouldCreateCycle(source, target)) {
        addToast({
          type: 'error',
          title: 'Circular dependency',
          message: 'Adding this connection would create a cycle. Workflows must be directed acyclic graphs (DAGs).',
          autoClose: 5000,
        })
        return
      }
      const newEdge: WorkflowEdge = {
        id: `edge-${source}-${target}`,
        source,
        target,
      }
      setEdges((prev) => [...prev, newEdge])
    },
    [edges, wouldCreateCycle, addToast],
  )

  const handleSave = useCallback(async () => {
    if (!workflowName.trim()) { setSaveError('Name is required'); return }
    setSaveError(null)
    const graphData = { nodes, edges }
    try {
      if (currentWorkflowId) {
        await fetch(`${getApiBase()}/v1/workflows/custom/${currentWorkflowId}`, {
          method: 'PUT',
          headers: apiHeaders(),
          body: JSON.stringify({ name: workflowName, graph_data: graphData }),
        })
      } else {
        const res = await fetch(`${getApiBase()}/v1/workflows/custom`, {
          method: 'POST',
          headers: apiHeaders(),
          body: JSON.stringify({ name: workflowName, graph_data: graphData }),
        })
        if (!res.ok) throw new Error(await res.text())
        const created = await res.json()
        setCurrentWorkflowId(created.id)
      }
      setShowSaveModal(false)
    } catch (err: any) {
      setSaveError(err.message || 'Save failed')
    }
  }, [workflowName, nodes, edges, currentWorkflowId, apiHeaders])

  const openLoadModal = useCallback(async () => {
    setShowLoadModal(true)
    setLoadingWorkflows(true)
    try {
      const res = await fetch(`${getApiBase()}/v1/workflows/custom`, { headers: apiHeaders() })
      if (!res.ok) throw new Error('Failed to fetch workflows')
      setSavedWorkflows(await res.json())
    } catch { setSavedWorkflows([]) }
    setLoadingWorkflows(false)
  }, [apiHeaders])

  const handleLoad = useCallback((wf: any) => {
    setNodes(wf.graph_data?.nodes || [])
    setEdges(wf.graph_data?.edges || [])
    setCurrentWorkflowId(wf.id)
    setWorkflowName(wf.name)
    setSelectedNode(null)
    setEdgeSource(null)
    setShowLoadModal(false)
  }, [])

  const handleDeleteWorkflow = useCallback(async (id: string) => {
    await fetch(`${getApiBase()}/v1/workflows/custom/${id}`, {
      method: 'DELETE',
      headers: apiHeaders(),
    })
    setSavedWorkflows((prev) => prev.filter((w) => w.id !== id))
    if (currentWorkflowId === id) { setCurrentWorkflowId(null); setWorkflowName('') }
  }, [apiHeaders, currentWorkflowId])

  // ------ Graph validation -----------------------------------------------
  const validateGraph = useCallback((): string | null => {
    if (nodes.length === 0) return 'Add at least one agent node to the canvas.'

    // Check for disconnected/isolated nodes (nodes with no edges) when there
    // are multiple nodes — a single node is fine to run standalone.
    if (nodes.length > 1) {
      const connectedIds = new Set<string>()
      for (const e of edges) { connectedIds.add(e.source); connectedIds.add(e.target) }
      const isolated = nodes.filter((n) => !connectedIds.has(n.id))
      if (isolated.length > 0) {
        return `Disconnected node${isolated.length > 1 ? 's' : ''}: ${isolated.map((n) => n.label).join(', ')}. Connect all nodes or remove unused ones.`
      }
    }

    // Valid DAG check (topological sort via Kahn's algorithm)
    const inDegree = new Map<string, number>()
    nodes.forEach((n) => inDegree.set(n.id, 0))
    for (const e of edges) {
      inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1)
    }
    const queue = Array.from(inDegree.entries()).filter(([, d]) => d === 0).map(([id]) => id)
    let visited = 0
    while (queue.length > 0) {
      const curr = queue.shift()!
      visited++
      for (const e of edges) {
        if (e.source === curr) {
          const newDeg = (inDegree.get(e.target) || 1) - 1
          inDegree.set(e.target, newDeg)
          if (newDeg === 0) queue.push(e.target)
        }
      }
    }
    if (visited !== nodes.length) return 'Workflow contains a cycle. Remove circular connections to form a valid DAG.'

    return null
  }, [nodes, edges])

  // ------ Graph to pipeline phases (topological sort) --------------------
  const graphToPhases = useCallback(() => {
    // Kahn's topological sort
    const inDegree = new Map<string, number>()
    nodes.forEach((n) => inDegree.set(n.id, 0))
    for (const e of edges) {
      inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1)
    }
    const queue = Array.from(inDegree.entries()).filter(([, d]) => d === 0).map(([id]) => id)
    const sorted: string[] = []
    while (queue.length > 0) {
      const curr = queue.shift()!
      sorted.push(curr)
      for (const e of edges) {
        if (e.source === curr) {
          const newDeg = (inDegree.get(e.target) || 1) - 1
          inDegree.set(e.target, newDeg)
          if (newDeg === 0) queue.push(e.target)
        }
      }
    }

    // Map node IDs to unique phase names
    const nodeNameMap = new Map<string, string>()
    const usedNames = new Set<string>()
    for (const id of sorted) {
      const node = nodes.find((n) => n.id === id)!
      let name = node.label.replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 50)
      if (usedNames.has(name)) {
        let i = 2
        while (usedNames.has(`${name}_${i}`)) i++
        name = `${name}_${i}`
      }
      usedNames.add(name)
      nodeNameMap.set(id, name)
    }

    // Build phases array
    return sorted.map((id) => {
      const node = nodes.find((n) => n.id === id)!
      const deps = edges.filter((e) => e.target === id).map((e) => nodeNameMap.get(e.source)!)
      return {
        name: nodeNameMap.get(id)!,
        role: node.type.charAt(0).toUpperCase() + node.type.slice(1),
        default_model: node.config.model || undefined,
        system_prompt: node.config.systemPrompt || undefined,
        artifact_type: node.config.artifactType === 'json' ? 'json' : node.config.artifactType === 'code' ? 'code' : 'md',
        depends_on: deps.length > 0 ? deps : undefined,
      }
    })
  }, [nodes, edges])

  // ------ Run workflow ----------------------------------------------------
  const handleRunClick = useCallback(() => {
    const error = validateGraph()
    if (error) {
      addToast({ type: 'error', title: 'Invalid workflow', message: error, autoClose: 5000 })
      return
    }
    setRunError(null)
    setRunTask('')
    setShowRunModal(true)
  }, [validateGraph, addToast])

  const handleRunSubmit = useCallback(async () => {
    if (!runTask.trim()) { setRunError('Task description is required.'); return }
    setRunError(null)
    setRunLoading(true)
    const headers = apiHeaders()
    try {
      const phases = graphToPhases()
      const methodName = `builder-${(workflowName || 'workflow').replace(/[^a-zA-Z0-9_-]/g, '_')}-${Date.now()}`

      // 1. Create custom method from graph phases
      const methodRes = await fetch(`${getApiBase()}/v1/methods/custom`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ name: methodName, description: 'Auto-generated from Workflow Builder', phases }),
      })
      if (!methodRes.ok) {
        const detail = await methodRes.json().catch(() => ({}))
        throw new Error(detail.detail || `Method creation failed (${methodRes.status})`)
      }
      const method = await methodRes.json()

      // 2. Create workbench session
      const sessRes = await fetch(`${getApiBase()}/v1/workbench/sessions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ task: runTask.trim(), agent_type: 'coder', model: phases[0]?.default_model || undefined }),
      })
      if (!sessRes.ok) {
        const detail = await sessRes.json().catch(() => ({}))
        throw new Error(detail.detail || `Session creation failed (${sessRes.status})`)
      }
      const session = await sessRes.json()

      // 3. Create pipeline with custom method
      const pipeRes = await fetch(`${getApiBase()}/v1/workbench/pipelines`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ session_id: session.id, method_id: method.id || method.name, task: runTask.trim(), auto_approve: false }),
      })
      if (!pipeRes.ok) {
        const detail = await pipeRes.json().catch(() => ({}))
        throw new Error(detail.detail || `Pipeline creation failed (${pipeRes.status})`)
      }
      const pipeline = await pipeRes.json()

      // 4. Redirect to pipeline execution view
      setShowRunModal(false)
      router.push(`/workbench/pipelines/${pipeline.id}`)
    } catch (err: any) {
      setRunError(err.message || 'Failed to run workflow')
    } finally {
      setRunLoading(false)
    }
  }, [runTask, apiHeaders, graphToPhases, workflowName, router])

  // ------ Drop from palette onto canvas ----------------------------------
  const handleCanvasDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      if (!draggingType || !canvasRef.current) return

      const rect = canvasRef.current.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top

      // Check built-in agents first, then custom
      const agentType = AGENT_TYPES.find((a) => a.type === draggingType)
      const custom = !agentType ? customAgents.find((a) => a.id === draggingType) : null
      if (!agentType && !custom) return

      const newNode: WorkflowNode = {
        id: `node-${Date.now()}`,
        type: agentType ? agentType.type : custom!.agent_type,
        label: agentType ? agentType.label : custom!.name,
        x,
        y,
        config: {
          artifactType: 'markdown',
          ...(custom?.resolved_model_name ? { model: custom.resolved_model_name } : {}),
        },
      }
      setNodes((prev) => [...prev, newNode])
      setDraggingType(null)
    },
    [draggingType, customAgents],
  )

  // ------ Drag nodes on the canvas ----------------------------------------
  const handleNodeMouseDown = useCallback(
    (nodeId: string, startE: React.MouseEvent) => {
      startE.stopPropagation()
      const startX = startE.clientX
      const startY = startE.clientY
      const node = nodes.find((n) => n.id === nodeId)
      if (!node) return

      const handleMouseMove = (e: MouseEvent) => {
        const dx = e.clientX - startX
        const dy = e.clientY - startY
        setNodes((prev) =>
          prev.map((n) =>
            n.id === nodeId ? { ...n, x: node.x + dx, y: node.y + dy } : n,
          ),
        )
      }
      const handleMouseUp = () => {
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
      }
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    },
    [nodes],
  )

  // ------ Edge creation via shift+click -----------------------------------
  const handleNodeClick = useCallback(
    (nodeId: string, e: React.MouseEvent) => {
      if (e.shiftKey && edgeSource && edgeSource !== nodeId) {
        connectNodes(edgeSource, nodeId)
        setEdgeSource(null)
      } else if (e.shiftKey) {
        setEdgeSource(nodeId)
      } else {
        setSelectedNode(nodes.find((n) => n.id === nodeId) || null)
        setEdgeSource(null)
        setSelectedEdge(null)
      }
    },
    [edgeSource, nodes, connectNodes],
  )

  // ------ Toolbar actions -------------------------------------------------
  const handleClear = () => {
    if (nodes.length === 0) return
    setNodes([])
    setEdges([])
    setSelectedNode(null)
    setEdgeSource(null)
  }

  const handleDeleteNode = (nodeId: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== nodeId))
    setEdges((prev) =>
      prev.filter((e) => e.source !== nodeId && e.target !== nodeId),
    )
    if (selectedNode?.id === nodeId) setSelectedNode(null)
  }

  // ------ Handle-based edge dragging ------------------------------------
  const handleOutputHandleMouseDown = useCallback(
    (nodeId: string, e: React.MouseEvent) => {
      e.stopPropagation()
      e.preventDefault()
      setHandleDragSource(nodeId)
      setSelectedEdge(null)
    },
    [],
  )

  useEffect(() => {
    if (!handleDragSource) return
    const onMouseMove = (e: MouseEvent) => {
      if (!canvasRef.current) return
      const rect = canvasRef.current.getBoundingClientRect()
      setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
    }
    const onMouseUp = () => {
      setHandleDragSource(null)
      setMousePos(null)
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    return () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
  }, [handleDragSource])

  const handleInputHandleMouseUp = useCallback(
    (nodeId: string, e: React.MouseEvent) => {
      e.stopPropagation()
      if (handleDragSource && handleDragSource !== nodeId) {
        connectNodes(handleDragSource, nodeId)
      }
      setHandleDragSource(null)
      setMousePos(null)
    },
    [handleDragSource, connectNodes],
  )

  // ------ Delete selected edge via keyboard -----------------------------
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedEdge) {
        const tag = (e.target as HTMLElement)?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
        setEdges((prev) => prev.filter((edge) => edge.id !== selectedEdge))
        setSelectedEdge(null)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [selectedEdge])

  // ------ Edge click handler --------------------------------------------
  const handleEdgeClick = useCallback(
    (edgeId: string, e: React.MouseEvent) => {
      e.stopPropagation()
      setSelectedEdge(edgeId)
      setSelectedNode(null)
    },
    [],
  )

  // ------ Node config helpers --------------------------------------------
  const updateNodeField = <K extends keyof WorkflowNode>(
    nodeId: string,
    field: K,
    value: WorkflowNode[K],
  ) => {
    setNodes((prev) =>
      prev.map((n) => (n.id === nodeId ? { ...n, [field]: value } : n)),
    )
    setSelectedNode((prev) =>
      prev && prev.id === nodeId ? { ...prev, [field]: value } : prev,
    )
  }

  const updateNodeConfig = (
    nodeId: string,
    key: string,
    value: string | string[] | number,
  ) => {
    setNodes((prev) =>
      prev.map((n) =>
        n.id === nodeId
          ? { ...n, config: { ...n.config, [key]: value } }
          : n,
      ),
    )
    setSelectedNode((prev) =>
      prev && prev.id === nodeId
        ? { ...prev, config: { ...prev.config, [key]: value } }
        : prev,
    )
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    // Break out of the parent layout padding / max-width so the builder fills
    // the viewport. The main layout applies px-6 py-6 ... max-w-7xl, we negate
    // those here with negative margins and full-width overrides.
    <div className="-mx-6 -my-6 md:-mx-8 md:-my-7 lg:-mx-10 lg:-my-8 flex flex-col h-[100dvh] max-w-none bg-zinc-950 text-zinc-100">
      {/* ============================================================== */}
      {/* Top Toolbar                                                     */}
      {/* ============================================================== */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900 shrink-0">
        <div className="flex items-center gap-3">
          <a
            href="/workbench"
            className="text-zinc-400 hover:text-zinc-200 text-sm transition-colors"
          >
            &larr; Workbench
          </a>
          <h1 className="text-lg font-semibold">Workflow Builder</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={openLoadModal}
            className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors"
          >
            Load
          </button>
          <button
            onClick={() => { setSaveError(null); setShowSaveModal(true) }}
            className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors"
          >
            Save
          </button>
          <button
            onClick={handleClear}
            className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors"
          >
            Clear
          </button>
          <button
            onClick={handleRunClick}
            className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 transition-colors"
            disabled={nodes.length === 0}
          >
            Run &#9654;
          </button>
        </div>
      </div>

      {/* ============================================================== */}
      {/* Three-column body                                               */}
      {/* ============================================================== */}
      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* -------------------------------------------------------------- */}
        {/* Left sidebar: Agent palette                                     */}
        {/* -------------------------------------------------------------- */}
        <div className="w-56 border-r border-zinc-800 bg-zinc-900 p-3 overflow-y-auto shrink-0">
          <h2 className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
            Agents
          </h2>
          {/* Search input */}
          <input
            type="text"
            value={paletteSearch}
            onChange={(e) => setPaletteSearch(e.target.value)}
            placeholder="Search agents…"
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm mb-3 focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder-zinc-600"
          />
          {/* Default agent types */}
          {filteredDefaults.map((agent) => (
            <div
              key={agent.type}
              draggable
              onDragStart={() => setDraggingType(agent.type)}
              className="flex items-center gap-2 p-2 mb-1 rounded cursor-grab hover:bg-zinc-800 border border-transparent hover:border-zinc-700 transition-colors"
            >
              <span className="text-lg">{agent.icon}</span>
              <div className="min-w-0">
                <div className="text-sm font-medium">{agent.label}</div>
                <div className="text-xs text-zinc-500 truncate">{agent.description}</div>
              </div>
            </div>
          ))}
          {/* Custom agents from API */}
          {filteredCustom.length > 0 && (
            <>
              <h3 className="text-xs uppercase tracking-wider text-zinc-500 mt-4 mb-2">
                Custom
              </h3>
              {filteredCustom.map((agent) => (
                <div
                  key={agent.id}
                  draggable
                  onDragStart={() => setDraggingType(agent.id)}
                  className="flex items-center gap-2 p-2 mb-1 rounded cursor-grab hover:bg-zinc-800 border border-transparent hover:border-zinc-700 transition-colors"
                >
                  <span className="text-lg">{'\u{1F916}'}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{agent.name}</div>
                    <div className="text-xs text-zinc-500 truncate">{agent.description ?? agent.agent_type}</div>
                  </div>
                </div>
              ))}
            </>
          )}
          {filteredDefaults.length === 0 && filteredCustom.length === 0 && (
            <p className="text-xs text-zinc-600 mt-2">No agents match &ldquo;{paletteSearch}&rdquo;</p>
          )}
          <div className="mt-4 pt-3 border-t border-zinc-800">
            <p className="text-xs text-zinc-600">
              Drag agents onto the canvas. Drag between handles or Shift+click
              two nodes to connect them. Click an edge &amp; press Delete to remove.
            </p>
          </div>
        </div>

        {/* -------------------------------------------------------------- */}
        {/* Center: Canvas                                                  */}
        {/* -------------------------------------------------------------- */}
        <div
          ref={canvasRef}
          className="flex-1 relative overflow-hidden"
          onDrop={handleCanvasDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => {
            setSelectedNode(null)
            setEdgeSource(null)
            setSelectedEdge(null)
            setHandleDragSource(null)
          }}
        >
          {/* Dot-grid background */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              backgroundImage:
                'radial-gradient(circle, #27272a 1px, transparent 1px)',
              backgroundSize: '24px 24px',
            }}
          />

          {/* Empty state message */}
          {nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center text-zinc-600">
                <div className="text-4xl mb-3">{'\u{1F527}'}</div>
                <div className="text-lg">
                  Drag agents from the left to start building your workflow
                </div>
                <div className="text-sm mt-1">
                  Drag between node handles or Shift+click to connect
                </div>
              </div>
            </div>
          )}

          {/* SVG layer for edges */}
          <svg
            className="absolute inset-0 w-full h-full"
            style={{ zIndex: 1, pointerEvents: 'none' }}
          >
            <defs>
              <marker
                id="arrowhead"
                markerWidth="10"
                markerHeight="7"
                refX="10"
                refY="3.5"
                orient="auto"
              >
                <polygon points="0 0, 10 3.5, 0 7" fill="#3b82f6" />
              </marker>
              <marker
                id="arrowhead-selected"
                markerWidth="10"
                markerHeight="7"
                refX="10"
                refY="3.5"
                orient="auto"
              >
                <polygon points="0 0, 10 3.5, 0 7" fill="#f59e0b" />
              </marker>
            </defs>
            {edges.map((edge) => {
              const source = nodes.find((n) => n.id === edge.source)
              const target = nodes.find((n) => n.id === edge.target)
              if (!source || !target) return null
              const x1 = source.x + NODE_W / 2
              const y1 = source.y + NODE_H
              const x2 = target.x + NODE_W / 2
              const y2 = target.y
              const dy = Math.abs(y2 - y1)
              const cp = Math.max(50, dy * 0.5)
              const d = `M ${x1},${y1} C ${x1},${y1 + cp} ${x2},${y2 - cp} ${x2},${y2}`
              const isSel = selectedEdge === edge.id
              return (
                <g key={edge.id} style={{ pointerEvents: 'auto' }}>
                  {/* Wide invisible hit-area for click detection */}
                  <path
                    d={d}
                    stroke="transparent"
                    strokeWidth={14}
                    fill="none"
                    className="cursor-pointer"
                    onClick={(e) => handleEdgeClick(edge.id, e)}
                  />
                  {/* Visible edge */}
                  <path
                    d={d}
                    stroke={isSel ? '#f59e0b' : '#3b82f6'}
                    strokeWidth={isSel ? 2.5 : 2}
                    fill="none"
                    markerEnd={isSel ? 'url(#arrowhead-selected)' : 'url(#arrowhead)'}
                    strokeDasharray="8 4"
                    className="pointer-events-none"
                  >
                    <animate
                      attributeName="stroke-dashoffset"
                      from="12"
                      to="0"
                      dur={isSel ? '0.6s' : '1s'}
                      repeatCount="indefinite"
                    />
                  </path>
                </g>
              )
            })}
            {/* In-progress drag edge */}
            {handleDragSource && mousePos && (() => {
              const src = nodes.find((n) => n.id === handleDragSource)
              if (!src) return null
              const x1 = src.x + NODE_W / 2
              const y1 = src.y + NODE_H
              const x2 = mousePos.x
              const y2 = mousePos.y
              const dy = Math.abs(y2 - y1)
              const cp = Math.max(50, dy * 0.5)
              const d = `M ${x1},${y1} C ${x1},${y1 + cp} ${x2},${y2 - cp} ${x2},${y2}`
              return (
                <path
                  d={d}
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="none"
                  strokeDasharray="6 3"
                  opacity={0.6}
                  className="pointer-events-none"
                />
              )
            })()}
          </svg>

          {/* Node cards */}
          {nodes.map((node) => {
            const agentType = AGENT_TYPES.find((a) => a.type === node.type)
            const isSelected = selectedNode?.id === node.id
            const isEdgeSrc = edgeSource === node.id
            const badgeColor = TYPE_COLORS[node.type] || 'bg-zinc-600'
            return (
              <div
                key={node.id}
                className={`absolute cursor-move select-none rounded-lg border-2 p-3 w-44 transition-colors ${
                  isSelected
                    ? 'border-blue-500 bg-zinc-800'
                    : isEdgeSrc
                      ? 'border-yellow-500 bg-zinc-800'
                      : 'border-zinc-700 bg-zinc-900 hover:border-zinc-500'
                }`}
                style={{ left: node.x, top: node.y, zIndex: 2 }}
                onMouseDown={(e) => handleNodeMouseDown(node.id, e)}
                onClick={(e) => {
                  e.stopPropagation()
                  handleNodeClick(node.id, e)
                }}
              >
                {/* Input handle (top center) */}
                <div
                  className="absolute -top-2 left-1/2 -translate-x-1/2 w-4 h-4 rounded-full border-2 border-blue-500 bg-zinc-900 cursor-crosshair hover:bg-blue-500 hover:scale-125 transition-all"
                  onMouseUp={(e) => handleInputHandleMouseUp(node.id, e)}
                />
                {/* Output handle (bottom center) */}
                <div
                  className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-4 h-4 rounded-full border-2 border-blue-500 bg-zinc-900 cursor-crosshair hover:bg-blue-500 hover:scale-125 transition-all"
                  onMouseDown={(e) => handleOutputHandleMouseDown(node.id, e)}
                />
                <div className="flex items-center gap-2">
                  {/* Status indicator */}
                  <span className="relative flex h-2.5 w-2.5 shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500" />
                  </span>
                  <span>{agentType?.icon ?? '\u{1F916}'}</span>
                  <span className="text-sm font-medium truncate">
                    {node.label}
                  </span>
                </div>
                {/* Type badge + model */}
                <div className="flex items-center gap-1.5 mt-1.5">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium leading-none ${badgeColor}`}>
                    {node.type}
                  </span>
                  <span className="text-[10px] text-zinc-500 truncate">
                    {node.config.model || 'default'}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        {/* -------------------------------------------------------------- */}
        {/* Right panel: Node configuration (slides open on select)         */}
        {/* -------------------------------------------------------------- */}
        <div
          className={`shrink-0 overflow-hidden transition-[width] duration-200 ease-in-out ${
            selectedNode ? 'w-80' : 'w-0'
          }`}
        >
          <div className="w-80 h-full border-l border-zinc-800 bg-zinc-900 p-4 overflow-y-auto">
            {selectedNode && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold">Node Configuration</h2>
                  <button
                    onClick={() => setSelectedNode(null)}
                    className="text-zinc-500 hover:text-zinc-300 transition-colors text-lg leading-none"
                    title="Close panel"
                  >
                    &times;
                  </button>
                </div>
                <div className="space-y-4">
                  {/* Name */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">Name</label>
                    <input
                      value={selectedNode.label}
                      onChange={(e) => updateNodeField(selectedNode.id, 'label', e.target.value)}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>

                  {/* Agent Type */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">Agent Type</label>
                    <select
                      value={selectedNode.type}
                      onChange={(e) => updateNodeField(selectedNode.id, 'type', e.target.value)}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                    >
                      {AGENT_TYPES.map((a) => (
                        <option key={a.type} value={a.type}>{a.icon} {a.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* Model */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">Model</label>
                    <select
                      value={selectedNode.config.model || ''}
                      onChange={(e) => updateNodeConfig(selectedNode.id, 'model', e.target.value)}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                    >
                      <option value="">Default</option>
                      {availableModels.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>

                  {/* System Prompt */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">System Prompt</label>
                    <textarea
                      value={selectedNode.config.systemPrompt || ''}
                      onChange={(e) => updateNodeConfig(selectedNode.id, 'systemPrompt', e.target.value)}
                      rows={4}
                      placeholder="Custom instructions for this agent…"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm resize-y focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[60px]"
                    />
                  </div>

                  {/* Tools */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-2">Tools</label>
                    <div className="space-y-1">
                      {['web_search', 'code_execution', 'file_ops'].map((tool) => (
                        <label key={tool} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-zinc-800/50 rounded px-2 py-1 -mx-2 transition-colors">
                          <input
                            type="checkbox"
                            checked={(selectedNode.config.tools || []).includes(tool)}
                            onChange={(e) => {
                              const current = selectedNode.config.tools || []
                              const next = e.target.checked
                                ? [...current, tool]
                                : current.filter((t) => t !== tool)
                              updateNodeConfig(selectedNode.id, 'tools', next)
                            }}
                            className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                          />
                          <span className="text-zinc-300">{tool.replace(/_/g, ' ')}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Max Iterations */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">Max Iterations</label>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={selectedNode.config.maxIterations ?? 10}
                      onChange={(e) => updateNodeConfig(selectedNode.id, 'maxIterations', parseInt(e.target.value) || 1)}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>

                  {/* Timeout */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">Timeout (seconds)</label>
                    <input
                      type="number"
                      min={1}
                      max={3600}
                      value={selectedNode.config.timeout ?? 300}
                      onChange={(e) => updateNodeConfig(selectedNode.id, 'timeout', parseInt(e.target.value) || 1)}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>

                  {/* Artifact Type */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">Artifact Type</label>
                    <div className="flex gap-1">
                      {(['json', 'code', 'markdown'] as const).map((at) => (
                        <button
                          key={at}
                          onClick={() => updateNodeConfig(selectedNode.id, 'artifactType', at)}
                          className={`flex-1 px-2 py-1.5 text-xs rounded border transition-colors ${
                            (selectedNode.config.artifactType || 'markdown') === at
                              ? 'bg-blue-600 border-blue-500 text-white'
                              : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500'
                          }`}
                        >
                          {at.charAt(0).toUpperCase() + at.slice(1)}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Condition */}
                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">
                      Condition <span className="text-zinc-600">(optional)</span>
                    </label>
                    <textarea
                      value={selectedNode.config.condition || ''}
                      onChange={(e) => updateNodeConfig(selectedNode.id, 'condition', e.target.value)}
                      rows={2}
                      placeholder="e.g. output.status === 'approved'"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs font-mono resize-y focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[40px]"
                    />
                  </div>

                  {/* Delete */}
                  <div className="pt-3 border-t border-zinc-800">
                    <button
                      onClick={() => handleDeleteNode(selectedNode.id)}
                      className="w-full px-3 py-1.5 text-sm rounded bg-red-900/30 border border-red-800/50 text-red-400 hover:bg-red-900/50 hover:text-red-300 transition-colors"
                    >
                      Delete Node
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ============================================================== */}
      {/* Save Modal                                                      */}
      {/* ============================================================== */}
      {showSaveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowSaveModal(false)}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-5 w-96 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4">{currentWorkflowId ? 'Update Workflow' : 'Save Workflow'}</h2>
            <label className="text-xs text-zinc-500 block mb-1">Name</label>
            <input
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              placeholder="My Workflow"
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-1 focus:ring-blue-500"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            />
            {saveError && <p className="text-xs text-red-400 mb-2">{saveError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowSaveModal(false)} className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700">Cancel</button>
              <button onClick={handleSave} className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white">Save</button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* Load Modal                                                      */}
      {/* ============================================================== */}
      {showLoadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowLoadModal(false)}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-5 w-[480px] max-h-[70vh] flex flex-col shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4">Load Workflow</h2>
            {loadingWorkflows ? (
              <p className="text-sm text-zinc-500">Loading…</p>
            ) : savedWorkflows.length === 0 ? (
              <p className="text-sm text-zinc-500">No saved workflows yet.</p>
            ) : (
              <div className="overflow-y-auto flex-1 space-y-2">
                {savedWorkflows.map((wf) => (
                  <div key={wf.id} className="flex items-center justify-between p-3 rounded bg-zinc-800 border border-zinc-700 hover:border-zinc-500 transition-colors">
                    <button onClick={() => handleLoad(wf)} className="flex-1 text-left">
                      <div className="text-sm font-medium">{wf.name}</div>
                      <div className="text-xs text-zinc-500">{wf.graph_data?.nodes?.length ?? 0} nodes · updated {new Date(wf.updated_at).toLocaleDateString()}</div>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteWorkflow(wf.id) }}
                      className="ml-2 text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-zinc-700"
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-end mt-4">
              <button onClick={() => setShowLoadModal(false)} className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700">Close</button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* Run Workflow Modal                                               */}
      {/* ============================================================== */}
      {showRunModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => !runLoading && setShowRunModal(false)}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-5 w-[480px] shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-1">Run Workflow</h2>
            <p className="text-xs text-zinc-500 mb-4">
              {nodes.length} node{nodes.length !== 1 ? 's' : ''} &middot; {edges.length} connection{edges.length !== 1 ? 's' : ''}
            </p>
            <label className="text-xs text-zinc-500 block mb-1">Task Description</label>
            <textarea
              value={runTask}
              onChange={(e) => setRunTask(e.target.value)}
              placeholder="Describe what this workflow should accomplish…"
              rows={4}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm mb-3 resize-y focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[80px]"
              autoFocus
              disabled={runLoading}
              onKeyDown={(e) => { if (e.key === 'Enter' && e.ctrlKey) handleRunSubmit() }}
            />
            <p className="text-xs text-zinc-600 mb-3">Ctrl+Enter to submit</p>
            {runError && <p className="text-xs text-red-400 mb-3">{runError}</p>}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowRunModal(false)}
                disabled={runLoading}
                className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleRunSubmit}
                disabled={runLoading || !runTask.trim()}
                className="px-4 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 transition-colors"
              >
                {runLoading ? 'Launching…' : 'Run \u25B6'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

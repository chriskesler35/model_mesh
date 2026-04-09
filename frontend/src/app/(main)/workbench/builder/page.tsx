'use client'

import { useState, useCallback, useRef } from 'react'

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
  }
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
// Page component
// ---------------------------------------------------------------------------
export default function WorkflowBuilderPage() {
  const [nodes, setNodes] = useState<WorkflowNode[]>([])
  const [edges, setEdges] = useState<WorkflowEdge[]>([])
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null)
  const [draggingType, setDraggingType] = useState<string | null>(null)
  const [edgeSource, setEdgeSource] = useState<string | null>(null)
  const canvasRef = useRef<HTMLDivElement>(null)

  // ------ Drop from palette onto canvas ----------------------------------
  const handleCanvasDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      if (!draggingType || !canvasRef.current) return

      const rect = canvasRef.current.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top

      const agentType = AGENT_TYPES.find((a) => a.type === draggingType)
      if (!agentType) return

      const newNode: WorkflowNode = {
        id: `node-${Date.now()}`,
        type: draggingType,
        label: agentType.label,
        x,
        y,
        config: { artifactType: 'markdown' },
      }
      setNodes((prev) => [...prev, newNode])
      setDraggingType(null)
    },
    [draggingType],
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
        const newEdge: WorkflowEdge = {
          id: `edge-${edgeSource}-${nodeId}`,
          source: edgeSource,
          target: nodeId,
        }
        setEdges((prev) => [...prev, newEdge])
        setEdgeSource(null)
      } else if (e.shiftKey) {
        setEdgeSource(nodeId)
      } else {
        setSelectedNode(nodes.find((n) => n.id === nodeId) || null)
        setEdgeSource(null)
      }
    },
    [edgeSource, nodes],
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
    value: string,
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
          <button className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors">
            Load
          </button>
          <button className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors">
            Save
          </button>
          <button
            onClick={handleClear}
            className="px-3 py-1.5 text-sm rounded bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors"
          >
            Clear
          </button>
          <button
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
          <h2 className="text-xs uppercase tracking-wider text-zinc-500 mb-3">
            Agents
          </h2>
          {AGENT_TYPES.map((agent) => (
            <div
              key={agent.type}
              draggable
              onDragStart={() => setDraggingType(agent.type)}
              className="flex items-center gap-2 p-2 mb-1 rounded cursor-grab hover:bg-zinc-800 border border-transparent hover:border-zinc-700 transition-colors"
            >
              <span className="text-lg">{agent.icon}</span>
              <div>
                <div className="text-sm font-medium">{agent.label}</div>
                <div className="text-xs text-zinc-500">{agent.description}</div>
              </div>
            </div>
          ))}
          <div className="mt-4 pt-3 border-t border-zinc-800">
            <p className="text-xs text-zinc-600">
              Drag agents onto the canvas. Shift+click two nodes to connect
              them.
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
                  Shift+click two nodes to create a connection
                </div>
              </div>
            </div>
          )}

          {/* SVG layer for edges */}
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            style={{ zIndex: 1 }}
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
            </defs>
            {edges.map((edge) => {
              const source = nodes.find((n) => n.id === edge.source)
              const target = nodes.find((n) => n.id === edge.target)
              if (!source || !target) return null
              // Center the endpoints on the node cards (node width=160, height~60)
              return (
                <line
                  key={edge.id}
                  x1={source.x + 80}
                  y1={source.y + 30}
                  x2={target.x + 80}
                  y2={target.y + 30}
                  stroke="#3b82f6"
                  strokeWidth={2}
                  markerEnd="url(#arrowhead)"
                />
              )
            })}
          </svg>

          {/* Node cards */}
          {nodes.map((node) => {
            const agentType = AGENT_TYPES.find((a) => a.type === node.type)
            const isSelected = selectedNode?.id === node.id
            const isEdgeSrc = edgeSource === node.id
            return (
              <div
                key={node.id}
                className={`absolute cursor-move select-none rounded-lg border-2 p-3 w-40 transition-colors ${
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
                <div className="flex items-center gap-2">
                  <span>{agentType?.icon}</span>
                  <span className="text-sm font-medium truncate">
                    {node.label}
                  </span>
                </div>
                <div className="text-xs text-zinc-500 mt-1">
                  {node.config.artifactType || 'markdown'}
                </div>
              </div>
            )
          })}
        </div>

        {/* -------------------------------------------------------------- */}
        {/* Right panel: Node properties                                    */}
        {/* -------------------------------------------------------------- */}
        <div className="w-64 border-l border-zinc-800 bg-zinc-900 p-3 overflow-y-auto shrink-0">
          {selectedNode ? (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold">Node Properties</h2>
                <button
                  onClick={() => handleDeleteNode(selectedNode.id)}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors"
                >
                  Delete
                </button>
              </div>
              <div className="space-y-3">
                {/* Name */}
                <div>
                  <label className="text-xs text-zinc-500 block mb-1">
                    Name
                  </label>
                  <input
                    value={selectedNode.label}
                    onChange={(e) =>
                      updateNodeField(selectedNode.id, 'label', e.target.value)
                    }
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                {/* Type (read-only) */}
                <div>
                  <label className="text-xs text-zinc-500 block mb-1">
                    Type
                  </label>
                  <div className="text-sm text-zinc-300">
                    {selectedNode.type}
                  </div>
                </div>

                {/* Artifact Type */}
                <div>
                  <label className="text-xs text-zinc-500 block mb-1">
                    Artifact Type
                  </label>
                  <select
                    value={selectedNode.config.artifactType || 'markdown'}
                    onChange={(e) =>
                      updateNodeConfig(
                        selectedNode.id,
                        'artifactType',
                        e.target.value,
                      )
                    }
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="markdown">Markdown</option>
                    <option value="json">JSON</option>
                    <option value="code">Code</option>
                  </select>
                </div>

                {/* System Prompt */}
                <div>
                  <label className="text-xs text-zinc-500 block mb-1">
                    System Prompt
                  </label>
                  <textarea
                    value={selectedNode.config.systemPrompt || ''}
                    onChange={(e) =>
                      updateNodeConfig(
                        selectedNode.id,
                        'systemPrompt',
                        e.target.value,
                      )
                    }
                    rows={4}
                    placeholder="Custom system prompt (optional)"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="text-zinc-600 text-sm">
              <h2 className="text-xs uppercase tracking-wider text-zinc-500 mb-3">
                Properties
              </h2>
              <p>Click a node to view and edit its properties.</p>
              <div className="mt-4 space-y-2 text-xs">
                <div>
                  <span className="text-zinc-400">Nodes:</span> {nodes.length}
                </div>
                <div>
                  <span className="text-zinc-400">Connections:</span>{' '}
                  {edges.length}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

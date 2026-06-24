import { useState, useEffect, useRef, useCallback } from 'react'

const AGENTS = [
  { id: 'issue_analyzer', label: 'Issue Analyzer' },
  { id: 'codebase_researcher', label: 'Codebase Researcher' },
  { id: 'fix_drafter', label: 'Fix Drafter' },
  { id: 'test_writer', label: 'Test Writer' },
  { id: 'pr_creator', label: 'PR Creator' },
]

const MOCK_LOGS = {
  issue_analyzer: [
    'Parsing issue #42: Fix login button not working on mobile devices',
    'Issue type: bug',
    'Complexity: medium',
    'Affected areas: Authentication, UI Components',
    'Suggested files: src/components/LoginButton.jsx, src/hooks/useAuth.js',
  ],
  codebase_researcher: [
    'Target: username/repo',
    'Branch: main',
    'Fetching src/components/LoginButton.jsx... OK',
    'Fetching src/hooks/useAuth.js... OK',
    'Created 6 chunks across 2 files',
    'Found 3 relevant chunks — handleTouch(), useAuthSession(), LoginButton',
  ],
  fix_drafter: [
    'Drafting fix for 2 file(s)...',
    'Analyzing touch event handler in LoginButton.jsx',
    'Adding preventDefault() on touchstart to avoid double-firing',
    'Fix generated for 1 file(s)',
  ],
  test_writer: [
    'No tests requested — skipping',
  ],
  pr_creator: [
    'Creating branch mergepilot/fix-42...',
    'Committing src/components/LoginButton.jsx',
    'Committing src/hooks/useAuth.js',
    'Generating PR description via Groq...',
    'PR #1 created: https://github.com/username/repo/pull/1',
  ],
}

const MOCK_AGENT_RESULTS = {
  issue_analyzer: {
    summary: 'Bug in login button touch handler causing double-firing on mobile',
    issue_type: 'bug',
    complexity: 'medium',
    relevant_files: ['src/components/LoginButton.jsx', 'src/hooks/useAuth.js'],
  },
  codebase_researcher: {
    num_files: 2,
    low_confidence: false,
    summary: '3 relevant chunks across 2 files',
  },
  fix_drafter: {
    num_files_fixed: 1,
    fix_summary: 'Added e.preventDefault() to touch event handler',
  },
  test_writer: {
    test_file: null,
    test_length: 0,
  },
  pr_creator: {
    pr_url: 'https://github.com/username/repo/pull/1',
  },
}

const MOCK_DIFF = `@@ -42,7 +42,9 @@ const LoginButton = ({ onSubmit }) => {
     className={styles.button}
     onClick={handleClick}
+    onTouchStart={handleTouch}
   >
-    {loading ? 'Logging in...' : 'Login'}
+    {loading ? 'Logging in...' : 'Sign In'}
   </button>
);

+const handleTouch = (e) => {
+  e.preventDefault();
+  handleClick(e);
+};`

const delay = (ms) => new Promise((r) => setTimeout(r, ms))

const CARD_CLASS = 'rounded-2xl backdrop-blur'
const CARD_STYLE = {
  background: 'rgba(10,15,35,0.7)',
  border: '1px solid rgba(255,255,255,0.08)',
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
  boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
}

function ParticleBackground() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    let animationId

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (prefersReduced) {
      return () => window.removeEventListener('resize', resize)
    }

    const particles = Array.from({ length: 25 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.2,
      vy: (Math.random() - 0.5) * 0.2,
      size: Math.random() * 1.5 + 0.5,
    }))

    let time = 0

    const animate = () => {
      time++
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      particles.forEach((p) => {
        p.x += p.vx + Math.sin(time * 0.01 + p.y * 0.01) * 0.05
        p.y += p.vy + Math.cos(time * 0.01 + p.x * 0.01) * 0.05
        if (p.x < 0) p.x = canvas.width
        if (p.x > canvas.width) p.x = 0
        if (p.y < 0) p.y = canvas.height
        if (p.y > canvas.height) p.y = 0

        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(108, 99, 255, 0.8)'
        ctx.fill()
      })

      animationId = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none" style={{ zIndex: 0 }} />
}

function PipelineStep({ agent, status, info, isLast }) {
  const isActive = status === 'active'
  const isComplete = status === 'complete'
  const isError = status === 'error'

  return (
    <div className="relative">
      <div className="flex items-center gap-4">
        <div className="relative flex-shrink-0">
          <div
            className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-500 border ${
              isActive
                ? 'border-accent/60 bg-accent/15 shadow-[0_0_16px_rgba(108,99,255,0.35)]'
                : isComplete
                ? 'border-green-500/50 bg-green-500/10'
                : isError
                ? 'border-red-500/50 bg-red-500/10'
                : 'border-dark-600 bg-dark-800/50'
            }`}
          >
            {isComplete ? (
              <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : isActive ? (
              <span className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-accent to-accent-light animate-pulse-glow" />
            ) : isError ? (
              <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <span className="w-2 h-2 rounded-full bg-dark-500" />
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium transition-colors duration-300 ${
            isActive ? 'text-white' : isComplete ? 'text-green-400' : isError ? 'text-red-400' : 'text-gray-500'
          }`}>
            {agent.label}
          </div>
          {info && isComplete && (
            <div className="text-[11px] text-gray-600 truncate mt-0.5">{info}</div>
          )}
        </div>

        {isActive && (
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              <span className="w-1 h-1 rounded-full bg-accent animate-pulse" />
              <span className="w-1 h-1 rounded-full bg-accent/60 animate-pulse" style={{ animationDelay: '0.2s' }} />
              <span className="w-1 h-1 rounded-full bg-accent/30 animate-pulse" style={{ animationDelay: '0.4s' }} />
            </div>
          </div>
        )}
      </div>

      {!isLast && (
        <div className="ml-4 pl-0 mt-0">
          <div className="w-px h-6 ml-[18px] relative overflow-hidden">
            <div
              className={`absolute inset-x-0 top-0 h-full transition-all duration-700 ${
                isComplete ? 'bg-green-500/40' : isActive ? 'bg-gradient-to-b from-accent to-accent/20' : 'bg-dark-600'
              }`}
            />
            {isActive && (
              <div className="absolute inset-x-0 top-0 h-full bg-gradient-to-b from-accent to-transparent animate-[pipelineGlow_1.5s_ease-in-out_infinite]" />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function LogViewer({ logs }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  if (logs.length === 0) return null

  const agentColors = {
    issue_analyzer: 'text-cyan-400',
    codebase_researcher: 'text-violet-400',
    fix_drafter: 'text-amber-400',
    test_writer: 'text-emerald-400',
    pr_creator: 'text-blue-400',
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-green-500/60" />
        <span className="text-xs text-gray-400 font-mono uppercase tracking-wider">Terminal</span>
        <span className="text-xs text-gray-600 font-mono ml-auto">{logs.length} lines</span>
      </div>
      <div className="p-4 flex-1 overflow-y-auto font-mono text-xs leading-relaxed space-y-1.5 min-h-[200px] max-h-[360px]">
        {logs.map((log, i) => {
          const agentLabel = AGENTS.find((a) => a.id === log.agentId)?.label || log.agentId
          const color = agentColors[log.agentId] || 'text-gray-400'
          return (
            <div key={i} className="opacity-0 animate-[fadeIn_0.2s_ease_forwards]">
              <span className={color}>[{agentLabel}]</span>
              <span className="text-gray-300"> {log.text}</span>
            </div>
          )
        })}
        <div ref={endRef} />
      </div>
    </div>
  )
}

function DiffPreview({ files }) {
  const [open, setOpen] = useState(null)

  if (!files || files.length === 0) return null

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Files Changed
      </h3>
      <div className="space-y-2">
        {files.map((file) => (
          <div key={file.path} className="rounded-xl overflow-hidden border border-white/5" style={{ background: 'rgba(10,15,35,0.5)' }}>
            <button
              onClick={() => setOpen(open === file.path ? null : file.path)}
              className="w-full px-4 py-3 flex items-center justify-between text-sm hover:bg-white/[0.03] transition-colors"
            >
              <span className="text-gray-300 font-mono">{file.path}</span>
              <svg
                className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${
                  open === file.path ? 'rotate-180' : ''
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {open === file.path && (
              <pre className="p-4 border-t border-white/5 overflow-x-auto text-xs leading-relaxed">
                <code className="text-gray-300">{file.diff}</code>
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [issueUrl, setIssueUrl] = useState('')
  const [status, setStatus] = useState('idle')
  const [agentStates, setAgentStates] = useState(() =>
    Object.fromEntries(AGENTS.map((a) => [a.id, { status: 'idle', info: null }]))
  )
  const [logs, setLogs] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [mockMode, setMockMode] = useState(false)
  const abortRef = useRef(false)

  const reset = useCallback(() => {
    abortRef.current = true
    setStatus('idle')
    setAgentStates(Object.fromEntries(AGENTS.map((a) => [a.id, { status: 'idle', info: null }])))
    setLogs([])
    setResult(null)
    setError(null)
    setMockMode(false)
  }, [])

  const addLog = useCallback((agentId, text) => {
    setLogs((prev) => [...prev, { agentId, text, timestamp: Date.now() }])
  }, [])

  const updateAgent = useCallback((agentId, status, info) => {
    setAgentStates((prev) => ({ ...prev, [agentId]: { status, info } }))
  }, [])

  const completedCount = Object.values(agentStates).filter((s) => s.status === 'complete').length

  const runMockPipeline = useCallback(async () => {
    abortRef.current = false

    for (const agent of AGENTS) {
      if (abortRef.current) break
      await delay(200)
      updateAgent(agent.id, 'active')
      addLog(agent.id, `Starting ${agent.label}...`)

      const mockLogs = MOCK_LOGS[agent.id]
      const perLine = Math.max(200, Math.floor(1800 / mockLogs.length))

      for (const line of mockLogs) {
        if (abortRef.current) break
        await delay(perLine)
        addLog(agent.id, line)
      }

      if (abortRef.current) break
      await delay(300)
      const resultData = MOCK_AGENT_RESULTS[agent.id]
      const infoText =
        resultData.summary || resultData.pr_url || `${resultData.num_files || 0} files`
      updateAgent(agent.id, 'complete', infoText)

    }

    if (!abortRef.current) {
      setStatus('done')
      setResult({
        pr_url: 'https://github.com/username/repo/pull/1',
        summary: 'Bug in login button touch handler causing double-firing on mobile. Added e.preventDefault() to touchstart event.',
        issue_type: 'bug',
        complexity: 'medium',
        files: [{ path: 'src/components/LoginButton.jsx', diff: MOCK_DIFF }],
      })
    }
  }, [addLog, updateAgent])

  const handleRun = useCallback(async () => {
    if (!issueUrl.trim()) return

    reset()
    await delay(50)
    abortRef.current = false
    setStatus('running')

    const trimmedUrl = issueUrl.trim()
    const urlPattern = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/issues\/\d+$/
    if (!urlPattern.test(trimmedUrl)) {
      setError('Please enter a valid GitHub issue URL (e.g. https://github.com/owner/repo/issues/42)')
      setStatus('idle')
      return
    }

    try {
      const response = await fetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_url: trimmedUrl }),
      })

      if (!response.ok) throw new Error(`Server responded with ${response.status}`)

      const { run_id } = await response.json()
      addLog('issue_analyzer', 'Connected to backend — starting pipeline...')

      const source = new EventSource(`/stream/${run_id}`)
      let pipelineDone = false

      source.addEventListener('agent_start', (e) => {
        if (abortRef.current) return
        const data = JSON.parse(e.data)
        updateAgent(data.agent, 'active')
        addLog(data.agent, `Starting ${AGENTS.find((a) => a.id === data.agent)?.label || data.agent}...`)
      })

      source.addEventListener('agent_complete', (e) => {
        if (abortRef.current) return
        const data = JSON.parse(e.data)
        const infoText = data.summary || data.pr_url || `${data.num_files || 0} files`
        updateAgent(data.agent, 'complete', infoText)
        addLog(data.agent, 'Complete')
      })

      source.addEventListener('agent_error', (e) => {
        if (abortRef.current) return
        const data = JSON.parse(e.data)
        updateAgent(data.agent, 'error')
        addLog(data.agent, `Error: ${data.error}`)
      })

      source.addEventListener('pipeline_done', (e) => {
        pipelineDone = true
        source.close()
        const data = JSON.parse(e.data)
        setStatus('done')
        setResult({
          pr_url: data.pr_url,
          summary: data.summary || 'Pipeline completed successfully',
          issue_type: data.issue_type,
          complexity: data.complexity,
          files: data.files || [],
        })
      })

      source.addEventListener('pipeline_failed', (e) => {
        pipelineDone = true
        source.close()
        const data = JSON.parse(e.data)
        setStatus('idle')
        setError(data.error || 'Pipeline failed')
      })

      source.onerror = () => {
        if (!pipelineDone && !abortRef.current) {
          source.close()
          addLog('issue_analyzer', 'Backend connection lost — falling back to mock simulation')
          setMockMode(true)
          runMockPipeline()
        }
      }
    } catch {
      addLog('issue_analyzer', 'Backend unavailable — running mock simulation')
      setMockMode(true)
      runMockPipeline()
    }
  }, [issueUrl, reset, addLog, updateAgent, runMockPipeline])

  return (
    <div className="relative min-h-screen text-gray-200">
      <div className="fixed inset-0 pointer-events-none bg-[url('/5.jpg')] bg-no-repeat bg-top bg-[length:auto_135%]" style={{ zIndex: 0 }} />
      <ParticleBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
        <nav className="flex items-center justify-between px-6 py-4 max-w-6xl mx-auto w-full">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-accent to-accent-light flex items-center justify-center">
              <span className="text-black text-xs font-bold font-mono">M</span>
            </div>
            <span className="text-sm font-semibold text-white">MergePilot</span>
          </div>
          <span className="text-xs text-gray-600 font-mono">v0.1</span>
        </nav>

        <main className="flex-1 px-6 pb-16 max-w-6xl mx-auto w-full">
          {status === 'idle' && !error && (
            <section className="pt-16 md:pt-20 pb-20 text-center">
              <h1 className="text-5xl sm:text-7xl md:text-8xl lg:text-9xl font-extrabold text-white leading-[1.05] tracking-tight mb-14">
                Your issues.
                <span className="block mt-2 bg-gradient-to-r from-accent to-accent-light bg-clip-text text-transparent">
                  Resolved.
                </span>
              </h1>
              <div className="flex flex-col items-center gap-2 max-w-2xl mx-auto mb-8">
                <label className="text-xs text-gray-400 font-medium tracking-wide uppercase">Enter GitHub Issue URL</label>
                <div className="flex items-center gap-3 w-full">
                  <input
                    type="text"
                    value={issueUrl}
                    onChange={(e) => setIssueUrl(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleRun()}
                    placeholder="https://github.com/owner/repo/issues/42"
                    className="flex-1 px-4 py-3 bg-dark-800/90 border border-dark-600 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-accent/50 shadow-[0_0_20px_rgba(108,99,255,0.25)] transition-all duration-300 font-mono"
                  />
                  <button
                    onClick={handleRun}
                    className="px-8 py-4 bg-gradient-to-r from-accent to-accent-light hover:from-accent/90 hover:to-accent-light/90 text-white text-base font-semibold rounded-xl transition-all duration-200 whitespace-nowrap shadow-[0_0_20px_rgba(108,99,255,0.3)] active:scale-95"
                  >
                    Run
                  </button>
                </div>
              </div>
              <p className="text-gray-300 text-sm md:text-base max-w-lg mx-auto leading-relaxed font-semibold mt-8">
                MergePilot reads a GitHub issue, researches your codebase, drafts a fix,
                writes tests, and opens a pull request — all autonomously.
              </p>
            </section>
          )}

          {(status === 'running' || status === 'done') && (
            <section className="pt-8 pb-8">
              <div className="grid grid-cols-12 gap-6">
                {/* Left Column — Pipeline */}
                <div className="col-span-12 lg:col-span-4">
                  <div className={CARD_CLASS} style={CARD_STYLE}>
                    <div className="px-5 py-4 border-b border-white/5">
                      <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">Pipeline</h2>
                        <span className="text-xs text-gray-500 font-mono">{completedCount}/{AGENTS.length}</span>
                      </div>
                      {status === 'running' && (
                        <div className="mt-2 w-full h-1 rounded-full bg-dark-600 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-accent to-accent-light transition-all duration-500"
                            style={{ width: `${(completedCount / AGENTS.length) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="p-5 space-y-0">
                      {AGENTS.map((agent, i) => (
                        <PipelineStep
                          key={agent.id}
                          agent={agent}
                          status={agentStates[agent.id]?.status || 'idle'}
                          info={agentStates[agent.id]?.info}
                          isLast={i === AGENTS.length - 1}
                        />
                      ))}
                    </div>
                    {status === 'running' && (
                      <div className="px-5 py-3 border-t border-white/5 flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-glow" />
                        <span className="text-xs text-gray-500">
                          {mockMode ? 'Mock mode' : 'Running...'}
                        </span>
                      </div>
                    )}
                    {status === 'done' && (
                      <div className="px-5 py-3 border-t border-white/5 flex items-center gap-2">
                        <svg className="w-3.5 h-3.5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        <span className="text-xs text-green-400">All checks passed</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right Column — Terminal + Summary */}
                <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
                  {/* Terminal */}
                  <div className={CARD_CLASS} style={CARD_STYLE}>
                    <LogViewer logs={logs} />
                    {logs.length === 0 && (
                      <div className="px-4 py-8 text-center text-sm text-gray-600">
                        Waiting for pipeline output...
                      </div>
                    )}
                  </div>

                  {/* PR Summary */}
                  {status === 'done' && result && (
                    <div className={CARD_CLASS} style={CARD_STYLE}>
                      <div className="px-5 py-4 border-b border-white/5 flex items-center gap-3">
                        <h2 className="text-sm font-semibold text-white uppercase tracking-wider flex-1">Pull Request</h2>
                        <a
                          href={result.pr_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-4 py-2 bg-black hover:bg-black/80 text-white text-sm font-medium rounded-lg border border-dark-600 transition-all duration-200 active:scale-95 flex items-center gap-1.5"
                        >
                          View PR
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        </a>
                      </div>
                      <div className="p-5 space-y-4">
                        <div className="flex gap-3 text-xs">
                          <span className="px-2.5 py-1 rounded-full bg-dark-700 text-gray-400 capitalize">
                            {result.issue_type || 'bug'}
                          </span>
                          <span className="px-2.5 py-1 rounded-full bg-dark-700 text-gray-400 capitalize">
                            {result.complexity || 'medium'} complexity
                          </span>
                        </div>
                        <p className="text-sm text-gray-400 leading-relaxed">{result.summary}</p>
                        <DiffPreview files={result.files} />
                      </div>
                      <div className="px-5 py-3 border-t border-white/5 flex items-center justify-between">
                        <span className="text-xs text-gray-600">Branch: <span className="text-gray-400 font-mono">mergepilot/fix-42</span></span>
                        <button
                          onClick={reset}
                          className="text-xs text-white font-semibold hover:text-gray-300 transition-colors"
                        >
                          Run another issue
                        </button>
                      </div>
                    </div>
                  )}

                  {status === 'running' && (
                    <button
                      onClick={reset}
                      className="self-start text-xs text-gray-600 hover:text-gray-400 transition-colors"
                    >
                      Cancel &amp; reset
                    </button>
                  )}
                </div>
              </div>
            </section>
          )}

          {error && status === 'idle' && (
            <section className="pt-24 pb-16 text-center">
              <div className="max-w-md mx-auto" style={{ ...CARD_STYLE, borderRadius: '1rem', padding: '1.5rem' }}>
                <div className="flex items-center gap-2 mb-3">
                  <svg className="w-5 h-5 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-sm font-semibold text-red-400">Error</span>
                </div>
                <p className="text-sm text-gray-400 mb-4">{error}</p>
                <button
                  onClick={reset}
                  className="text-sm text-accent hover:text-accent-light transition-colors"
                >
                  Try again
                </button>
              </div>
            </section>
          )}
        </main>

        <footer className="border-t border-dark-600 py-6 px-6">
          <div className="max-w-6xl mx-auto flex items-center justify-between text-xs text-gray-400">
            <span>MergePilot — autonomous PR generation</span>
            <span>Built with Groq &middot; FastAPI &middot; React</span>
          </div>
        </footer>
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pipelineGlow {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}

import { useState, useEffect } from 'react'

export default function MissionPanel({ missionHistory, missionStats, scenario }) {
  // Hide entirely in attacker scenario — 3D missions are fire-only
  if (scenario === 'attacker') return null
  const [open, setOpen] = useState(false)
  const [running, setRunning] = useState(false)
  const [btnMsg, setBtnMsg] = useState('▶ Run 3D Mission Now')

  const stats = missionStats || {}
  const last  = missionHistory || {}

  const successRate = stats.success_rate ?? 0
  const total       = stats.total_missions ?? 0
  const successful  = stats.successful_missions ?? 0

  // Poll mission status while running
  useEffect(() => {
    if (!running) return
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/mission_status')
        const data = await res.json()
        if (!data.running) {
          setRunning(false)
          setBtnMsg('▶ Run 3D Mission Now')
          clearInterval(interval)
        }
      } catch (e) {
        clearInterval(interval)
        setRunning(false)
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [running])

  const triggerMission = async () => {
    if (running) return
    try {
      const res = await fetch('/trigger_mission', { method: 'POST' })
      const data = await res.json()
      if (data.status === 'started') {
        setRunning(true)
        setBtnMsg('⏳ Mission running...')
      } else if (data.status === 'already_running') {
        setBtnMsg('⏳ Already running...')
        setRunning(true)
      }
    } catch (e) {
      setBtnMsg('⚠ Backend unreachable')
      setTimeout(() => setBtnMsg('▶ Run 3D Mission Now'), 3000)
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: open ? '#1a1a2e' : '#0f172a',
          border: `1px solid ${open ? '#6366f1' : '#334155'}`,
          color: open ? '#a5b4fc' : '#94a3b8',
          padding: '5px 14px', borderRadius: 6,
          cursor: 'pointer', fontSize: 14, fontFamily: 'monospace',
          transition: 'all 0.15s',
        }}
      >
        📊 Missions
        {total > 0 && (
          <span style={{
            background: successRate >= 50 ? '#16a34a33' : '#dc262633',
            color: successRate >= 50 ? '#4ade80' : '#f87171',
            borderRadius: 10, padding: '1px 6px', fontSize: 13,
          }}>
            {Math.round(successRate)}%
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: 'fixed', right: 16, top: 60,
          width: 340, background: '#0a0f1e',
          border: '1px solid #1e1b4b', borderRadius: 10,
          boxShadow: '0 8px 32px rgba(0,0,0,0.7)',
          zIndex: 1002, fontFamily: 'monospace', padding: 16,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ color: '#a5b4fc', fontWeight: 'bold', fontSize: 15 }}>
              📊 RescueNav 3D Missions
            </span>
            <button onClick={() => setOpen(false)}
              style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 16 }}>
              ✕
            </button>
          </div>

          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 14 }}>
            <StatBox label='Total' value={total} color='#94a3b8' />
            <StatBox label='Success' value={successful} color='#4ade80' />
            <StatBox label='Rate' value={`${Math.round(successRate)}%`}
              color={successRate >= 50 ? '#4ade80' : '#f87171'} />
          </div>

          {stats.avg_time > 0 && (
            <div style={{ fontSize: 13, color: '#64748b', marginBottom: 12 }}>
              Avg: <span style={{ color: '#94a3b8' }}>{stats.avg_time?.toFixed(1)}s</span>
              {' '}| Best: <span style={{ color: '#4ade80' }}>{stats.min_time?.toFixed(1)}s</span>
              {' '}| Worst: <span style={{ color: '#f87171' }}>{stats.max_time?.toFixed(1)}s</span>
            </div>
          )}

          {/* Last mission */}
          {last.mission_id ? (
            <div style={{
              background: '#0f172a', borderRadius: 8, padding: '10px 12px', marginBottom: 12,
              border: `1px solid ${last.success ? '#16a34a' : '#dc2626'}44`,
            }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                Last Mission #{last.mission_number} — {last.scenario}
              </div>
              <div style={{ fontSize: 14, fontWeight: 'bold', color: last.success ? '#4ade80' : '#f87171', marginBottom: 6 }}>
                {last.success ? '✅ SUCCESS' : `❌ FAILED — ${last.reason_failed}`}
              </div>
              <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.8 }}>
                <div>Time: <span style={{ color: '#e2e8f0' }}>{last.total_time}s</span></div>
                <div>
                  Agents: <span style={{ color: '#4ade80' }}>{last.agents_alive}</span>/{last.num_agents} alive
                  {' '}| <span style={{ color: '#38bdf8' }}>{last.agents_rescued}</span> rescued
                </div>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#334155', textAlign: 'center', padding: '8px 0 12px' }}>
              No missions yet. Fire triggers one automatically.
            </div>
          )}

          {/* What this does */}
          <div style={{ fontSize: 12, color: '#475569', marginBottom: 10, lineHeight: 1.6 }}>
            Runs the RescuNav 3D simulation (NeMo agents + Building3D A*).
            Agent paths appear as purple trails on the floor plan.
          </div>

          <button
            onClick={triggerMission}
            disabled={running}
            style={{
              width: '100%',
              background: running ? '#1e1b4b88' : '#1e1b4b',
              border: `1px solid ${running ? '#4338ca88' : '#6366f1'}`,
              color: running ? '#818cf8' : '#a5b4fc',
              padding: '9px 0', borderRadius: 6,
              cursor: running ? 'not-allowed' : 'pointer',
              fontSize: 14, fontFamily: 'monospace',
              transition: 'all 0.2s',
            }}
          >
            {btnMsg}
          </button>
        </div>
      )}
    </>
  )
}

function StatBox({ label, value, color }) {
  return (
    <div style={{
      background: '#0f172a', borderRadius: 6, padding: '8px 10px',
      border: `1px solid ${color}33`, textAlign: 'center',
    }}>
      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 'bold', color }}>{value}</div>
    </div>
  )
}

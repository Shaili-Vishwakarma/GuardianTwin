import { useMemo, useState, useEffect, useCallback } from 'react'

const CELL = 28, GRID = 20, W = CELL * GRID, H = CELL * GRID
// Building occupies rows 0–14 (3 floors × 5 rows each), trim empty rows below
const VIEW_H = 15 * CELL  // exactly 15 rows tall, no empty space

const ZONE_REGIONS = {
  'F3-A': { r: 0,  c: 0  }, 'F3-B': { r: 0,  c: 5  },
  'F3-C': { r: 0,  c: 10 }, 'F3-D': { r: 0,  c: 15 },
  'F2-A': { r: 5,  c: 0  }, 'F2-B': { r: 5,  c: 5  },
  'F2-C': { r: 5,  c: 10 }, 'F2-D': { r: 5,  c: 15 },
  'F1-A': { r: 10, c: 0  }, 'F1-B': { r: 10, c: 5  },
  'F1-C': { r: 10, c: 10 }, 'F1-D': { r: 10, c: 15 },
}

const EXITS = [
  { x: 19, y: 2 },
  { x: 19, y: 7 },
  { x: 19, y: 12 },
]

// Lifts — one per zone column, at zone boundaries (col 4, 9, 14)
// Shown on each floor row boundary
const LIFTS = [
  { x: 4, y: 4,  label: 'L1' },
  { x: 9, y: 4,  label: 'L2' },
  { x: 4, y: 9,  label: 'L3' },
  { x: 9, y: 9,  label: 'L4' },
]

// Stairwells — at zone corners, spanning floor boundaries
const STAIRWELLS = [
  { x: 0,  y: 4,  label: 'S1' },
  { x: 14, y: 4,  label: 'S2' },
  { x: 0,  y: 9,  label: 'S3' },
  { x: 14, y: 9,  label: 'S4' },
]

function fireColor(p, suppressed, brigadeActive, extinguished) {
  if (extinguished || p < 0.02) return 'transparent'  // fully clear — no overlay
  if (brigadeActive) {
    return `rgba(251,146,60,${0.15 + p * 0.5})`       // orange fading as brigade fights
  }
  if (suppressed) {
    return `rgba(56,189,248,${0.10 + p * 0.35})`      // blue tint fading as sprinklers work
  }
  // Normal fire — red/orange, intensity tracks fire_prob
  const r = Math.round(255 * Math.min(1, p * 1.5))
  const g = Math.round(80  * Math.max(0, 1 - p * 1.8))
  return `rgba(${r},${g},0,${0.20 + p * 0.70})`
}

function zoneCenter(zone) {
  const reg = ZONE_REGIONS[zone]
  if (!reg) return null
  return { x: (reg.c + 2.5) * CELL, y: (reg.r + 2.5) * CELL }
}

export default function FloorPlan({ state }) {
  const hm            = state?.fire_heatmap       || {}
  const occ           = state?.occupant_positions || []
  const routes        = state?.safe_routes        || {}
  const fireOrigin    = state?.fire_origin_zone
  const threat        = state?.threat_level       || 'none'
  const rescueAgents  = state?.rescue_agents      || []
  const fireBrigade   = state?.fire_brigade       || []
  const brigadeZones  = state?.brigade_zones      || []
  const suppressionZones   = state?.suppression_active  || []
  const extinguishedZones  = state?.extinguished_zones  || []
  const unaccounted   = state?.unaccounted_count  ?? 0
  const elevatorsOff  = state?.elevators_recalled ?? false

  const routeLines = useMemo(() =>
    Object.entries(routes).flatMap(([pid, wps]) => {
      if (!wps || wps.length < 2) return []
      const points = wps.map(w =>
        `${w.grid_x * CELL + CELL / 2},${w.grid_y * CELL + CELL / 2}`
      ).join(' ')
      return [{ pid, points }]
    }),
  [routes])

  const fireOriginCenter = fireOrigin ? zoneCenter(fireOrigin) : null

  // Map person_id → rescue agent assigned to them
  const rescuerFor = useMemo(() => {
    const map = {}
    rescueAgents.forEach(a => { if (a.target) map[a.target] = a })
    return map
  }, [rescueAgents])
  const [maximized, setMaximized] = useState(false)
  const [tooltip, setTooltip] = useState(null) // { x, y, content: [...] }

  const showTip = useCallback((e, content) => {
    const rect = e.currentTarget.closest('svg').getBoundingClientRect()
    // Scale factor: SVG viewBox vs rendered size
    const scaleX = W / rect.width
    const scaleY = VIEW_H / rect.height
    const svgX = (e.clientX - rect.left) * scaleX
    const svgY = (e.clientY - rect.top)  * scaleY
    const TIP_W = 220, TIP_H = content.length * 22 + 16
    // Flip above cursor if near bottom, flip left if near right edge
    const x = svgX + TIP_W > W   ? svgX - TIP_W - 8 : svgX + 12
    const y = svgY + TIP_H > VIEW_H ? svgY - TIP_H - 8 : svgY - 8
    setTooltip({ x, y, content, tipW: TIP_W, tipH: TIP_H })
  }, [])
  const hideTip = useCallback(() => setTooltip(null), [])

  // Close fullscreen on Escape
  useEffect(() => {
    const handler = e => { if (e.key === 'Escape') setMaximized(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const containerStyle = maximized ? {
    position: 'fixed', inset: 0, zIndex: 999,
    background: '#020617',
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    padding: 24,
  } : {
    width: '100%', height: '100%',
    display: 'flex', flexDirection: 'column',
  }

  return (
    <div style={containerStyle}>
      {/* Top bar: legend + maximize button */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
        {/* Legend */}
        <div style={{ display: 'flex', gap: 12, fontSize: 12, color: '#64748b', flexWrap: 'wrap' }}>
          <span><span style={{ color: '#ef4444' }}>●</span> Trapped</span>
          <span><span style={{ color: '#22c55e' }}>●</span> Safe</span>
          <span><span style={{ color: '#f59e0b' }}>●</span> Unknown</span>
          <span><span style={{ color: '#ff6600' }}>🔥</span> Fire origin</span>
          <span><span style={{ color: '#22c55e' }}>▬</span> Evac route</span>
          <span><span style={{ color: '#a78bfa' }}>◆</span> Rescue agent</span>
          <span>
            <span style={{ color: elevatorsOff ? '#ef4444' : '#22c55e' }}>▣</span>
            {' '}Lift {elevatorsOff ? '(OFF)' : '(ON)'}
          </span>
          <span><span style={{ color: '#60a5fa' }}>⊞</span> Stairwell</span>
          <span><span style={{ color: '#f43f5e' }}>◆</span> Fire Brigade</span>
          <span><span style={{ color: '#38bdf8' }}>~</span> Sprinklers</span>
          <span><span style={{ color: '#64748b' }}>✅</span> Cleared</span>
          {unaccounted > 0 && (
            <span style={{ color: '#ef4444', fontWeight: 'bold' }}>⚠ {unaccounted} UNACCOUNTED</span>
          )}
        </div>

        {/* Maximize button */}
        <button
          onClick={() => setMaximized(m => !m)}
          title={maximized ? 'Restore' : 'Fullscreen map'}
          style={{
            marginLeft: 12, flexShrink: 0,
            background: '#1e293b', border: '1px solid #334155',
            color: '#94a3b8', borderRadius: 6,
            width: 28, height: 28, cursor: 'pointer',
            fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          {maximized ? '✕' : '⤢'}
        </button>
      </div>

      <svg
        viewBox={`0 0 ${W} ${VIEW_H}`}
        style={maximized
          ? { flex: 1, width: '100%', maxHeight: 'calc(100vh - 80px)' }
          : { display: 'block', width: '100%', height: '100%', flex: 1, minHeight: 0 }
        }
        preserveAspectRatio='xMidYMid meet'
      >
        {/* Grid lines — only within active building area */}
        {Array.from({ length: GRID + 1 }).map((_, i) => (
          <g key={i}>
            <line x1={i * CELL} y1={0} x2={i * CELL} y2={VIEW_H} stroke='#1e293b' strokeWidth={0.5} />
            {i <= 15 && <line x1={0} y1={i * CELL} x2={W} y2={i * CELL} stroke='#1e293b' strokeWidth={0.5} />}
          </g>
        ))}

        {/* Zone borders + labels */}
        {Object.entries(ZONE_REGIONS).map(([zone, { r, c }]) => (
          <g key={zone}>
            <rect x={c * CELL} y={r * CELL} width={5 * CELL} height={5 * CELL}
              fill='none' stroke='#334155' strokeWidth={1} />
            <text x={c * CELL + 4} y={r * CELL + 13}
              fill='#475569' fontSize={11} fontFamily='monospace'>{zone}</text>
          </g>
        ))}

        {/* Floor dividers — thick lines between floors */}
        {[5, 10].map(row => (
          <line key={row} x1={0} y1={row * CELL} x2={W} y2={row * CELL}
            stroke='#475569' strokeWidth={2} />
        ))}

        {/* Floor labels on left */}
        {[
          { label: 'FLOOR 3', y: 2.5 },
          { label: 'FLOOR 2', y: 7.5 },
          { label: 'FLOOR 1', y: 12.5 },
        ].map(({ label, y }) => (
          <text key={label} x={2} y={y * CELL}
            fill='#334155' fontSize={9} fontFamily='monospace'
            transform={`rotate(-90, 2, ${y * CELL})`}>{label}</text>
        ))}

        {/* Fire heatmap overlay */}
        {Object.entries(hm).map(([zone, data]) => {
          const reg = ZONE_REGIONS[zone]
          if (!reg) return null
          const isSuppressed   = data.suppressed    || suppressionZones.includes(zone)
          const isBrigade      = data.brigade_active || brigadeZones.includes(zone)
          const isExtinguished = data.extinguished   || extinguishedZones.includes(zone)
          const color = fireColor(data.fire_prob, isSuppressed, isBrigade, isExtinguished)
          if (color === 'transparent') return null
          return (
            <rect key={zone}
              x={reg.c * CELL} y={reg.r * CELL}
              width={5 * CELL} height={5 * CELL}
              fill={color} rx={2} />
          )
        })}

        {/* Sprinkler icon overlay — shown on suppressed zones with active fire */}
        {suppressionZones
          .filter(z => !extinguishedZones.includes(z) && (hm[z]?.fire_prob ?? 0) > 0.05)
          .map(zone => {
          const reg = ZONE_REGIONS[zone]
          if (!reg) return null
          return (
            <text key={`spr-${zone}`}
              x={(reg.c + 2.5) * CELL} y={(reg.r + 4.5) * CELL}
              textAnchor='middle' fontSize={14}>💧</text>
          )
        })}

        {/* Stairwells — blue cross pattern */}
        {STAIRWELLS.map(s => {
          const sx = s.x * CELL + 1
          const sy = s.y * CELL + 1
          const sw = CELL - 2
          const sh = CELL - 2
          return (
            <g key={s.label} style={{ cursor: 'pointer' }}
              onMouseMove={e => showTip(e, [
                { text: `Stairwell ${s.label}`, bold: true, color: '#60a5fa' },
                { text: 'Status: OPEN', color: '#22c55e' },
                { text: 'Use for evacuation', color: '#94a3b8' },
              ])}
              onMouseLeave={hideTip}>
              <rect x={sx} y={sy} width={sw} height={sh}
                fill='#1e3a5f' stroke='#60a5fa' strokeWidth={1.5} rx={2} />
              <line x1={sx + sw * 0.2} y1={sy + sh / 2} x2={sx + sw * 0.8} y2={sy + sh / 2}
                stroke='#60a5fa' strokeWidth={1.5} />
              <line x1={sx + sw / 2} y1={sy + sh * 0.2} x2={sx + sw / 2} y2={sy + sh * 0.8}
                stroke='#60a5fa' strokeWidth={1.5} />
              <text x={sx + sw / 2} y={sy + sh + 11}
                textAnchor='middle' fill='#60a5fa' fontSize={9}>{s.label}</text>
            </g>
          )
        })}

        {/* Lifts — recalled/off shown in red, normal in gray */}
        {LIFTS.map(l => {
          const lx = l.x * CELL + 1
          const ly = l.y * CELL + 1
          const lw = CELL - 2
          const lh = CELL - 2
          const liftColor = elevatorsOff ? '#ef4444' : '#94a3b8'
          const liftBg    = elevatorsOff ? '#2d0a0a' : '#1e293b'
          return (
            <g key={l.label} style={{ cursor: 'pointer' }}
              onMouseMove={e => showTip(e, [
                { text: `Lift ${l.label}`, bold: true, color: liftColor },
                { text: elevatorsOff ? '⚠ RECALLED — DO NOT USE' : 'Status: Operational', color: liftColor },
                { text: elevatorsOff ? 'Use stairwells for evacuation' : 'Available', color: '#94a3b8' },
              ])}
              onMouseLeave={hideTip}>
              <rect x={lx} y={ly} width={lw} height={lh}
                fill={liftBg} stroke={liftColor} strokeWidth={1.5} rx={2} />
              <line x1={lx + lw / 2} y1={ly + 2} x2={lx + lw / 2} y2={ly + lh - 2}
                stroke={liftColor} strokeWidth={1} />
              <text x={lx + lw / 2} y={ly + lh / 2 + 4}
                textAnchor='middle' fill={liftColor} fontSize={11}>
                {elevatorsOff ? '✕' : '⇕'}
              </text>
              <text x={lx + lw / 2} y={ly + lh + 11}
                textAnchor='middle' fill={liftColor} fontSize={9}>{l.label}</text>
              {elevatorsOff && (
                <text x={lx + lw / 2} y={ly - 2}
                  textAnchor='middle' fill='#ef4444' fontSize={8} fontWeight='bold'>OFF</text>
              )}
            </g>
          )
        })}

        {/* Evacuation routes */}
        {routeLines.map(({ pid, points }) => (
          <polyline key={pid} points={points}
            fill='none' stroke='#22c55e' strokeWidth={2}
            strokeDasharray='5 3' opacity={0.85} />
        ))}

        {/* Exit markers */}
        {EXITS.map((e, i) => (
          <g key={i}>
            <rect x={e.x * CELL + 2} y={e.y * CELL + 2}
              width={CELL - 4} height={CELL - 4}
              fill='#22c55e' opacity={0.9} rx={3} />
            <text x={e.x * CELL + CELL / 2} y={e.y * CELL + CELL / 2 + 4}
              textAnchor='middle' fill='white' fontSize={9} fontWeight='bold'>EXIT</text>
          </g>
        ))}

        {/* Fire origin — pulsing (hidden once extinguished or all clear) */}
        {fireOriginCenter
          && threat !== 'none'
          && !extinguishedZones.includes(fireOrigin)
          && (hm[fireOrigin]?.fire_prob ?? 0) > 0.05
          && (
          <g>
            <circle cx={fireOriginCenter.x} cy={fireOriginCenter.y} r={22} fill='#ff6600' opacity={0.15}>
              <animate attributeName='r' values='18;28;18' dur='1.2s' repeatCount='indefinite' />
              <animate attributeName='opacity' values='0.15;0.35;0.15' dur='1.2s' repeatCount='indefinite' />
            </circle>
            <text x={fireOriginCenter.x} y={fireOriginCenter.y + 6}
              textAnchor='middle' fontSize={20}>🔥</text>
            <text x={fireOriginCenter.x} y={fireOriginCenter.y + 22}
              textAnchor='middle' fontSize={11} fill='#ff6600' fontWeight='bold'>ORIGIN</text>
          </g>
        )}

        {/* Occupant dots */}
        {occ.map(o => {
          const cx = o.grid_x * CELL + CELL / 2
          const cy = o.grid_y * CELL + CELL / 2
          const color = o.status === 'at_risk' ? '#ef4444'
                      : o.status === 'safe'    ? '#22c55e' : '#f59e0b'
          const assignedRescuer = rescuerFor[o.person_id]
          return (
            <g key={o.person_id} style={{ cursor: 'pointer' }}
              onMouseMove={e => {
                const tips = [
                  { text: `Person ${o.person_id}`, bold: true, color },
                  { text: `Zone: ${o.zone}  |  Floor ${o.floor}`, color: '#94a3b8' },
                  { text: `Status: ${o.status.replace('_', ' ').toUpperCase()}`, color },
                  { text: `Danger level: ${o.danger_level || 'unknown'}`, color: o.danger_level === 'high' || o.danger_level === 'critical' ? '#ef4444' : '#f59e0b' },
                ]
                if (assignedRescuer) {
                  tips.push({ text: `Rescuer: ${assignedRescuer.id} (${assignedRescuer.status})`, color: assignedRescuer.color })
                  const trail = assignedRescuer.path_history || []
                  if (trail.length > 0) {
                    const last = trail[trail.length - 1]
                    tips.push({ text: `Rescuer at grid (${last.grid_x}, ${last.grid_y})`, color: '#64748b' })
                  }
                } else if (o.status === 'at_risk') {
                  tips.push({ text: 'No rescuer assigned yet', color: '#64748b' })
                }
                showTip(e, tips)
              }}
              onMouseLeave={hideTip}>
              {o.status === 'at_risk' && (
                <circle cx={cx} cy={cy} r={12} fill='none' stroke='#ef4444' strokeWidth={1.5} opacity={0.6}>
                  <animate attributeName='r' values='10;16;10' dur='1s' repeatCount='indefinite' />
                  <animate attributeName='opacity' values='0.6;0;0.6' dur='1s' repeatCount='indefinite' />
                </circle>
              )}
              <circle cx={cx} cy={cy} r={10} fill={color} opacity={0.95} />
              <text x={cx} y={cy + 4} textAnchor='middle' fill='white' fontSize={8} fontWeight='bold'>
                {o.person_id}
              </text>
            </g>
          )
        })}

        {/* Rescue agent trails */}
        {rescueAgents.map(agent => {
          const trail = agent.path_history || []
          if (trail.length < 2) return null
          const pts = trail.map(p =>
            `${p.grid_x * CELL + CELL / 2},${p.grid_y * CELL + CELL / 2}`
          ).join(' ')
          return (
            <polyline key={`trail-${agent.id}`} points={pts}
              fill='none' stroke={agent.color} strokeWidth={2}
              strokeDasharray='3 2' opacity={0.45} />
          )
        })}

        {/* Rescue agents — diamond */}
        {rescueAgents.map(agent => {
          if (agent.status === 'standby') return null
          const cx = agent.grid_x * CELL + CELL / 2
          const cy = agent.grid_y * CELL + CELL / 2
          const trail = agent.path_history || []
          const pathStr = trail.length > 1
            ? `(${trail[0].grid_x},${trail[0].grid_y}) → ... → (${trail[trail.length-1].grid_x},${trail[trail.length-1].grid_y})`
            : 'starting'
          return (
            <g key={agent.id} style={{ cursor: 'pointer' }}
              onMouseMove={e => showTip(e, [
                { text: `Rescue Agent ${agent.id}`, bold: true, color: agent.color },
                { text: `Status: ${agent.status.toUpperCase()}`, color: agent.color },
                { text: `Target: ${agent.target || 'none'}`, color: '#e2e8f0' },
                { text: `Group: ${(agent.group || []).join(', ') || '—'}`, color: '#e2e8f0' },
                { text: `Position: grid (${agent.grid_x}, ${agent.grid_y})`, color: '#94a3b8' },
                { text: `Path: ${pathStr}`, color: '#64748b' },
                { text: `Steps taken: ${trail.length}`, color: '#64748b' },
              ])}
              onMouseLeave={hideTip}>
              {agent.status === 'on_scene' && (
                <circle cx={cx} cy={cy} r={14} fill={agent.color} opacity={0.2}>
                  <animate attributeName='r' values='12;20;12' dur='0.8s' repeatCount='indefinite' />
                </circle>
              )}
              <polygon points={`${cx},${cy-11} ${cx+9},${cy} ${cx},${cy+11} ${cx-9},${cy}`}
                fill={agent.color} opacity={0.95} />
              <text x={cx} y={cy + 4} textAnchor='middle' fill='white' fontSize={8} fontWeight='bold'>
                {agent.id}
              </text>
              <text x={cx} y={cy - 15} textAnchor='middle' fill={agent.color} fontSize={10}>
                {agent.status === 'on_scene'   ? '🚑'
               : agent.status === 'escorting'  ? `🤝×${(agent.group||[]).length}`
               : `→${agent.target || ''}`}
              </text>
            </g>
          )
        })}
        {/* Fire Brigade trails */}
        {fireBrigade.map(unit => {
          const trail = unit.path_history || []
          if (trail.length < 2) return null
          const pts = trail.map(p =>
            `${p.grid_x * CELL + CELL / 2},${p.grid_y * CELL + CELL / 2}`
          ).join(' ')
          return (
            <polyline key={`fb-trail-${unit.id}`} points={pts}
              fill='none' stroke={unit.color} strokeWidth={2}
              strokeDasharray='3 2' opacity={0.4} />
          )
        })}

        {/* Fire Brigade units — red square */}
        {fireBrigade.map(unit => {
          if (unit.status === 'standby') return null
          const cx = unit.grid_x * CELL + CELL / 2
          const cy = unit.grid_y * CELL + CELL / 2
          const sz = 10
          return (
            <g key={unit.id} style={{ cursor: 'pointer' }}
              onMouseMove={e => showTip(e, [
                { text: `Fire Brigade ${unit.id}`, bold: true, color: unit.color },
                { text: `Status: ${unit.status.toUpperCase()}`, color: unit.color },
                { text: unit.status === 'returning' ? 'Returning to base' : `Target zone: ${unit.target_zone || '—'}`, color: '#e2e8f0' },
                { text: `Fight cycles: ${unit.fight_cycles || 0}`, color: '#94a3b8' },
                { text: `Position: grid (${unit.grid_x}, ${unit.grid_y})`, color: '#64748b' },
              ])}
              onMouseLeave={hideTip}>
              {unit.status === 'fighting' && (
                <circle cx={cx} cy={cy} r={14} fill={unit.color} opacity={0.2}>
                  <animate attributeName='r' values='12;20;12' dur='0.6s' repeatCount='indefinite' />
                </circle>
              )}
              <rect x={cx - sz} y={cy - sz} width={sz * 2} height={sz * 2}
                fill={unit.color} rx={2} opacity={0.95} />
              <text x={cx} y={cy + 4} textAnchor='middle' fill='white' fontSize={8} fontWeight='bold'>
                {unit.id}
              </text>
              <text x={cx} y={cy - 15} textAnchor='middle' fill={unit.color} fontSize={11}>
                {unit.status === 'fighting'   ? '🚒'
               : unit.status === 'returning'  ? '↩ base'
               : '→🔥'}
              </text>
            </g>
          )
        })}

        {/* Tooltip */}
        {tooltip && (
          <foreignObject
            x={tooltip.x} y={tooltip.y}
            width={tooltip.tipW} height={tooltip.tipH}
            style={{ pointerEvents: 'none' }}>
            <div style={{
              background: '#0f172a', border: '1px solid #475569',
              borderRadius: 8, padding: '8px 12px',
              fontSize: 13, fontFamily: 'monospace',
              boxShadow: '0 4px 20px rgba(0,0,0,0.8)',
            }}>
              {tooltip.content.map((line, i) => (
                <div key={i} style={{
                  color: line.color || '#94a3b8',
                  fontWeight: line.bold ? 'bold' : 'normal',
                  marginBottom: 3,
                  whiteSpace: 'nowrap',
                }}>
                  {line.text}
                </div>
              ))}
            </div>
          </foreignObject>
        )}
      </svg>
    </div>
  )
}

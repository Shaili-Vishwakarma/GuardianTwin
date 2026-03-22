import { useMemo } from 'react'

const CELL = 24, GRID = 20, W = 480, H = 480

const ZONE_REGIONS = {
  'F3-A': { r: 0,  c: 0  }, 'F3-B': { r: 0,  c: 5  },
  'F3-C': { r: 0,  c: 10 }, 'F3-D': { r: 0,  c: 15 },
  'F2-A': { r: 5,  c: 0  }, 'F2-B': { r: 5,  c: 5  },
  'F2-C': { r: 5,  c: 10 }, 'F2-D': { r: 5,  c: 15 },
  'F1-A': { r: 10, c: 0  }, 'F1-B': { r: 10, c: 5  },
  'F1-C': { r: 10, c: 10 }, 'F1-D': { r: 10, c: 15 },
}

function fireColor(p) {
  if (p < 0.05) return 'transparent'
  const r = Math.round(255 * Math.min(1, p * 2))
  const g = Math.round(255 * Math.max(0, 1 - p * 2))
  return `rgba(${r},${g},0,${0.3 + p * 0.5})`
}

export default function FloorPlan({ state }) {
  const hm     = state?.fire_heatmap       || {}
  const occ    = state?.occupant_positions || []
  const routes = state?.safe_routes        || {}

  const routeLines = useMemo(() =>
    Object.entries(routes).map(([pid, wps]) => ({
      pid,
      points: wps.map(w => `${w.grid_x * CELL + CELL / 2},${w.grid_y * CELL + CELL / 2}`).join(' '),
    })),
  [routes])

  return (
    <div style={{ background: '#0f172a', borderRadius: 12, padding: 16, display: 'inline-block' }}>
      <svg width={W} height={H} style={{ display: 'block' }}>
        {/* Grid lines */}
        {Array.from({ length: GRID + 1 }).map((_, i) => (
          <g key={i}>
            <line x1={i * CELL} y1={0} x2={i * CELL} y2={H} stroke='#1e293b' strokeWidth={0.5} />
            <line x1={0} y1={i * CELL} x2={W} y2={i * CELL} stroke='#1e293b' strokeWidth={0.5} />
          </g>
        ))}

        {/* Zone labels */}
        {Object.entries(ZONE_REGIONS).map(([zone, { r, c }]) => (
          <text key={zone} x={c * CELL + 4} y={r * CELL + 14}
            fill='#475569' fontSize={10} fontFamily='monospace'>{zone}</text>
        ))}

        {/* Fire heatmap overlay */}
        {Object.entries(hm).map(([zone, data]) => {
          const reg = ZONE_REGIONS[zone]
          if (!reg) return null
          return (
            <rect key={zone}
              x={reg.c * CELL} y={reg.r * CELL}
              width={5 * CELL} height={5 * CELL}
              fill={fireColor(data.fire_prob)} rx={4} />
          )
        })}

        {/* Evacuation routes */}
        {routeLines.map(({ pid, points }) => (
          <polyline key={pid} points={points}
            fill='none' stroke='#22c55e' strokeWidth={2}
            strokeDasharray='4 2' opacity={0.8} />
        ))}

        {/* Exit markers */}
        {[[19, 0], [19, 5], [19, 10], [19, 15]].map(([r, c], i) => (
          <rect key={i}
            x={c * CELL + 2} y={r * CELL + 2}
            width={CELL - 4} height={CELL - 4}
            fill='#22c55e' opacity={0.8} rx={3} />
        ))}

        {/* Occupant dots */}
        {occ.map(o => {
          const cx = o.grid_x * CELL + CELL / 2
          const cy = o.grid_y * CELL + CELL / 2
          const color = o.status === 'at_risk' ? '#ef4444'
                      : o.status === 'safe'    ? '#22c55e'
                      : '#f59e0b'
          return (
            <g key={o.person_id}>
              <circle cx={cx} cy={cy} r={8} fill={color} opacity={0.9} />
              <text x={cx} y={cy + 4} textAnchor='middle'
                fill='white' fontSize={8} fontWeight='bold'>
                {o.person_id}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

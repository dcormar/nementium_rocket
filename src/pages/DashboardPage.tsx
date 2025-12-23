import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchWithAuth } from '../utils/fetchWithAuth'

type MesResumen = {
  anio: number
  mes: number
  ventas_mes: number
  gastos_mes: number
  facturas_trimestre: number
}

/** Histórico: factura individual o ingresos agregados por día */
type Operacion = {
  tipo: 'FACTURA' | 'INGRESOS'
  fecha: string            // ISO date
  descripcion: string
  importe_eur: number
}

export default function DashboardPage({ token, onLogout }: { token: string; onLogout?: () => void }) {
  const [resumen, setResumen] = useState<MesResumen[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 🟢 nuevo: estado para histórico
  const [ops, setOps] = useState<Operacion[]>([])
  const [opsError, setOpsError] = useState<string | null>(null)

  useEffect(() => {
    fetchWithAuth('http://localhost:8000/dashboard/', {
      token,
      onLogout,
    })
      .then(r => (r.ok ? r.json() : Promise.reject('Error cargando dashboard')))
      .then(data => setResumen(data.ultimos_seis_meses || []))
      .catch(e => setError(typeof e === 'string' ? e : 'Error desconocido'))
      .finally(() => setLoading(false))
  }, [token, onLogout])

  // 🟢 nuevo: cargar histórico (independiente del dashboard)
  useEffect(() => {
    fetchWithAuth('http://localhost:8000/dashboard/historico?limit=10', {
      //cambiar limite a 60 dias en prod
      token,
      onLogout,
    })
      .then(r => (r.ok ? r.json() : Promise.reject('Error cargando histórico')))
      .then(data => setOps(data.items || []))
      .catch(e => setOpsError(typeof e === 'string' ? e : 'Error desconocido'))
  }, [token, onLogout])

  function pad(n: number) {
    return n < 10 ? `0${n}` : n
  }

  // 👇 Hook SIEMPRE declarado (antes de cualquier return)
  const chartData = useMemo(() => {
    const labels = resumen.map(m => `${pad(m.mes)}/${m.anio}`)
    const ventas = resumen.map(m => m.ventas_mes || 0)
    const gastos = resumen.map(m => m.gastos_mes || 0)
    const maxValue = Math.max(1, ...ventas, ...gastos)
    return { labels, ventas, gastos, maxValue }
  }, [resumen])

  // 👇 returns después de registrar todos los hooks
  if (loading) return <div>Cargando...</div>
  if (error) return <div style={{ color: 'red' }}>{error}</div>

  return (
    <div style={{ width: '100%', padding: '2rem' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr',
          gap: '2rem',
          alignItems: 'stretch',
        }}
      >
        {/* Columna izquierda: tarjetas */}
        <section
          style={{
            background: '#fff',
            borderRadius: 12,
            boxShadow: '0 8px 20px #0001',
            padding: '1.5rem',
          }}
        >
          <h2 style={{ margin: '0 0 1.5rem', color: '#163a63' }}>
            Resumen últimos 6 meses
          </h2>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '1.5rem',
            }}
          >
            {resumen.map((mes) => (
              <div
                key={mes.anio + '-' + mes.mes}
                style={{
                  background: '#f6f8fa',
                  borderRadius: 8,
                  boxShadow: '0 1px 6px #0001',
                  padding: '1.2rem 1rem',
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    fontWeight: 600,
                    fontSize: '1.15em',
                    color: '#1a2a4a',
                    marginBottom: 8,
                    textAlign: 'center',
                  }}
                >
                  {pad(mes.mes)}/{mes.anio}
                </div>
                <div style={{ marginBottom: 6, color: '#222', whiteSpace: 'nowrap'  }}>
                  <span style={{ fontWeight: 500 }}>Ventas:</span>{' '}
                  <span style={{ fontWeight: 600 }}>
                    {mes.ventas_mes.toLocaleString('es-ES', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}{' '}
                    €
                  </span>
                </div>
                <div style={{ marginBottom: 6, color: '#222', whiteSpace: 'nowrap'  }}>
                  <span style={{ fontWeight: 500 }}>Gastos:</span>{' '}
                  <span style={{ fontWeight: 600 }}>
                    {mes.gastos_mes.toLocaleString('es-ES', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}{' '}
                    €
                  </span>
                </div>
                <div style={{ marginBottom: 6, color: '#222', whiteSpace: 'nowrap' }}>
                  <span style={{ fontWeight: 500 }}>Facturas subidas:</span>{' '}
                  <span style={{ fontWeight: 600 }}>{mes.facturas_trimestre}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Columna derecha: gráfica */}
        <section
          style={{
            background: '#fff',
            borderRadius: 12,
            boxShadow: '0 8px 20px #0001',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <h3 style={{ margin: '0 0 1rem', color: '#163a63' }}>
            Gráfica Ventas vs. Gastos
          </h3>

          <Legend />

          {/* ocupa todo el alto disponible sin crecer en bucle */}
          <div style={{ flex: 1, minHeight: 0 }}>
            <BarsChart
              labels={chartData.labels}
              seriesA={chartData.ventas}
              seriesB={chartData.gastos}
              maxValue={chartData.maxValue}
              /* sin height fijo, lo medimos dentro */
            />
          </div>
        </section>
      </div>

      {/* ========= Histórico de operaciones ========= */}
      <section
        style={{
          background: '#fff',
          borderRadius: 12,
          boxShadow: '0 8px 20px #0001',
          padding: '1.5rem',
          marginTop: '2rem'
        }}
      >
        <h3 style={{ margin: 0, color: '#163a63' }}>Histórico de operaciones</h3>
        <p style={{ margin: '0.25rem 0 1rem', color: '#5b667a' }}>
          Facturas (individual) e ingresos (agregados por día)
        </p>

        {opsError && (
          <div style={{ color: 'red', marginBottom: '0.75rem' }}>{opsError}</div>
        )}

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0 }}>
            <thead>
              <tr style={{ background: '#f6f8fa', color: '#163a63' }}>
                <th style={{ textAlign: "center" }}>Fecha</th>
                <th style={{ ...th, textAlign: 'center' }}>Tipo</th>
                <th style={{...th, textAlign: "center" }}>Descripción</th>
                <th style={{ ...th, textAlign: 'right' }}>Importe (€)</th>
              </tr>
            </thead>
            <tbody>
              {ops.map((op, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #eef2f7' }}>
                  <td style={td}>{new Date(op.fecha).toLocaleDateString('es-ES')}</td>
                  <td style={td}>
                    <span style={{
                      fontSize: 12,
                      padding: '2px 8px',
                      borderRadius: 999,
                      background: op.tipo === 'FACTURA' ? '#eef2ff' : '#ecfdf5',
                      color: op.tipo === 'FACTURA' ? '#3730a3' : '#065f46',
                      fontWeight: 600
                    }}>
                      {op.tipo}
                    </span>
                  </td>
                  <td style={td}>{op.descripcion}</td>
                  <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>
                    {op.importe_eur.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                </tr>
              ))}

              {ops.length === 0 && !opsError && (
                <tr>
                  <td colSpan={4} style={{ ...td, textAlign: 'center', color: '#667085' }}>
                    Sin operaciones recientes.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )

}

/** Leyenda simple */
function Legend() {
  const item = (color: string, text: string) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: color }} />
      <span style={{ fontSize: 14, color: '#334' }}>{text}</span>
    </div>
  )
  return (
    <div style={{ display: 'flex', gap: '1.25rem', marginBottom: '0.75rem' }}>
      {item('#2563eb', 'Ventas')}
      {item('#16a34a', 'Gastos')}
    </div>
  )
}

/** Gráfica de barras (SVG) sin librerías externas */
function BarsChart({
  labels,
  seriesA,
  seriesB,
  maxValue,
  height, // opcional: si lo pasas, manda
}: {
  labels: string[]
  seriesA: number[]
  seriesB: number[]
  maxValue: number
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600) // ← solo ancho en estado

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const measure = () => {
      const w = Math.max(480, Math.round(el.clientWidth))
      setWidth(prev => (prev !== w ? w : prev))
    }
    measure()

    const ro = new ResizeObserver(() => measure())
    ro.observe(el)

    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])

  // Alto SIN estado (no provoca re-renders en bucle)
  const containerH = Math.max(260, Math.round(containerRef.current?.clientHeight ?? 300))
  const chartW = width
  const chartH = height ?? containerH

  const paddingX = 36
  const paddingTop = 12
  const paddingBottom = 28
  const innerW = chartW - paddingX * 2
  const innerH = chartH - paddingTop - paddingBottom

  const n = Math.max(1, labels.length)
  const groupW = innerW / n
  const barW = Math.max(10, (groupW - 12) / 2)
  const scaleY = (v: number) => innerH * (v / maxValue)
  const yBase = chartH - paddingBottom

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
      <svg width={chartW} height={chartH} role="img" aria-label="Barras ventas y gastos">
        {/* Ejes */}
        <line x1={paddingX} y1={yBase} x2={chartW - paddingX} y2={yBase} stroke="#e2e8f0" />
        <line x1={paddingX} y1={paddingTop} x2={paddingX} y2={yBase} stroke="#e2e8f0" />

        {/* Barras + etiquetas */}
        {labels.map((lb, i) => {
          const x0 = paddingX + i * groupW
          const hA = scaleY(seriesA[i] || 0)
          const hB = scaleY(seriesB[i] || 0)
          return (
            <g key={lb}>
              <rect x={x0 + 2} y={yBase - hA} width={barW} height={hA} rx={3} fill="#2563eb" opacity={0.9} />
              <rect x={x0 + 2 + barW + 6} y={yBase - hB} width={barW} height={hB} rx={3} fill="#16a34a" opacity={0.9} />
              <text x={x0 + groupW / 2} y={chartH - 8} textAnchor="middle" fontSize="11" fill="#64748b">
                {lb}
              </text>
            </g>
          )
        })}

        {/* Ticks horizontales */}
        {[0.25, 0.5, 0.75, 1].map((p) => {
          const y = yBase - innerH * p
          const val = maxValue * p
          return (
            <g key={p}>
              <line x1={paddingX} y1={y} x2={chartW - paddingX} y2={y} stroke="#eef2f7" />
              <text x={paddingX - 8} y={y + 4} textAnchor="end" fontSize="10" fill="#94a3b8">
                {val.toLocaleString('es-ES', { maximumFractionDigits: 0 })}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/* estilos tabla histórico */
const th: React.CSSProperties = { padding: '10px 12px', fontWeight: 700, textAlign: 'left', borderBottom: '1px solid #e5e7eb' }
const td: React.CSSProperties = { padding: '10px 12px', whiteSpace: 'nowrap' }
import { useState } from 'react'

function pad(n: number) {
  return n < 10 ? `0${n}` : n
}

type SortDirection = 'asc' | 'desc'
interface SortConfig {
  column: string
  direction: SortDirection
}

export default function MesDetallePage({ token }: { token: string }) {
  const today = new Date()
  const [anio, setAnio] = useState(today.getFullYear())
  const [mes, setMes] = useState(today.getMonth() + 1)
  // Día vacío por defecto
  const [dia, setDia] = useState<number | ''>('')

  const [ventas, setVentas] = useState<any[]>([])
  const [facturas, setFacturas] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Persiana
  const [showVentas, setShowVentas] = useState(true)
  const [showFacturas, setShowFacturas] = useState(true)

  // Filtros / columnas ventas
  const ventaCampos = ventas.length > 0
    ? Object.keys(ventas[0]).map(k => ({ key: k, label: k }))
    : []
  const [ventaFiltros, setVentaFiltros] = useState([{ campo: '', valor: '' }])
  const [columnasVisibles, setColumnasVisibles] = useState<string[]>([])
  const [showColumnPanel, setShowColumnPanel] = useState(false)

  // Ordenación facturas
  const [facturasSort, setFacturasSort] = useState<SortConfig | null>(null)

  const handleSortFacturas = (column: string) => {
    setFacturasSort(prev => {
      if (prev && prev.column === column) {
        // alterna asc/desc
        return { column, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
      }
      return { column, direction: 'asc' }
    })
  }

  const renderSortIndicator = (column: string) => {
    if (!facturasSort || facturasSort.column !== column) return ' ↕'
    return facturasSort.direction === 'asc' ? ' ▲' : ' ▼'
  }

  const parseFechaDDMMYYYY = (s: string) => {
    const [d, m, y] = s.split('/')
    const dd = Number(d)
    const mm = Number(m)
    const yy = Number(y)
    if (!dd || !mm || !yy) return 0
    return new Date(yy, mm - 1, dd).getTime()
  }

  const sortedFacturas = (() => {
    if (!facturasSort) return facturas
    const { column, direction } = facturasSort
    const factor = direction === 'asc' ? 1 : -1

    return [...facturas].sort((a, b) => {
      let va = a[column]
      let vb = b[column]

      // Nulls siempre al final
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1

      // Fecha dd/mm/yyyy
      if (column === 'fecha' && typeof va === 'string' && typeof vb === 'string') {
        const ta = parseFechaDDMMYYYY(va)
        const tb = parseFechaDDMMYYYY(vb)
        if (ta === tb) return 0
        return ta < tb ? -1 * factor : 1 * factor
      }

      // números
      if (typeof va === 'number' && typeof vb === 'number') {
        if (va === vb) return 0
        return va < vb ? -1 * factor : 1 * factor
      }

      // fallback string
      const sa = String(va)
      const sb = String(vb)
      return sa.localeCompare(sb, 'es') * factor
    })
  })()

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const mesStr = pad(mes)
      let desde = `${anio}-${mesStr}-01`
      let hasta = `${anio}-${mesStr}-${pad(new Date(anio, mes, 0).getDate())}`
      if (dia !== '') {
        const diaStr = pad(Number(dia))
        desde = `${anio}-${mesStr}-${diaStr}`
        hasta = desde
      }
      const ventasRes = await fetch(`http://localhost:8000/ventas?desde=${desde}&hasta=${hasta}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!ventasRes.ok) throw new Error('Error cargando ventas')
      const facturasRes = await fetch(`http://localhost:8000/facturas?desde=${desde}&hasta=${hasta}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!facturasRes.ok) throw new Error('Error cargando facturas')
      setVentas(await ventasRes.json())
      setFacturas(await facturasRes.json())
      // reset orden al recargar
      setFacturasSort(null)
    } catch (e: any) {
      setError(e.message || 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }

  // Estilo unificado: inputs, selects y button
  const fieldStyle: React.CSSProperties = {
    height: 36,
    padding: '4px 8px',
    borderRadius: 4,
    border: '1px solid #ced4da',
    boxSizing: 'border-box',
    margin: 0
  }

  const labelStyle: React.CSSProperties = {
    marginBottom: 4,
    fontWeight: 500,
    fontSize: '0.9rem'
  }
  return (
    <div className="mes-detalle-page">
      <h2>Ventas y facturas por fecha</h2>

      {/* Filtro fecha un poco más "tarjeta" */}
      <div
        style={{
          marginTop: '1rem',
          padding: '1rem 1.25rem',
          borderRadius: 8,
          border: '1px solid #d0d7de',
          background: '#f6f8fa'
        }}
      >
        <form
          onSubmit={e => { e.preventDefault(); fetchData() }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1.5rem',
            flexWrap: 'wrap',
            margin: 0,
            padding: 0
          }}
        >
          {/* Año */}
          <div style={{ display: 'flex', flexDirection: 'column', margin: 0 }}>
            <label style={labelStyle}>Año</label>
            <input
              type="number"
              value={anio}
              onChange={e => setAnio(Number(e.target.value))}
              min={2000}
              max={2100}
              style={{ ...fieldStyle, width: 90 }}
            />
          </div>

          {/* Mes */}
          <div style={{ display: 'flex', flexDirection: 'column', margin: 0 }}>
            <label style={labelStyle}>Mes</label>
            <select
              value={mes}
              onChange={e => setMes(Number(e.target.value))}
              style={{ ...fieldStyle, width: 120 }}
            >
              <option value={1}>Enero</option>
              <option value={2}>Febrero</option>
              <option value={3}>Marzo</option>
              <option value={4}>Abril</option>
              <option value={5}>Mayo</option>
              <option value={6}>Junio</option>
              <option value={7}>Julio</option>
              <option value={8}>Agosto</option>
              <option value={9}>Septiembre</option>
              <option value={10}>Octubre</option>
              <option value={11}>Noviembre</option>
              <option value={12}>Diciembre</option>
            </select>
          </div>

          {/* Día */}
          <div style={{ display: 'flex', flexDirection: 'column', margin: 0 }}>
            <label style={labelStyle}>Día (opcional)</label>
            <input
              type="number"
              value={dia}
              onChange={e => setDia(e.target.value === '' ? '' : Number(e.target.value))}
              min={1}
              max={31}
              placeholder="Todo el mes"
              style={{ ...fieldStyle, width: 120, minWidth: 120 }}
            />
          </div>

          {/* Botón */}
          <div style={{ display: 'flex', flexDirection: 'column', margin: 0 }}>
            <label style={{ ...labelStyle, visibility: 'hidden' }}>Acción</label>
            <button
              type="submit"
              style={{
                ...fieldStyle,
                minWidth: 80,
                border: '1px solid #0969da',
                background: '#0969da',
                color: 'white',
                cursor: 'pointer'
              }}
            >
              Ver
            </button>
          </div>
        </form>
        <div style={{ marginTop: '0.5rem', color: '#555', fontSize: '0.9em' }}>
          {dia === ''
            ? 'Sin día: se mostrarán los datos de todo el mes seleccionado.'
            : 'Se mostrarán los datos solo del día seleccionado.'
          }
        </div>
      </div>

      {loading && <div style={{ marginTop: '1.5rem' }}>Cargando...</div>}
      {error && <div style={{ color: 'red', marginTop: '1.5rem' }}>Error: {error}</div>}

      <div style={{ marginTop: '2.5rem' }}>
        {/* VENTAS */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <h3 style={{ margin: 0 }}>Ventas</h3>
          <button
            type="button"
            onClick={() => setShowVentas(v => !v)}
            style={{
              padding: '2px 10px',
              fontSize: '0.85rem',
              borderRadius: 4,
              border: '1px solid #b3c6e0',
              background: '#f6f8fa',
              cursor: 'pointer'
            }}
          >
            {showVentas ? 'Replegar ▲' : 'Desplegar ▼'}
          </button>
        </div>

        {showVentas && (
          <>
            {ventas.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-end',
                  gap: '1.5rem',
                  marginBottom: '1rem',
                  flexWrap: 'wrap',
                  justifyContent: 'space-between'
                }}
              >
                <div>
                  {ventaFiltros.map((filtro, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-end',
                        gap: '1rem',
                        marginBottom: idx < ventaFiltros.length - 1 ? '0.5rem' : 0
                      }}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                        <label style={{ marginBottom: 4 }}>Filtrar ventas por:</label>
                        <select
                          value={filtro.campo}
                          onChange={e => {
                            const nuevo = [...ventaFiltros]
                            nuevo[idx].campo = e.target.value
                            nuevo[idx].valor = ''
                            setVentaFiltros(nuevo)
                          }}
                          style={{ width: 140 }}
                        >
                          <option value="">(Selecciona campo)</option>
                          {ventaCampos.map(c => (
                            <option key={c.key} value={c.key}>{c.label}</option>
                          ))}
                        </select>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                        <label style={{ marginBottom: 4 }}>Valor:</label>
                        <select
                          value={filtro.valor}
                          onChange={e => {
                            const nuevo = [...ventaFiltros]
                            nuevo[idx].valor = e.target.value
                            setVentaFiltros(nuevo)
                          }}
                          style={{ width: 140 }}
                          disabled={!filtro.campo}
                        >
                          <option value="">Todos</option>
                          {filtro.campo && [...new Set(
                            ventas
                              .map(v => v[filtro.campo])
                              .filter(v => v !== undefined && v !== null)
                          )].map((v, i) => (
                            <option key={i} value={v}>{v}</option>
                          ))}
                        </select>
                      </div>
                      {idx === ventaFiltros.length - 1 && filtro.campo && (
                        <button
                          type="button"
                          style={{ marginLeft: 8 }}
                          onClick={() => setVentaFiltros([...ventaFiltros, { campo: '', valor: '' }])}
                        >
                          +
                        </button>
                      )}
                      {ventaFiltros.length > 1 && (
                        <button
                          type="button"
                          style={{ marginLeft: 8 }}
                          onClick={() => setVentaFiltros(ventaFiltros.filter((_, i) => i !== idx))}
                        >
                          -
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', marginLeft: 'auto' }}>
                  <button
                    type="button"
                    style={{
                      marginBottom: 4,
                      padding: '4px 12px',
                      borderRadius: 4,
                      border: '1px solid #b3c6e0',
                      background: '#f6f8fa',
                      cursor: 'pointer'
                    }}
                    onClick={() => setShowColumnPanel(v => !v)}
                  >
                    {showColumnPanel ? 'Ocultar columnas ▲' : 'Mostrar columnas ▼'}
                  </button>
                  {showColumnPanel && (
                    <div
                      style={{
                        border: '1px solid #b3c6e0',
                        borderRadius: 6,
                        background: '#fff',
                        boxShadow: '0 2px 8px #0001',
                        padding: '10px',
                        maxHeight: 180,
                        overflowY: 'auto',
                        minWidth: 180,
                        marginBottom: 4
                      }}
                    >
                      <label style={{ fontWeight: 600, marginBottom: 8, display: 'block' }}>
                        Columnas a mostrar:
                      </label>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        {ventaCampos.map(c => (
                          <label key={c.key} style={{ display: 'flex', alignItems: 'center', marginRight: 8 }}>
                            <input
                              type="checkbox"
                              checked={columnasVisibles.length === 0 || columnasVisibles.includes(c.key)}
                              onChange={e => {
                                let nuevas = columnasVisibles.length === 0
                                  ? ventaCampos.map(col => col.key)
                                  : [...columnasVisibles]
                                if (e.target.checked) {
                                  if (!nuevas.includes(c.key)) nuevas.push(c.key)
                                } else {
                                  nuevas = nuevas.filter(k => k !== c.key)
                                }
                                setColumnasVisibles(nuevas)
                              }}
                            />
                            {c.label}
                          </label>
                        ))}
                      </div>
                      <small style={{ color: '#555' }}>
                        Marca/desmarca para mostrar u ocultar columnas
                      </small>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div style={{ overflowX: 'auto' }}>
              <table style={{ whiteSpace: 'nowrap' }}>
                <thead>
                  <tr style={{ background: '#b3c6e0' }}>
                    {ventas.length > 0
                      ? (columnasVisibles.length ? columnasVisibles : Object.keys(ventas[0])).map((col) => (
                          <th key={col}>{col}</th>
                        ))
                      : <th>ID</th>
                    }
                  </tr>
                </thead>
                <tbody>
                  {ventas.length === 0 ? (
                    <tr>
                      <td
                        colSpan={1}
                        style={{ textAlign: 'center', color: '#888', background: '#f6f8fa' }}
                      >
                        No hay ventas registradas para el filtro seleccionado.
                      </td>
                    </tr>
                  ) : ventas
                    .filter(v =>
                      ventaFiltros.every(f =>
                        !f.campo || f.valor === '' || v[f.campo] === f.valor
                      )
                    )
                    .map((v, i) => (
                      <tr key={i}>
                        {(columnasVisibles.length ? columnasVisibles : Object.keys(ventas[0])).map((col) => (
                          <td key={col}>{v[col]}</td>
                        ))}
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* FACTURAS */}
        <div style={{ marginTop: '2.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <h3 style={{ margin: 0 }}>Facturas</h3>
          <button
            type="button"
            onClick={() => setShowFacturas(v => !v)}
            style={{
              padding: '2px 10px',
              fontSize: '0.85rem',
              borderRadius: 4,
              border: '1px solid #b3c6e0',
              background: '#f6f8fa',
              cursor: 'pointer'
            }}
          >
            {showFacturas ? 'Replegar ▲' : 'Desplegar ▼'}
          </button>
        </div>

        {showFacturas && (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr style={{ background: '#b3c6e0' }}>
                  <th
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSortFacturas('id')}
                  >
                    ID{renderSortIndicator('id')}
                  </th>
                  <th
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSortFacturas('proveedor')}
                  >
                    Proveedor{renderSortIndicator('proveedor')}
                  </th>
                  <th
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSortFacturas('fecha')}
                  >
                    Fecha{renderSortIndicator('fecha')}
                  </th>
                  <th
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSortFacturas('importe_total_euro')}
                  >
                    Total (€){renderSortIndicator('importe_total_euro')}
                  </th>
                  <th
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSortFacturas('importe_sin_iva_euro')}
                  >
                    Importe sin IVA (€){renderSortIndicator('importe_sin_iva_euro')}
                  </th>
                  <th
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleSortFacturas('pais_origen')}
                  >
                    País Origen{renderSortIndicator('pais_origen')}
                  </th>
                  <th>Factura</th>
                </tr>
              </thead>
              <tbody>
                {sortedFacturas.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      style={{ textAlign: 'center', color: '#888', background: '#f6f8fa' }}
                    >
                      No hay facturas registradas para el filtro seleccionado.
                    </td>
                  </tr>
                ) : sortedFacturas.map((f, i) => (
                  <tr key={i}>
                    <td>{f.id}</td>
                    <td>{f.proveedor}</td>
                    <td>{f.fecha}</td>
                    <td>{f.importe_total_euro}</td>
                    <td>{f.importe_sin_iva_euro}</td>
                    <td>{f.pais_origen}</td>
                    <td>
                      {f.ubicacion_factura ? (
                        <a
                          href={f.ubicacion_factura}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Ver
                        </a>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

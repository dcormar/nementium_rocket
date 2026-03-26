import { useState, useEffect, useMemo, useRef } from 'react'
import { fetchWithAuth } from '../utils/fetchWithAuth'

type Summary = {
  total_revenue: number
  total_units: number
  total_vat: number
  total_cogs: number
  total_amazon_fees: number
  total_dst: number
  total_ads_spend: number
  total_costs: number
  net_profit: number
  margin_pct: number
  roi: number
}

type BreakdownItem = {
  asin: string
  country: string
  title: string
  month?: string
  units: number
  revenue: number
  vat: number
  cogs: number
  amazon_referral_fee: number
  fba_fee: number
  other_costs: number
  dst: number
  ads_spend: number
  total_costs: number
  net_profit: number
  margin_pct: number
  profit_per_unit: number
  acos_real: number
  roi: number
}

type CogsItem = {
  ASIN: string
  SKU: string
  Title: string | null
  Cost: number | null
  amazon_referral_fee_pct: number | null
  fba_fee_es: number | null
  fba_fee_it: number | null
  fba_fee_de: number | null
  fba_fee_fr: number | null
  other_fixed_costs: number | null
  Marketplace: string | null
  categoria: string | null
}

type AnalysisResult = {
  summary: Summary
  breakdown: BreakdownItem[]
  warnings: string[]
}

type UploadResult = {
  ok: boolean
  conflict?: boolean
  message?: string
  filename: string
  total_rows: number
  inserted: number
  parse_errors: { row: number; error: string }[]
  insert_errors: { batch_start: number; error: string }[]
}

type AdsRecord = {
  id: number
  asin: string
  country: string
  country_code: string
  campaign_name: string
  ad_group_name: string
  fecha_inicio: string
  fecha_fin: string
  spend: number
  impressions: number
  clicks: number
  sales_7d: number
  acos: number
  roas: number
}

const EUR = (n: number) => n.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })
const PCT = (n: number) => `${n.toFixed(1)}%`

const COLORS = {
  revenue: '#22c55e',
  cogs: '#ef4444',
  amazonFees: '#f97316',
  ads: '#8b5cf6',
  profit: '#22c55e',
  loss: '#ef4444',
}

function Tip({ text }: { text: string }) {
  return (
    <span style={{ position: 'relative', display: 'inline-block', marginLeft: '6px' }} className="tip-wrap">
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: '16px', height: '16px', borderRadius: '50%', backgroundColor: '#e5e7eb',
        color: '#6b7280', fontSize: '11px', fontWeight: 700, cursor: 'help', verticalAlign: 'middle',
      }}>?</span>
      <span className="tip-text" style={{
        visibility: 'hidden', opacity: 0, position: 'absolute', bottom: 'calc(100% + 6px)', left: '50%',
        transform: 'translateX(-50%)', backgroundColor: '#1f2937', color: 'white', padding: '8px 12px',
        borderRadius: '8px', fontSize: '12px', lineHeight: '1.4', whiteSpace: 'pre-line',
        width: '260px', zIndex: 50, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        transition: 'opacity 0.15s',
      }}>{text}</span>
      <style>{`.tip-wrap:hover .tip-text { visibility: visible !important; opacity: 1 !important; }`}</style>
    </span>
  )
}

export default function RentabilidadPage({ token, onLogout }: { token: string; onLogout?: () => void }) {
  // --- State ---
  const [availableAsins, setAvailableAsins] = useState<string[]>([])
  const [availableCountries, setAvailableCountries] = useState<string[]>([])
  const [availableCategorias, setAvailableCategorias] = useState<string[]>([])
  const [selectedAsins, setSelectedAsins] = useState<string[]>([])
  const [selectedCountries, setSelectedCountries] = useState<string[]>([])
  const [selectedCategorias, setSelectedCategorias] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [groupBy, setGroupBy] = useState<'asin' | 'country' | 'asin_country' | 'month'>('asin')

  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [cogs, setCogs] = useState<CogsItem[]>([])
  const [showCogs, setShowCogs] = useState(false)
  const [editingCogs, setEditingCogs] = useState<string | null>(null)
  const [cogsForm, setCogsForm] = useState({ amazon_referral_fee_pct: '', fba_fee_es: '', fba_fee_it: '', fba_fee_de: '', fba_fee_fr: '', other_fixed_costs: '', cost: '', categoria: '' })
  const [cogsSaving, setCogsSaving] = useState(false)
  const [cogsSortCol, setCogsSortCol] = useState<string>('ASIN')
  const [cogsSortDir, setCogsSortDir] = useState<'asc' | 'desc'>('asc')
  const [confirmDelete, setConfirmDelete] = useState<{ asin: string; sku: string } | null>(null)
  const [modalMsg, setModalMsg] = useState<string | null>(null)

  const [showUpload, setShowUpload] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [showConflictConfirm, setShowConflictConfirm] = useState(false)

  const [showAds, setShowAds] = useState(false)
  const [adsData, setAdsData] = useState<AdsRecord[]>([])
  const [adsLoading, setAdsLoading] = useState(false)

  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [salesModal, setSalesModal] = useState<{ asin: string; rows: any[] } | null>(null)
  const [salesLoading, setSalesLoading] = useState(false)

  const [asinFilter, setAsinFilter] = useState('')
  const [countryFilter, setCountryFilter] = useState('')
  const [categoriaFilter, setCategoriaFilter] = useState('')
  const [showAsinDropdown, setShowAsinDropdown] = useState(false)
  const [showCountryDropdown, setShowCountryDropdown] = useState(false)
  const [showCategoriaDropdown, setShowCategoriaDropdown] = useState(false)

  const hasLoadedRef = useRef(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // --- Load initial data ---
  useEffect(() => {
    if (hasLoadedRef.current) return
    hasLoadedRef.current = true

    const opts = { token, onLogout }
    Promise.all([
      fetchWithAuth('/api/rentabilidad/asins', opts).then(r => r.ok ? r.json() : []),
      fetchWithAuth('/api/rentabilidad/countries', opts).then(r => r.ok ? r.json() : []),
      fetchWithAuth('/api/rentabilidad/cogs', opts).then(r => r.ok ? r.json() : []),
      fetchWithAuth('/api/rentabilidad/categorias', opts).then(r => r.ok ? r.json() : []),
    ]).then(([asins, countries, cogsData, categorias]) => {
      setAvailableAsins(asins)
      setAvailableCountries(countries)
      setCogs(cogsData)
      setAvailableCategorias(categorias)

      // Default dates: last 3 months
      const now = new Date()
      const threeMonthsAgo = new Date(now.getFullYear(), now.getMonth() - 3, 1)
      setDateFrom(threeMonthsAgo.toISOString().slice(0, 10))
      setDateTo(now.toISOString().slice(0, 10))
    })
  }, [token, onLogout])

  // --- Analyze ---
  const analyze = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const r = await fetchWithAuth('/api/rentabilidad/analyze', {
        token, onLogout,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asins: selectedAsins,
          date_from: dateFrom,
          date_to: dateTo,
          countries: selectedCountries,
          categorias: selectedCategorias,
          group_by: groupBy,
        }),
      })
      if (!r.ok) throw new Error(await r.text())
      setResult(await r.json())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }

  // --- Upload ads file ---
  const handleUpload = async (file: File, force = false) => {
    setUploading(true)
    setUploadResult(null)
    setShowConflictConfirm(false)
    const form = new FormData()
    form.append('file', file)
    try {
      const url = force ? '/api/rentabilidad/ads/upload?force=true' : '/api/rentabilidad/ads/upload'
      const r = await fetchWithAuth(url, {
        token, onLogout,
        method: 'POST',
        body: form,
      })
      const data = await r.json()
      setUploadResult(data)

      if (data.conflict) {
        // Hay duplicados - guardar el archivo y pedir confirmación
        setPendingFile(file)
        setShowConflictConfirm(true)
        return
      }

      if (data.ok) {
        await reloadListsAfterUpload()
      }
    } catch {
      setUploadResult({ ok: false, filename: file.name, total_rows: 0, inserted: 0, parse_errors: [], insert_errors: [{ batch_start: 0, error: 'Error de red' }] })
    } finally {
      setUploading(false)
    }
  }

  const handleForceUpload = async () => {
    if (!pendingFile) return
    await handleUpload(pendingFile, true)
    setPendingFile(null)
  }

  const reloadListsAfterUpload = async () => {
    const opts = { token, onLogout }
    const [asins, countries] = await Promise.all([
      fetchWithAuth('/api/rentabilidad/asins', opts).then(r2 => r2.ok ? r2.json() : []),
      fetchWithAuth('/api/rentabilidad/countries', opts).then(r2 => r2.ok ? r2.json() : []),
    ])
    setAvailableAsins(asins)
    setAvailableCountries(countries)
  }

  // --- Load ads data ---
  const loadAdsData = async () => {
    setAdsLoading(true)
    try {
      const r = await fetchWithAuth('/api/rentabilidad/ads', { token, onLogout })
      if (r.ok) setAdsData(await r.json())
    } finally {
      setAdsLoading(false)
    }
  }

  const deleteAds = async (asin: string, country: string, dateFrom: string, dateTo: string) => {
    if (!confirm(`¿Borrar datos de Ads para ${asin} (${country}) del ${dateFrom} al ${dateTo}?`)) return
    const params = new URLSearchParams()
    if (asin) params.set('asin', asin)
    if (country) params.set('country', country)
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    const r = await fetchWithAuth(`/api/rentabilidad/ads?${params}`, { token, onLogout, method: 'DELETE' })
    if (r.ok) {
      const { deleted } = await r.json()
      setModalMsg(`${deleted} registros eliminados`)
      loadAdsData()
      await reloadListsAfterUpload()
    }
  }

  // --- Update COGS ---
  const saveCogs = async (asin: string, sku: string) => {
    setCogsSaving(true)
    try {
      const p = (s: string) => parseFloat(s.replace(',', '.'))
      const body: Record<string, number | string> = {}
      if (cogsForm.amazon_referral_fee_pct) body.amazon_referral_fee_pct = p(cogsForm.amazon_referral_fee_pct)
      if (cogsForm.fba_fee_es) body.fba_fee_es = p(cogsForm.fba_fee_es)
      if (cogsForm.fba_fee_it) body.fba_fee_it = p(cogsForm.fba_fee_it)
      if (cogsForm.fba_fee_de) body.fba_fee_de = p(cogsForm.fba_fee_de)
      if (cogsForm.fba_fee_fr) body.fba_fee_fr = p(cogsForm.fba_fee_fr)
      if (cogsForm.other_fixed_costs) body.other_fixed_costs = p(cogsForm.other_fixed_costs)
      if (cogsForm.cost) body.cost = p(cogsForm.cost)
      body.categoria = cogsForm.categoria || null as any

      const r = await fetchWithAuth(`/api/rentabilidad/cogs/${encodeURIComponent(asin)}/${encodeURIComponent(sku)}`, {
        token, onLogout,
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) throw new Error('Error')
      const updated = await r.json()
      setCogs(prev => prev.map(c => (c.ASIN === asin && c.SKU === sku) ? { ...c, ...updated } : c))
      setEditingCogs(null)
      // Refresh categorias
      fetchWithAuth('/api/rentabilidad/categorias', { token, onLogout }).then(r => r.ok ? r.json() : []).then(setAvailableCategorias)
    } catch {
      setModalMsg('Error actualizando COGS')
    } finally {
      setCogsSaving(false)
    }
  }

  // --- Fetch sales for ASIN modal ---
  const openSalesModal = async (asin: string) => {
    setSalesLoading(true)
    try {
      const params = new URLSearchParams()
      if (dateFrom) params.set('desde', dateFrom)
      if (dateTo) params.set('hasta', dateTo)
      params.set('asin', asin)
      const r = await fetchWithAuth(`/api/ventas/?${params}`, { token, onLogout })
      if (!r.ok) throw new Error('Error cargando ventas')
      const rows = await r.json()
      setSalesModal({ asin, rows })
    } catch {
      setModalMsg('Error cargando ventas para este ASIN')
    } finally {
      setSalesLoading(false)
    }
  }

  // --- Filtered lists for dropdowns ---
  const filteredAsins = useMemo(() => {
    if (!asinFilter) return availableAsins
    const f = asinFilter.toLowerCase()
    return availableAsins.filter(a => a.toLowerCase().includes(f))
  }, [availableAsins, asinFilter])

  const filteredCountries = useMemo(() => {
    if (!countryFilter) return availableCountries
    const f = countryFilter.toLowerCase()
    return availableCountries.filter(c => c.toLowerCase().includes(f))
  }, [availableCountries, countryFilter])

  const filteredCategorias = useMemo(() => {
    if (!categoriaFilter) return availableCategorias
    const f = categoriaFilter.toLowerCase()
    return availableCategorias.filter(c => c.toLowerCase().includes(f))
  }, [availableCategorias, categoriaFilter])

  const sortedCogs = useMemo(() => {
    const col = cogsSortCol
    return [...cogs].sort((a, b) => {
      const av = (a as any)[col] ?? ''
      const bv = (b as any)[col] ?? ''
      const na = typeof av === 'number' ? av : parseFloat(av)
      const nb = typeof bv === 'number' ? bv : parseFloat(bv)
      let cmp: number
      if (!isNaN(na) && !isNaN(nb)) {
        cmp = na - nb
      } else {
        cmp = String(av).localeCompare(String(bv), 'es', { sensitivity: 'base' })
      }
      return cogsSortDir === 'asc' ? cmp : -cmp
    })
  }, [cogs, cogsSortCol, cogsSortDir])

  const toggleCogsSort = (col: string) => {
    if (cogsSortCol === col) {
      setCogsSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setCogsSortCol(col)
      setCogsSortDir('asc')
    }
  }

  const deleteCogs = async (asin: string, sku: string) => {
    try {
      const r = await fetchWithAuth(`/api/rentabilidad/cogs/${encodeURIComponent(asin)}/${encodeURIComponent(sku)}`, { token, onLogout, method: 'DELETE' })
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }))
        setModalMsg(`Error eliminando: ${err.detail || r.statusText}`)
        return
      }
      setCogs(prev => prev.filter(c => !(c.ASIN === asin && c.SKU === sku)))
      setEditingCogs(null)
      setConfirmDelete(null)
    } catch (e: any) {
      setModalMsg(`Error: ${e.message}`)
    }
  }

  // --- Chart data for stacked bar ---
  const chartData = useMemo(() => {
    if (!result) return null
    const items = result.breakdown.slice(0, 15) // top 15
    const maxRevenue = Math.max(1, ...items.map(i => i.revenue))
    return { items, maxRevenue }
  }, [result])

  // --- Styles ---
  const cardStyle: React.CSSProperties = {
    backgroundColor: 'white',
    borderRadius: '10px',
    padding: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    border: '1px solid #e5e7eb',
  }
  const labelStyle: React.CSSProperties = { fontSize: '12px', color: '#6b7280', fontWeight: 500, marginBottom: '4px' }
  const valueStyle: React.CSSProperties = { fontSize: '24px', fontWeight: 700 }
  const btnPrimary: React.CSSProperties = {
    padding: '10px 24px', backgroundColor: '#2563eb', color: 'white',
    border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '14px',
  }
  const btnSecondary: React.CSSProperties = {
    padding: '10px 24px', backgroundColor: '#f3f4f6', color: '#374151',
    border: '1px solid #d1d5db', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '14px',
  }
  const inputStyle: React.CSSProperties = {
    padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: '6px',
    fontSize: '14px', width: '100%', boxSizing: 'border-box',
  }

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '0 24px 48px' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', marginBottom: '24px' }}>
        Análisis de Rentabilidad por ASIN
      </h1>

      {/* ===== FILTROS ===== */}
      <div style={{ ...cardStyle, marginBottom: '24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 2fr', gap: '16px', alignItems: 'end' }}>
          {/* ASIN selector */}
          <div style={{ position: 'relative' }}>
            <label style={labelStyle}>ASINs</label>
            <input
              style={inputStyle}
              placeholder="Todos los ASINs"
              value={showAsinDropdown ? asinFilter : (selectedAsins.length ? `${selectedAsins.length} ASIN${selectedAsins.length > 1 ? 's' : ''} seleccionado${selectedAsins.length > 1 ? 's' : ''}` : '')}
              onChange={e => { setAsinFilter(e.target.value); setShowAsinDropdown(true) }}
              onFocus={() => { setAsinFilter(''); setShowAsinDropdown(true) }}
              onBlur={() => setTimeout(() => setShowAsinDropdown(false), 200)}
            />
            {showAsinDropdown && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                backgroundColor: 'white', border: '1px solid #d1d5db', borderRadius: '6px',
                maxHeight: '200px', overflowY: 'auto', boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
              }}>
                {selectedAsins.length > 0 && (
                  <div
                    style={{ padding: '8px 12px', cursor: 'pointer', color: '#dc2626', fontSize: '13px', borderBottom: '1px solid #e5e7eb' }}
                    onMouseDown={() => setSelectedAsins([])}
                  >
                    Limpiar selección ({selectedAsins.length})
                  </div>
                )}
                {filteredAsins.map(a => (
                  <div
                    key={a}
                    style={{
                      padding: '6px 12px', cursor: 'pointer', fontSize: '13px',
                      backgroundColor: selectedAsins.includes(a) ? '#eff6ff' : 'white',
                    }}
                    onMouseDown={() => {
                      setSelectedAsins(prev => prev.includes(a) ? prev.filter(x => x !== a) : [...prev, a])
                    }}
                  >
                    {selectedAsins.includes(a) ? '✓ ' : ''}{a}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Country selector */}
          <div style={{ position: 'relative' }}>
            <label style={labelStyle}>Países</label>
            <input
              style={inputStyle}
              placeholder="Todos los países"
              value={showCountryDropdown ? countryFilter : (selectedCountries.length ? `${selectedCountries.length} país${selectedCountries.length > 1 ? 'es' : ''} seleccionado${selectedCountries.length > 1 ? 's' : ''}` : '')}
              onChange={e => { setCountryFilter(e.target.value); setShowCountryDropdown(true) }}
              onFocus={() => { setCountryFilter(''); setShowCountryDropdown(true) }}
              onBlur={() => setTimeout(() => setShowCountryDropdown(false), 200)}
            />
            {showCountryDropdown && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                backgroundColor: 'white', border: '1px solid #d1d5db', borderRadius: '6px',
                maxHeight: '200px', overflowY: 'auto', boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
              }}>
                {selectedCountries.length > 0 && (
                  <div
                    style={{ padding: '8px 12px', cursor: 'pointer', color: '#dc2626', fontSize: '13px', borderBottom: '1px solid #e5e7eb' }}
                    onMouseDown={() => setSelectedCountries([])}
                  >
                    Limpiar selección ({selectedCountries.length})
                  </div>
                )}
                {filteredCountries.map(c => (
                  <div
                    key={c}
                    style={{
                      padding: '6px 12px', cursor: 'pointer', fontSize: '13px',
                      backgroundColor: selectedCountries.includes(c) ? '#eff6ff' : 'white',
                    }}
                    onMouseDown={() => {
                      setSelectedCountries(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])
                    }}
                  >
                    {selectedCountries.includes(c) ? '✓ ' : ''}{c}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Categoria selector */}
          <div style={{ position: 'relative' }}>
            <label style={labelStyle}>Categoría</label>
            <input
              style={inputStyle}
              placeholder="Todas las categorías"
              value={showCategoriaDropdown ? categoriaFilter : (selectedCategorias.length ? `${selectedCategorias.length} categoría${selectedCategorias.length > 1 ? 's' : ''} seleccionada${selectedCategorias.length > 1 ? 's' : ''}` : '')}
              onChange={e => { setCategoriaFilter(e.target.value); setShowCategoriaDropdown(true) }}
              onFocus={() => { setCategoriaFilter(''); setShowCategoriaDropdown(true) }}
              onBlur={() => setTimeout(() => setShowCategoriaDropdown(false), 200)}
            />
            {showCategoriaDropdown && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                backgroundColor: 'white', border: '1px solid #d1d5db', borderRadius: '6px',
                maxHeight: '200px', overflowY: 'auto', boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
              }}>
                {selectedCategorias.length > 0 && (
                  <div
                    style={{ padding: '8px 12px', cursor: 'pointer', color: '#dc2626', fontSize: '13px', borderBottom: '1px solid #e5e7eb' }}
                    onMouseDown={() => setSelectedCategorias([])}
                  >
                    Limpiar selección ({selectedCategorias.length})
                  </div>
                )}
                {filteredCategorias.map(c => (
                  <div
                    key={c}
                    style={{
                      padding: '6px 12px', cursor: 'pointer', fontSize: '13px',
                      backgroundColor: selectedCategorias.includes(c) ? '#eff6ff' : 'white',
                    }}
                    onMouseDown={() => {
                      setSelectedCategorias(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])
                    }}
                  >
                    {selectedCategorias.includes(c) ? '✓ ' : ''}{c}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Date range */}
          <div style={{ gridColumn: 'span 1' }}>
            <label style={labelStyle}>Periodo</label>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
              {(() => {
                const now = new Date()
                const presets = [
                  { label: 'Este mes', from: new Date(now.getFullYear(), now.getMonth(), 1), to: now },
                  { label: 'Mes pasado', from: new Date(now.getFullYear(), now.getMonth() - 1, 1), to: new Date(now.getFullYear(), now.getMonth(), 0) },
                  { label: 'Últimos 3 meses', from: new Date(now.getFullYear(), now.getMonth() - 2, 1), to: now },
                  { label: 'Últimos 6 meses', from: new Date(now.getFullYear(), now.getMonth() - 5, 1), to: now },
                  { label: 'Este año', from: new Date(now.getFullYear(), 0, 1), to: now },
                  { label: 'Año pasado', from: new Date(now.getFullYear() - 1, 0, 1), to: new Date(now.getFullYear() - 1, 11, 31) },
                ]
                return presets.map(p => {
                  const f = p.from.toISOString().slice(0, 10)
                  const t = p.to.toISOString().slice(0, 10)
                  const active = dateFrom === f && dateTo === t
                  return (
                    <button
                      key={p.label}
                      onClick={() => { setDateFrom(f); setDateTo(t) }}
                      style={{
                        padding: '4px 10px', fontSize: '12px', borderRadius: '14px', cursor: 'pointer',
                        border: active ? '1px solid #3b82f6' : '1px solid #d1d5db',
                        backgroundColor: active ? '#eff6ff' : 'white',
                        color: active ? '#2563eb' : '#374151',
                        fontWeight: active ? 600 : 400,
                      }}
                    >
                      {p.label}
                    </button>
                  )
                })
              })()}
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input type="date" style={{ ...inputStyle, flex: 1 }} value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
              <span style={{ color: '#9ca3af', fontSize: '13px' }}>—</span>
              <input type="date" style={{ ...inputStyle, flex: 1 }} value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </div>
          </div>

          {/* Group by */}
          <div>
            <label style={labelStyle}>Agrupar por</label>
            <select
              style={inputStyle}
              value={groupBy}
              onChange={e => setGroupBy(e.target.value as typeof groupBy)}
            >
              <option value="asin">ASIN</option>
              <option value="country">País</option>
              <option value="asin_country">ASIN + País</option>
              <option value="month">Mes</option>
            </select>
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
          <button style={btnPrimary} onClick={analyze} disabled={loading || !dateFrom || !dateTo}>
            {loading ? 'Analizando...' : 'Analizar'}
          </button>
          <button style={btnSecondary} onClick={() => setShowUpload(true)}>
            Subir datos Ads (CSV/XLSX)
          </button>
          <button style={btnSecondary} onClick={() => setShowCogs(!showCogs)}>
            {showCogs ? 'Ocultar COGS' : 'Gestionar COGS'}
          </button>
          <button style={btnSecondary} onClick={() => { setShowAds(!showAds); if (!showAds) loadAdsData() }}>
            {showAds ? 'Ocultar Ads' : 'Ver datos Ads'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ ...cardStyle, marginBottom: '24px', backgroundColor: '#fef2f2', borderColor: '#fecaca', color: '#dc2626' }}>
          {error}
        </div>
      )}

      {/* ===== UPLOAD MODAL ===== */}
      {showUpload && (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{ ...cardStyle, maxWidth: '500px', width: '90%' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>Subir datos de Amazon Ads</h3>

            <div
              style={{
                border: `2px dashed ${dragOver ? '#2563eb' : '#d1d5db'}`,
                borderRadius: '8px', padding: '40px', textAlign: 'center',
                backgroundColor: dragOver ? '#eff6ff' : '#f9fafb', cursor: 'pointer',
                transition: 'all 0.2s',
              }}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => {
                e.preventDefault(); setDragOver(false)
                const file = e.dataTransfer.files[0]
                if (file) handleUpload(file)
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx"
                style={{ display: 'none' }}
                onChange={e => { if (e.target.files?.[0]) handleUpload(e.target.files[0]) }}
              />
              {uploading ? (
                <p style={{ color: '#6b7280' }}>Subiendo y procesando...</p>
              ) : (
                <p style={{ color: '#6b7280' }}>Arrastra un archivo CSV/XLSX aquí o haz clic para seleccionar</p>
              )}
            </div>

            {/* Resultado normal */}
            {uploadResult && !showConflictConfirm && (
              <div style={{
                marginTop: '16px', padding: '12px', borderRadius: '6px',
                backgroundColor: uploadResult.ok ? '#f0fdf4' : '#fef2f2',
                color: uploadResult.ok ? '#166534' : '#dc2626',
              }}>
                <p style={{ fontWeight: 600 }}>
                  {uploadResult.ok
                    ? `${uploadResult.inserted} filas ${uploadResult.conflict === false ? 'insertadas/actualizadas' : 'insertadas'} de ${uploadResult.total_rows}`
                    : uploadResult.message || 'Error en la subida'}
                </p>
                {uploadResult.insert_errors?.length > 0 && (
                  <p style={{ fontSize: '12px', marginTop: '4px' }}>
                    Errores: {uploadResult.insert_errors.map(e => e.error).join(', ')}
                  </p>
                )}
              </div>
            )}

            {/* Confirmación de duplicados */}
            {showConflictConfirm && (
              <div style={{
                marginTop: '16px', padding: '16px', borderRadius: '6px',
                backgroundColor: '#fffbeb', border: '1px solid #fde68a',
              }}>
                <p style={{ fontWeight: 600, color: '#92400e', marginBottom: '8px' }}>
                  Se encontraron datos que ya existen
                </p>
                <p style={{ fontSize: '13px', color: '#92400e', marginBottom: '12px' }}>
                  El archivo contiene {uploadResult?.total_rows} filas con datos que coinciden con registros existentes.
                  Si continúas, se actualizarán los valores existentes con los nuevos datos.
                </p>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    style={{ ...btnPrimary, backgroundColor: '#d97706' }}
                    onClick={handleForceUpload}
                    disabled={uploading}
                  >
                    {uploading ? 'Actualizando...' : 'Confirmar y actualizar'}
                  </button>
                  <button
                    style={btnSecondary}
                    onClick={() => { setShowConflictConfirm(false); setPendingFile(null); setUploadResult(null) }}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button style={btnSecondary} onClick={() => { setShowUpload(false); setUploadResult(null); setShowConflictConfirm(false); setPendingFile(null) }}>
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== SUMMARY CARDS ===== */}
      {result && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '16px', marginBottom: '24px' }}>
            <div style={cardStyle}>
              <div style={labelStyle}>Ingresos (con IVA)<Tip text="Suma de TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL de todas las ventas del periodo. Incluye IVA del país de destino." /></div>
              <div style={{ ...valueStyle, color: COLORS.revenue }}>{EUR(result.summary.total_revenue)}</div>
              <div style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px' }}>{result.summary.total_units} uds · IVA {EUR(result.summary.total_vat)}</div>
            </div>
            <div style={cardStyle}>
              <div style={labelStyle}>Costes Totales<Tip text={"IVA (precio con IVA − precio sin IVA)\n+ COGS (coste unitario × uds)\n+ Comisión Amazon (% sobre ingreso)\n+ FBA fee (tarifa por país × uds)\n+ Otros costes fijos × uds\n+ Gasto en Ads"} /></div>
              <div style={{ ...valueStyle, color: COLORS.cogs }}>{EUR(result.summary.total_costs)}</div>
              <div style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px' }}>
                IVA {EUR(result.summary.total_vat)} | COGS {EUR(result.summary.total_cogs)} | Amazon {EUR(result.summary.total_amazon_fees)} | Ads {EUR(result.summary.total_ads_spend)}
              </div>
            </div>
            <div style={cardStyle}>
              <div style={labelStyle}>Beneficio Neto<Tip text="Ingresos (con IVA) − Costes Totales.\nEl margen es este valor entre los ingresos (%). El ROI es beneficio entre costes (%)." /></div>
              <div style={{ ...valueStyle, color: result.summary.net_profit >= 0 ? COLORS.profit : COLORS.loss }}>
                {EUR(result.summary.net_profit)}
              </div>
            </div>
            <div style={cardStyle}>
              <div style={labelStyle}>Margen<Tip text="Beneficio Neto ÷ Ingresos (con IVA) × 100. Indica qué porcentaje del precio de venta queda como beneficio." /></div>
              <div style={{ ...valueStyle, color: result.summary.margin_pct >= 0 ? COLORS.profit : COLORS.loss }}>
                {PCT(result.summary.margin_pct)}
              </div>
            </div>
            <div style={cardStyle}>
              <div style={labelStyle}>ROI<Tip text="Beneficio Neto ÷ Costes Totales × 100. Mide el retorno obtenido por cada euro invertido en costes." /></div>
              <div style={{ ...valueStyle, color: result.summary.roi >= 0 ? COLORS.profit : COLORS.loss }}>
                {PCT(result.summary.roi)}
              </div>
            </div>
          </div>

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <div style={{ ...cardStyle, marginBottom: '24px', backgroundColor: '#fffbeb', borderColor: '#fde68a' }}>
              <div style={{ fontWeight: 600, color: '#92400e', marginBottom: '8px' }}>Avisos</div>
              {result.warnings.map((w, i) => (
                <div key={i} style={{ fontSize: '13px', color: '#92400e' }}>{w}</div>
              ))}
            </div>
          )}

          {/* ===== STACKED BAR CHART ===== */}
          {chartData && chartData.items.length > 0 && (
            <div style={{ ...cardStyle, marginBottom: '24px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Desglose de Costes vs Ingresos</h3>

              {/* Legend */}
              <div style={{ display: 'flex', gap: '20px', marginBottom: '12px', fontSize: '12px' }}>
                {[
                  { label: 'IVA', color: '#a3a3a3' },
                  { label: 'COGS', color: COLORS.cogs },
                  { label: 'Amazon Fees', color: COLORS.amazonFees },
                  { label: 'Ads', color: COLORS.ads },
                  { label: 'Beneficio', color: COLORS.profit },
                ].map(l => (
                  <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <div style={{ width: '12px', height: '12px', borderRadius: '2px', backgroundColor: l.color }} />
                    {l.label}
                  </div>
                ))}
              </div>

              <svg width="100%" viewBox={`0 0 800 ${chartData.items.length * 36 + 20}`}>
                {chartData.items.map((item, i) => {
                  const y = i * 36 + 10
                  const barWidth = 580
                  const maxVal = chartData.maxRevenue
                  const scale = (v: number) => (v / maxVal) * barWidth

                  const vatW = scale(item.vat)
                  const cogsW = scale(item.cogs)
                  const feesW = scale(item.amazon_referral_fee + item.fba_fee + item.other_costs + (item.dst || 0))
                  const adsW = scale(item.ads_spend)
                  const profitW = Math.max(0, scale(Math.max(0, item.net_profit)))

                  const label = item.month || item.asin || item.country || '?'

                  return (
                    <g key={i}>
                      <text x="0" y={y + 16} fontSize="11" fill="#374151" fontWeight="500">
                        {label.slice(0, 14)}
                      </text>
                      {/* Revenue outline */}
                      <rect x="120" y={y} width={scale(item.revenue)} height="22" fill="none" stroke="#d1d5db" strokeWidth="1" rx="3" />
                      {/* Stacked costs */}
                      <rect x="120" y={y} width={vatW} height="22" fill="#a3a3a3" rx="3" />
                      <rect x={120 + vatW} y={y} width={cogsW} height="22" fill={COLORS.cogs} />
                      <rect x={120 + vatW + cogsW} y={y} width={feesW} height="22" fill={COLORS.amazonFees} />
                      <rect x={120 + vatW + cogsW + feesW} y={y} width={adsW} height="22" fill={COLORS.ads} />
                      <rect x={120 + vatW + cogsW + feesW + adsW} y={y} width={profitW} height="22" fill={COLORS.profit} opacity="0.6" rx="0" />
                      {/* Values */}
                      <text x="720" y={y + 16} fontSize="11" fill={item.net_profit >= 0 ? '#166534' : '#dc2626'} textAnchor="end" fontWeight="600">
                        {EUR(item.net_profit)} ({PCT(item.margin_pct)})
                      </text>
                    </g>
                  )
                })}
              </svg>
            </div>
          )}

          {/* ===== DETAIL TABLE ===== */}
          <div style={{ ...cardStyle, marginBottom: '24px', overflowX: 'auto' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Detalle</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                  {groupBy !== 'month' && <th style={{ textAlign: 'left', padding: '8px' }}>ASIN<Tip text="Identificador único del producto en Amazon." /></th>}
                  {groupBy === 'month' && <th style={{ textAlign: 'left', padding: '8px' }}>Mes</th>}
                  {(groupBy === 'country' || groupBy === 'asin_country') && <th style={{ textAlign: 'left', padding: '8px' }}>País<Tip text="País de destino de la venta (SALE_ARRIVAL_COUNTRY)." /></th>}
                  {groupBy === 'asin' && <th style={{ textAlign: 'left', padding: '8px' }}>Título<Tip text="Descripción del producto en el catálogo de Amazon." /></th>}
                  <th style={{ textAlign: 'right', padding: '8px' }}>Uds<Tip text="Suma de unidades vendidas (QTY) en el periodo." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>Ingresos<Tip text="Suma de TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL. Precio total cobrado al cliente, IVA incluido." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>IVA<Tip text="IVA real de cada venta (precio con IVA − precio sin IVA). Varía según país de destino." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>COGS<Tip text="Coste unitario del producto × unidades vendidas." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>Referral<Tip text="Comisión de Amazon por venta. 8% si PVP < 10€, sino el % configurado (por defecto 15%)." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>DST<Tip text="Impuesto de Servicios Digitales. ES/IT/FR: 3%, DE: 1%. Se aplica sobre Referral + FBA." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>Ads<Tip text="Gasto en publicidad de Amazon Ads para este ASIN/periodo (importado por CSV/XLSX)." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>Beneficio<Tip text="Ingresos − todos los costes (IVA, COGS, Referral, FBA, DST, Otros, Ads)." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>Margen<Tip text="Beneficio ÷ Ingresos × 100. Porcentaje de beneficio sobre el precio de venta." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>ROI<Tip text="Beneficio ÷ Costes totales × 100. Retorno sobre la inversión." /></th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>EUR/ud<Tip text="Beneficio neto ÷ unidades vendidas. Ganancia por unidad." /></th>
                </tr>
              </thead>
              <tbody>
                {result.breakdown.map((b, i) => {
                  const key = `${b.asin}-${b.country}-${b.month || i}`
                  const isExpanded = expandedRow === key
                  return (
                    <tr
                      key={key}
                      style={{
                        borderBottom: '1px solid #f3f4f6', cursor: 'pointer',
                        backgroundColor: isExpanded ? '#f9fafb' : i % 2 === 0 ? 'white' : '#fafafa',
                      }}
                      onClick={() => setExpandedRow(isExpanded ? null : key)}
                    >
                      {groupBy !== 'month' && (
                        <td style={{ padding: '8px', fontFamily: 'monospace', fontWeight: 500 }}>
                          {b.asin ? (
                            <span
                              style={{ color: '#2563eb', cursor: 'pointer', textDecoration: 'underline' }}
                              onClick={e => { e.stopPropagation(); openSalesModal(b.asin) }}
                            >{b.asin}</span>
                          ) : '-'}
                        </td>
                      )}
                      {groupBy === 'month' && <td style={{ padding: '8px', fontWeight: 500 }}>{b.month}</td>}
                      {(groupBy === 'country' || groupBy === 'asin_country') && (
                        <td style={{ padding: '8px' }}>{b.country}</td>
                      )}
                      {groupBy === 'asin' && (
                        <td style={{ padding: '8px', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {b.title}
                        </td>
                      )}
                      <td style={{ textAlign: 'right', padding: '8px' }}>{b.units}</td>
                      <td style={{ textAlign: 'right', padding: '8px' }}>{EUR(b.revenue)}</td>
                      <td style={{ textAlign: 'right', padding: '8px', color: '#6b7280' }}>{EUR(b.vat)}</td>
                      <td style={{ textAlign: 'right', padding: '8px', color: COLORS.cogs }}>{EUR(b.cogs)}</td>
                      <td style={{ textAlign: 'right', padding: '8px', color: COLORS.amazonFees }}>
                        {EUR(b.amazon_referral_fee + b.fba_fee + b.other_costs)}
                      </td>
                      <td style={{ textAlign: 'right', padding: '8px', color: '#9333ea' }}>{EUR(b.dst || 0)}</td>
                      <td style={{ textAlign: 'right', padding: '8px', color: COLORS.ads }}>{EUR(b.ads_spend)}</td>
                      <td style={{
                        textAlign: 'right', padding: '8px', fontWeight: 600,
                        color: b.net_profit >= 0 ? COLORS.profit : COLORS.loss,
                      }}>
                        {EUR(b.net_profit)}
                      </td>
                      <td style={{
                        textAlign: 'right', padding: '8px',
                        color: b.margin_pct >= 0 ? COLORS.profit : COLORS.loss,
                      }}>
                        {PCT(b.margin_pct)}
                      </td>
                      <td style={{
                        textAlign: 'right', padding: '8px',
                        color: b.roi >= 0 ? COLORS.profit : COLORS.loss,
                      }}>
                        {PCT(b.roi)}
                      </td>
                      <td style={{ textAlign: 'right', padding: '8px' }}>{EUR(b.profit_per_unit)}</td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr style={{ borderTop: '2px solid #374151', fontWeight: 700 }}>
                  <td style={{ padding: '8px' }} colSpan={groupBy === 'asin' ? 2 : (groupBy === 'asin_country' ? 2 : 1)}>
                    TOTAL
                  </td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>{result.summary.total_units}</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>{EUR(result.summary.total_revenue)}</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: '#6b7280' }}>{EUR(result.summary.total_vat)}</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: COLORS.cogs }}>{EUR(result.summary.total_cogs)}</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: COLORS.amazonFees }}>{EUR(result.summary.total_amazon_fees)}</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: '#9333ea' }}>{EUR(result.summary.total_dst)}</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: COLORS.ads }}>{EUR(result.summary.total_ads_spend)}</td>
                  <td style={{
                    textAlign: 'right', padding: '8px',
                    color: result.summary.net_profit >= 0 ? COLORS.profit : COLORS.loss,
                  }}>
                    {EUR(result.summary.net_profit)}
                  </td>
                  <td style={{
                    textAlign: 'right', padding: '8px',
                    color: result.summary.margin_pct >= 0 ? COLORS.profit : COLORS.loss,
                  }}>
                    {PCT(result.summary.margin_pct)}
                  </td>
                  <td style={{
                    textAlign: 'right', padding: '8px',
                    color: result.summary.roi >= 0 ? COLORS.profit : COLORS.loss,
                  }}>
                    {PCT(result.summary.roi)}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}

      {/* ===== ADS DATA VIEWER ===== */}
      {showAds && (
        <div style={{ ...cardStyle, marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600 }}>
              Datos de Ads cargados {adsData.length > 0 && `(${adsData.length} registros)`}
            </h3>
          </div>
          {adsLoading ? (
            <p style={{ textAlign: 'center', color: '#6b7280', padding: '20px' }}>Cargando...</p>
          ) : adsData.length === 0 ? (
            <p style={{ textAlign: 'center', color: '#6b7280', padding: '20px' }}>
              No hay datos de Ads cargados. Sube un archivo CSV/XLSX.
            </p>
          ) : (
            <>
              {/* Agrupar por fecha_inicio-fecha_fin para mostrar lotes */}
              {(() => {
                const groups: Record<string, AdsRecord[]> = {}
                for (const a of adsData) {
                  const key = `${a.fecha_inicio}|${a.fecha_fin}`
                  if (!groups[key]) groups[key] = []
                  groups[key].push(a)
                }
                return Object.entries(groups).map(([key, records]) => {
                  const [fi, ff] = key.split('|')
                  const totalSpend = records.reduce((s, r) => s + (r.spend || 0), 0)
                  const totalSales = records.reduce((s, r) => s + (r.sales_7d || 0), 0)
                  const asins = [...new Set(records.map(r => r.asin))]
                  const countries = [...new Set(records.map(r => r.country_code || r.country))]
                  return (
                    <div key={key} style={{ marginBottom: '16px', border: '1px solid #e5e7eb', borderRadius: '8px', overflow: 'hidden' }}>
                      <div style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '12px 16px', backgroundColor: '#f9fafb',
                      }}>
                        <div>
                          <span style={{ fontWeight: 600, fontSize: '14px' }}>{fi} → {ff}</span>
                          <span style={{ fontSize: '12px', color: '#6b7280', marginLeft: '16px' }}>
                            {records.length} registros | {asins.length} ASINs | {countries.join(', ')} | Spend: {EUR(totalSpend)} | Sales: {EUR(totalSales)}
                          </span>
                        </div>
                        <button
                          style={{ padding: '4px 12px', fontSize: '12px', color: '#dc2626', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', cursor: 'pointer' }}
                          onClick={() => deleteAds('', '', fi, ff)}
                        >
                          Borrar periodo
                        </button>
                      </div>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                        <thead>
                          <tr style={{ borderBottom: '1px solid #e5e7eb', backgroundColor: '#fafafa' }}>
                            <th style={{ textAlign: 'left', padding: '6px 8px' }}>ASIN</th>
                            <th style={{ textAlign: 'left', padding: '6px 8px' }}>País</th>
                            <th style={{ textAlign: 'left', padding: '6px 8px' }}>Campaña</th>
                            <th style={{ textAlign: 'right', padding: '6px 8px' }}>Impr.</th>
                            <th style={{ textAlign: 'right', padding: '6px 8px' }}>Clics</th>
                            <th style={{ textAlign: 'right', padding: '6px 8px' }}>Spend</th>
                            <th style={{ textAlign: 'right', padding: '6px 8px' }}>Sales 7d</th>
                            <th style={{ textAlign: 'right', padding: '6px 8px' }}>ACOS</th>
                            <th style={{ textAlign: 'right', padding: '6px 8px' }}>ROAS</th>
                          </tr>
                        </thead>
                        <tbody>
                          {records.map(r => (
                            <tr key={r.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                              <td style={{ padding: '4px 8px', fontFamily: 'monospace' }}>{r.asin}</td>
                              <td style={{ padding: '4px 8px' }}>{r.country_code || r.country}</td>
                              <td style={{ padding: '4px 8px', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.campaign_name}</td>
                              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{(r.impressions || 0).toLocaleString()}</td>
                              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{r.clicks || 0}</td>
                              <td style={{ textAlign: 'right', padding: '4px 8px', color: COLORS.ads }}>{EUR(r.spend || 0)}</td>
                              <td style={{ textAlign: 'right', padding: '4px 8px', color: COLORS.revenue }}>{EUR(r.sales_7d || 0)}</td>
                              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{r.acos ? PCT(r.acos * 100) : '-'}</td>
                              <td style={{ textAlign: 'right', padding: '4px 8px' }}>{r.roas?.toFixed(2) || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                })
              })()}
            </>
          )}
        </div>
      )}

      {/* ===== COGS MANAGEMENT ===== */}
      {showCogs && (
        <div style={{ ...cardStyle, marginBottom: '24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Gestión de COGS</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                {[
                  { col: 'ASIN', label: 'ASIN', tip: 'Identificador único del producto en Amazon.', align: 'left' },
                  { col: 'categoria', label: 'Categoría', tip: 'Categoría de producto para agrupar y filtrar.', align: 'left' },
                  { col: 'Title', label: 'Título', tip: 'Nombre del producto importado del catálogo.', align: 'left' },
                  { col: 'Cost', label: 'Coste Ud.', tip: 'Coste de adquisición/fabricación por unidad (sin IVA).', align: 'right' },
                  { col: 'amazon_referral_fee_pct', label: 'Referral %', tip: 'Comisión de Amazon (referral fee). Se aplica el % configurado si PVP ≥ 10€, o 8% si PVP < 10€.', align: 'right' },
                  { col: 'fba_fee_es', label: 'FBA ES', tip: 'Tarifa FBA por unidad en España. Se usa como fallback para países sin tarifa específica.', align: 'right' },
                  { col: 'fba_fee_it', label: 'FBA IT', tip: 'Tarifa FBA por unidad en Italia.', align: 'right' },
                  { col: 'fba_fee_de', label: 'FBA DE', tip: 'Tarifa FBA por unidad en Alemania.', align: 'right' },
                  { col: 'fba_fee_fr', label: 'FBA FR', tip: 'Tarifa FBA por unidad en Francia.', align: 'right' },
                  { col: 'other_fixed_costs', label: 'Otros costes', tip: 'Costes fijos adicionales por unidad: etiquetado, packaging especial, seguros, etc.', align: 'right' },
                ].map(h => (
                  <th
                    key={h.col}
                    style={{ textAlign: h.align as any, padding: '8px', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                    onClick={() => toggleCogsSort(h.col)}
                  >
                    {h.label}{cogsSortCol === h.col ? (cogsSortDir === 'asc' ? ' ▲' : ' ▼') : ''}<Tip text={h.tip} />
                  </th>
                ))}
                <th style={{ textAlign: 'center', padding: '8px' }}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {sortedCogs.map((c, i) => {
                const cogsKey = `${c.ASIN}|${c.SKU}`
                const isEditing = editingCogs === cogsKey
                return (
                  <tr key={cogsKey} style={{ borderBottom: '1px solid #f3f4f6', backgroundColor: i % 2 === 0 ? 'white' : '#fafafa' }}>
                    <td style={{ padding: '8px', fontFamily: 'monospace' }}>{c.ASIN}</td>
                    {isEditing ? (
                      <>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '100px' }} value={cogsForm.categoria}
                            onChange={e => setCogsForm(f => ({ ...f, categoria: e.target.value }))} placeholder="Categoría" />
                        </td>
                        <td style={{ padding: '8px', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {c.Title || '-'}
                        </td>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '80px' }} value={cogsForm.cost}
                            onChange={e => setCogsForm(f => ({ ...f, cost: e.target.value }))} />
                        </td>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '60px' }} value={cogsForm.amazon_referral_fee_pct}
                            onChange={e => setCogsForm(f => ({ ...f, amazon_referral_fee_pct: e.target.value }))} />
                        </td>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '55px' }} value={cogsForm.fba_fee_es}
                            onChange={e => setCogsForm(f => ({ ...f, fba_fee_es: e.target.value }))} />
                        </td>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '55px' }} value={cogsForm.fba_fee_it}
                            onChange={e => setCogsForm(f => ({ ...f, fba_fee_it: e.target.value }))} />
                        </td>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '55px' }} value={cogsForm.fba_fee_de}
                            onChange={e => setCogsForm(f => ({ ...f, fba_fee_de: e.target.value }))} />
                        </td>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '55px' }} value={cogsForm.fba_fee_fr}
                            onChange={e => setCogsForm(f => ({ ...f, fba_fee_fr: e.target.value }))} />
                        </td>
                        <td style={{ padding: '4px' }}>
                          <input style={{ ...inputStyle, width: '60px' }} value={cogsForm.other_fixed_costs}
                            onChange={e => setCogsForm(f => ({ ...f, other_fixed_costs: e.target.value }))} />
                        </td>
                        <td style={{ padding: '4px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                          <button
                            style={{ ...btnPrimary, padding: '4px 12px', fontSize: '12px', marginRight: '4px' }}
                            onClick={() => saveCogs(c.ASIN, c.SKU)}
                            disabled={cogsSaving}
                          >
                            {cogsSaving ? '...' : 'Guardar'}
                          </button>
                          <button
                            style={{ ...btnSecondary, padding: '4px 12px', fontSize: '12px', marginRight: '4px' }}
                            onClick={() => setEditingCogs(null)}
                          >
                            X
                          </button>
                          <button
                            title="Eliminar registro"
                            style={{ padding: '4px 8px', fontSize: '14px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', cursor: 'pointer', color: '#dc2626' }}
                            onClick={() => setConfirmDelete({ asin: c.ASIN, sku: c.SKU })}
                          >
                            🗑
                          </button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td style={{ padding: '8px', fontSize: '12px' }}>{c.categoria || '-'}</td>
                        <td style={{ padding: '8px', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {c.Title || '-'}
                        </td>
                        <td style={{ textAlign: 'right', padding: '8px' }}>{c.Cost != null ? EUR(c.Cost) : '-'}</td>
                        <td style={{ textAlign: 'right', padding: '8px' }}>{c.amazon_referral_fee_pct ?? 15}%</td>
                        <td style={{ textAlign: 'right', padding: '8px' }}>{c.fba_fee_es != null ? EUR(c.fba_fee_es) : '-'}</td>
                        <td style={{ textAlign: 'right', padding: '8px' }}>{c.fba_fee_it != null ? EUR(c.fba_fee_it) : '-'}</td>
                        <td style={{ textAlign: 'right', padding: '8px' }}>{c.fba_fee_de != null ? EUR(c.fba_fee_de) : '-'}</td>
                        <td style={{ textAlign: 'right', padding: '8px' }}>{c.fba_fee_fr != null ? EUR(c.fba_fee_fr) : '-'}</td>
                        <td style={{ textAlign: 'right', padding: '8px' }}>{c.other_fixed_costs != null ? EUR(c.other_fixed_costs) : '-'}</td>
                        <td style={{ textAlign: 'center', padding: '8px' }}>
                          <button
                            style={{ ...btnSecondary, padding: '4px 12px', fontSize: '12px' }}
                            onClick={() => {
                              setEditingCogs(cogsKey)
                              setCogsForm({
                                cost: c.Cost?.toString() || '',
                                amazon_referral_fee_pct: (c.amazon_referral_fee_pct ?? 15).toString(),
                                fba_fee_es: c.fba_fee_es?.toString() || '0',
                                fba_fee_it: c.fba_fee_it?.toString() || '0',
                                fba_fee_de: c.fba_fee_de?.toString() || '0',
                                fba_fee_fr: c.fba_fee_fr?.toString() || '0',
                                other_fixed_costs: c.other_fixed_costs?.toString() || '0',
                                categoria: c.categoria || '',
                              })
                            }}
                          >
                            Editar
                          </button>
                        </td>
                      </>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
          {cogs.length === 0 && (
            <p style={{ textAlign: 'center', color: '#6b7280', padding: '20px' }}>
              No hay datos de COGS. Importa los costes desde Amazon Seller Central.
            </p>
          )}
        </div>
      )}
      {/* ===== SALES DETAIL MODAL ===== */}
      {salesModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setSalesModal(null)}>
          <div style={{ background: 'white', borderRadius: '12px', padding: '24px', maxWidth: '900px', width: '95%', maxHeight: '80vh', display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Ventas — {salesModal.asin} ({salesModal.rows.length} registros)</h3>
              <button style={{ ...btnSecondary, padding: '4px 12px', fontSize: '12px' }} onClick={() => setSalesModal(null)}>X</button>
            </div>
            <div style={{ overflowY: 'auto', flex: 1 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e5e7eb', position: 'sticky', top: 0, backgroundColor: 'white' }}>
                    <th style={{ textAlign: 'left', padding: '6px' }}>Fecha</th>
                    <th style={{ textAlign: 'left', padding: '6px' }}>País</th>
                    <th style={{ textAlign: 'left', padding: '6px' }}>SKU</th>
                    <th style={{ textAlign: 'right', padding: '6px' }}>Uds</th>
                    <th style={{ textAlign: 'right', padding: '6px' }}>Precio (IVA incl.)</th>
                    <th style={{ textAlign: 'right', padding: '6px' }}>Precio (sin IVA)</th>
                    <th style={{ textAlign: 'right', padding: '6px' }}>IVA</th>
                  </tr>
                </thead>
                <tbody>
                  {salesModal.rows.map((s, i) => {
                    const vatIncl = s.TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL || 0
                    const vatExcl = parseFloat(s.TOTAL_PRICE_OF_ITEMS_AMT_VAT_EXCL) || 0
                    return (
                      <tr key={i} style={{ borderBottom: '1px solid #f3f4f6', backgroundColor: i % 2 === 0 ? 'white' : '#fafafa' }}>
                        <td style={{ padding: '6px' }}>{s.TRANSACTION_COMPLETE_DATE_DT || s.TRANSACTION_COMPLETE_DATE || '-'}</td>
                        <td style={{ padding: '6px' }}>{s.SALE_ARRIVAL_COUNTRY || '-'}</td>
                        <td style={{ padding: '6px', fontFamily: 'monospace', fontSize: '11px' }}>{s.SELLER_SKU || '-'}</td>
                        <td style={{ textAlign: 'right', padding: '6px' }}>{s.QTY ?? '-'}</td>
                        <td style={{ textAlign: 'right', padding: '6px' }}>{EUR(vatIncl)}</td>
                        <td style={{ textAlign: 'right', padding: '6px' }}>{EUR(vatExcl)}</td>
                        <td style={{ textAlign: 'right', padding: '6px', color: '#6b7280' }}>{EUR(vatIncl - vatExcl)}</td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr style={{ borderTop: '2px solid #374151', fontWeight: 700 }}>
                    <td colSpan={3} style={{ padding: '6px' }}>TOTAL</td>
                    <td style={{ textAlign: 'right', padding: '6px' }}>{salesModal.rows.reduce((s, r) => s + (r.QTY || 0), 0)}</td>
                    <td style={{ textAlign: 'right', padding: '6px' }}>{EUR(salesModal.rows.reduce((s, r) => s + (r.TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL || 0), 0))}</td>
                    <td style={{ textAlign: 'right', padding: '6px' }}>{EUR(salesModal.rows.reduce((s, r) => s + (parseFloat(r.TOTAL_PRICE_OF_ITEMS_AMT_VAT_EXCL) || 0), 0))}</td>
                    <td style={{ textAlign: 'right', padding: '6px', color: '#6b7280' }}>{EUR(salesModal.rows.reduce((s, r) => s + ((r.TOTAL_PRICE_OF_ITEMS_AMT_VAT_INCL || 0) - (parseFloat(r.TOTAL_PRICE_OF_ITEMS_AMT_VAT_EXCL) || 0)), 0))}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>
      )}
      {salesLoading && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
          <div style={{ background: 'white', borderRadius: '12px', padding: '24px 32px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            Cargando ventas...
          </div>
        </div>
      )}

      {/* ===== MESSAGE MODAL ===== */}
      {confirmDelete && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setConfirmDelete(null)}>
          <div style={{ background: 'white', borderRadius: '12px', padding: '24px 32px', maxWidth: '420px', width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}
            onClick={e => e.stopPropagation()}>
            <p style={{ margin: '0 0 16px', fontSize: '14px', color: '#1f2937' }}>
              ¿Seguro que quieres eliminar el registro <strong>{confirmDelete.asin}</strong> / <strong>{confirmDelete.sku}</strong>?
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button style={{ ...btnSecondary, padding: '6px 20px', fontSize: '13px' }} onClick={() => setConfirmDelete(null)}>
                Cancelar
              </button>
              <button
                style={{ padding: '6px 20px', fontSize: '13px', backgroundColor: '#dc2626', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer' }}
                onClick={() => deleteCogs(confirmDelete.asin, confirmDelete.sku)}
              >
                Eliminar
              </button>
            </div>
          </div>
        </div>
      )}

      {modalMsg && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setModalMsg(null)}>
          <div style={{ background: 'white', borderRadius: '12px', padding: '24px 32px', maxWidth: '420px', width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}
            onClick={e => e.stopPropagation()}>
            <p style={{ margin: '0 0 16px', fontSize: '14px', color: '#1f2937' }}>{modalMsg}</p>
            <div style={{ textAlign: 'right' }}>
              <button style={{ ...btnPrimary, padding: '6px 20px', fontSize: '13px' }} onClick={() => setModalMsg(null)}>
                Aceptar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

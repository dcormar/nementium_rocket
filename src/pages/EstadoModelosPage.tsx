import { useEffect, useState } from 'react'
import { fetchWithAuth } from '../utils/fetchWithAuth'

export default function EstadoModelosPage({ token, onLogout }: { token: string; onLogout?: () => void }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchWithAuth('http://localhost:8000/modelos/estado', {
      token,
      onLogout,
    })
      .then(r => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [token, onLogout])

  if (loading) return <div>Cargando...</div>
  if (!data) return <div>Error cargando estado</div>

  return (
    <div className="estado-modelos-page">
      <h2>Estado de modelos de Hacienda</h2>
      <ul>
        <li>Ingresos netos: <b>{data.ingresos_netos} €</b></li>
        <li>Gastos deducibles: <b>{data.gastos_deducibles} €</b></li>
        <li>Rendimiento neto: <b>{data.rendimiento_neto} €</b></li>
        <li>Resultado IRPF: <b>{data.resultado_irpf} €</b></li>
        <li>Ventas nacionales con IVA: <b>{data.ventas_nacionales_iva} €</b></li>
        <li>IVA repercutido: <b>{data.iva_repercutido} €</b></li>
        <li>Entregas intracomunitarias exentas: <b>{data.entregas_intracomunitarias} €</b></li>
        <li>Casilla 60: <b>{data.casilla_60} €</b></li>
        <li>Adquisiciones intracomunitarias: <b>{data.adquisiciones_intracomunitarias} €</b></li>
        <li>Servicios intracomunitarios: <b>{data.servicios_intracomunitarios} €</b></li>
        <li>Servicios extracomunitarios: <b>{data.servicios_extracomunitarios} €</b></li>
        <li>Importaciones (DUAs): <b>{data.importaciones_duas} €</b></li>
        <li>Gastos nacionales con IVA: <b>{data.gastos_nacionales_iva} €</b></li>
      </ul>
    </div>
  )
}

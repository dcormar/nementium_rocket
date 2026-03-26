import { useState, useEffect } from 'react'
import { supabase } from './utils/supabaseClient'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import UploadPage from './pages/UploadPage'
import EstadoModelosPage from './pages/EstadoModelosPage'
import MesDetallePage from './pages/MesDetallePage'
import CreateInvoicePage from './pages/CreateInvoicePage'
import ConsultaPage from './pages/ConsultaPage'
import RentabilidadPage from './pages/RentabilidadPage'
import ChatAssistant from './components/ChatAssistant'
import './App.css'

import logo from './assets/logo.png'
import { LogOut, User } from 'lucide-react'

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [page, setPage] = useState('dashboard')
  const [loading, setLoading] = useState(true)
  const [dashboardKey, setDashboardKey] = useState(0)

  // Inicializar sesión desde Supabase Auth
  useEffect(() => {
    // Recuperar sesión existente (persistida por el SDK en localStorage)
    supabase.auth.getSession().then(({ data: { session } }) => {
      setToken(session?.access_token ?? null)
      setLoading(false)
    })

    // Escuchar cambios de sesión (login, logout, token refresh automático)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setToken(session?.access_token ?? null)
    })

    return () => subscription.unsubscribe()
  }, [])

  const handleLogout = async () => {
    await supabase.auth.signOut()
    setToken(null)
    setPage('dashboard')
  }

  if (loading) {
    return <div style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>
  }

  if (!token) return <LoginPage onLogin={setToken} />

  return (
    <div>
      <nav style={{ display: 'flex', alignItems: 'center', width: '100%' }} className="bg-blue-900 text-white px-6 py-3 mb-8">
        <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
          <div className="flex items-center space-x-2">
            <img src={logo} alt="Nementium.ai" className="h-6 object-contain" />
          </div>

          <div className="flex space-x-6">
            <button
              onClick={() => {
                setPage('dashboard')
                setDashboardKey(prev => prev + 1)
              }}
              className={`navlink ${page === 'dashboard' ? 'active' : ''}`}
              aria-current={page === 'dashboard' ? 'page' : undefined}
            >
              Dashboard
            </button>
            <button
              onClick={() => setPage('upload')}
              className={`navlink ${page === 'upload' ? 'active' : ''}`}
              aria-current={page === 'upload' ? 'page' : undefined}
            >
              Subir factura/ventas
            </button>
            <button
              onClick={() => setPage('estado')}
              className={`navlink ${page === 'estado' ? 'active' : ''}`}
              aria-current={page === 'estado' ? 'page' : undefined}
            >
              Estado trimestral
            </button>
            <button
              onClick={() => setPage('mesdetalle')}
              className={`navlink ${page === 'mesdetalle' ? 'active' : ''}`}
              aria-current={page === 'mesdetalle' ? 'page' : undefined}
            >
              Histórico
            </button>
            <button
              onClick={() => setPage('crear-factura')}
              className={`navlink ${page === 'crear-factura' ? 'active' : ''}`}
              aria-current={page === 'crear-factura' ? 'page' : undefined}
            >
              Crear Facturas
            </button>
            <button
              onClick={() => setPage('consulta')}
              className={`navlink ${page === 'consulta' ? 'active' : ''}`}
              aria-current={page === 'consulta' ? 'page' : undefined}
            >
              Consulta
            </button>
            <button
              onClick={() => setPage('rentabilidad')}
              className={`navlink ${page === 'rentabilidad' ? 'active' : ''}`}
              aria-current={page === 'rentabilidad' ? 'page' : undefined}
            >
              Rentabilidad
            </button>
            <button
              onClick={() => setPage('mesdetalle')}
              className={`navlink ${page === 'mesdetalle' ? 'active' : ''}`}
              aria-current={page === 'mesdetalle' ? 'page' : undefined}
            >
              Notificaciones (2)
            </button>
            <button
              onClick={() => setPage('mesdetalle')}
              className={`navlink ${page === 'mesdetalle' ? 'active' : ''}`}
              aria-current={page === 'mesdetalle' ? 'page' : undefined}
            >
              Documentos presentados
            </button>
          </div>
        </div>

        <div style={{ flex: 1 }}></div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginRight: '3rem' }}>
          <button
            type="button"
            className="navlink p-1"
            aria-label="Usuario"
            title="Usuario"
          >
            <User className="w-5 h-5" />
          </button>
          <button
            onClick={handleLogout}
            className="navlink p-1"
            aria-label="Salir"
            title="Salir"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </nav>

      <main style={{ marginTop: '4rem' }}>
        {page === 'dashboard' && <DashboardPage key={dashboardKey} token={token} onLogout={handleLogout} />}
        {page === 'upload' && <UploadPage token={token} onLogout={handleLogout} />}
        {page === 'estado' && <EstadoModelosPage token={token} onLogout={handleLogout} />}
        {page === 'mesdetalle' && <MesDetallePage token={token} onLogout={handleLogout} />}
        {page === 'crear-factura' && <CreateInvoicePage token={token} onLogout={handleLogout} />}
        {page === 'consulta' && <ConsultaPage token={token} onLogout={handleLogout} />}
        {page === 'rentabilidad' && <RentabilidadPage token={token} onLogout={handleLogout} />}
      </main>

      <ChatAssistant token={token} onLogout={handleLogout} />
    </div>
  )
}

export default App

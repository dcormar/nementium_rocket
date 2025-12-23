import { useState, useEffect } from 'react'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import UploadPage from './pages/UploadPage'
import EstadoModelosPage from './pages/EstadoModelosPage'
import MesDetallePage from './pages/MesDetallePage'
import './App.css'

// Importamos el logo desde src/assets
import logo from './assets/logo.png'
// Iconos
import { LogOut, User } from 'lucide-react'
import { fetchWithAuth } from './utils/fetchWithAuth'

function App() {
  const [token, setToken] = useState<string | null>(null)
  const [page, setPage] = useState('dashboard')
  const [checkingToken, setCheckingToken] = useState(false)

  const handleLogout = () => {
    setToken(null)
    setPage('dashboard')
  }

  // Verificar si el token es válido cuando cambia el token, la página, o al montar
  useEffect(() => {
    if (!token) return

    const verifyToken = async () => {
      setCheckingToken(true)
      try {
        const response = await fetchWithAuth('http://localhost:8000/auth/me', {
          token,
          onLogout: handleLogout,
        })
        if (!response.ok) {
          // Si el token no es válido, handleLogout ya fue llamado por fetchWithAuth
          return
        }
      } catch (error) {
        // Si hay un error de red, también cerramos sesión por seguridad
        console.error('Error verificando token:', error)
        handleLogout()
      } finally {
        setCheckingToken(false)
      }
    }

    verifyToken()
  }, [token, page]) // Verificar cuando cambia el token o la página

  // También verificar periódicamente cada 5 minutos
  useEffect(() => {
    if (!token) return

    const interval = setInterval(async () => {
      try {
        const response = await fetchWithAuth('http://localhost:8000/auth/me', {
          token,
          onLogout: handleLogout,
        })
        if (!response.ok) {
          // Si el token no es válido, handleLogout ya fue llamado por fetchWithAuth
          return
        }
      } catch (error) {
        console.error('Error verificando token periódicamente:', error)
        handleLogout()
      }
    }, 5 * 60 * 1000) // Cada 5 minutos

    return () => clearInterval(interval)
  }, [token])

  if (!token) return <LoginPage onLogin={setToken} />
  
  if (checkingToken) {
    return <div style={{ padding: '2rem', textAlign: 'center' }}>Verificando sesión...</div>
  }

  return (
    <div>
      <nav style={{ display: 'flex', alignItems: 'center', width: '100%' }} className="bg-blue-900 text-white px-6 py-3 mb-8">
        {/* Logo y Menú juntos a la izquierda */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
          {/* Logo */}
          <div className="flex items-center space-x-2">
            <img src={logo} alt="Nementium.ai" className="h-6 object-contain" />
          </div>

          {/* Menú junto al logo */}
          <div className="flex space-x-6">
            <button
              onClick={() => setPage('dashboard')}
              className={`navlink ${page === 'dashboard' ? 'active' : ''}`}
              aria-current={page === 'dashboard' ? 'page' : undefined}
            >
              Dashboard
            </button>
            <button
              onClick={() => setPage('upload')}
              className={`navlink ${page === 'upload' ? 'active' : ''}`}
              aria-current={page === 'upload' ? 'page' : undefined}å
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

        {/* Espacio flexible para empujar los botones a la derecha */}
        <div style={{ flex: 1 }}></div>

        {/* Botones a la derecha - siempre dentro de la imagen */}
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
        {page === 'dashboard' && <DashboardPage token={token} onLogout={handleLogout} />}
        {page === 'upload' && <UploadPage token={token} onLogout={handleLogout} />}
        {page === 'estado' && <EstadoModelosPage token={token} onLogout={handleLogout} />}
        {page === 'mesdetalle' && <MesDetallePage token={token} onLogout={handleLogout} />}
      </main>
    </div>
  )
}

export default App
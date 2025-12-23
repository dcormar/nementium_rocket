import { useState } from 'react'
import logologin from '../assets/logo-login.png'


export default function LoginPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [email, setEmail] = useState('demo@demo.com')
  const [password, setPassword] = useState('demo')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await fetch('http://localhost:8000/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password, grant_type: 'password' })
      })
      if (!res.ok) throw new Error('Login incorrecto')
      const data = await res.json()
      onLogin(data.access_token)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        padding: '2rem',
      }}
    >
      <div 
        className="login-page"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          margin: '0 auto',
          padding: '2rem',
          width: '100%',
          maxWidth: '400px',
          background: '#ffffff',
          borderRadius: '12px',
          boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
        }}
      >
        <img 
          src={logologin} 
          alt="Logo" 
          style={{
            width: '200px',
            height: 'auto',
            marginBottom: '2rem',
            maxWidth: '100%',
          }}
        />
        <h2 
          style={{ 
            textAlign: 'center', 
            marginBottom: '2rem', 
            fontSize: '1.875rem',
            fontWeight: 700,
            background: 'linear-gradient(135deg, #3631a3 0%, #092342 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            letterSpacing: '-0.02em',
          }}
        >
          Iniciar sesión
        </h2>
        <form onSubmit={handleSubmit} style={{ width: '100%' }}>
          <label 
            style={{ 
              display: 'block', 
              marginBottom: '0.5rem', 
              color: '#3631a3',
              fontSize: '0.875rem',
              fontWeight: 600,
              letterSpacing: '0.025em',
              textTransform: 'uppercase',
            }}
          >
            Email
          </label>
          <input
              type="email"
              name="username"
              autoComplete="username"
              placeholder="Email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.75rem',
                marginBottom: '1rem',
                borderRadius: '6px',
                border: '1px solid #d1d5db',
                background: '#ffffff',
                color: '#222',
                fontSize: '1rem',
                boxSizing: 'border-box',
              }}
          />
          <label 
            style={{ 
              display: 'block', 
              marginBottom: '0.5rem', 
              color: '#3631a3',
              fontSize: '0.875rem',
              fontWeight: 600,
              letterSpacing: '0.025em',
              textTransform: 'uppercase',
            }}
          >
            Password
          </label>
          <input
              type="password"
              name="password"
              autoComplete="current-password"
              placeholder="Contraseña"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.75rem',
                marginBottom: '1rem',
                borderRadius: '6px',
                border: '1px solid #d1d5db',
                background: '#ffffff',
                color: '#222',
                fontSize: '1rem',
                boxSizing: 'border-box',
              }}
          />
          <button 
            type="submit" 
            disabled={loading}
            style={{
              width: '100%',
              backgroundColor: '#3631a3',
              color: '#ffffff',
            }}
          >
              {loading ? 'Entrando...' : 'Entrar'}
          </button>
          {error && <div className="error" style={{ marginTop: '1rem', color: '#ff6b6b' }}>{error}</div>}
        </form>
      </div>
    </div>
  )
}

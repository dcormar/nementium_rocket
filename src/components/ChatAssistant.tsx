import { useState, useRef, useEffect } from 'react'
import { MessageCircle, X, Send, Loader2, Bot, User, CheckCircle2 } from 'lucide-react'
import { fetchWithAuth } from '../utils/fetchWithAuth'

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  actions?: Array<{ tool: string; timestamp: string }>
}

type ChatAssistantProps = {
  token: string
  onLogout?: () => void
}

export default function ChatAssistant({ token, onLogout }: ChatAssistantProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasUnread, setHasUnread] = useState(false)
  const [expandedActions, setExpandedActions] = useState<Set<string>>(new Set())
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll al final cuando hay nuevos mensajes
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  // Focus en input cuando se abre el chat
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  // Mensaje de bienvenida (solo si no hay mensajes y no hay acciones previas)
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: '¡Hola! 👋 Soy tu asistente de Nementium.ai. Puedo ayudarte con:\n\n• Preguntas sobre cómo usar la aplicación\n• Información sobre modelos tributarios y plazos\n• Dudas sobre Hacienda y Seguridad Social\n• Enviar notificaciones a tus contactos\n\n¿En qué puedo ayudarte?',
        timestamp: new Date()
      }])
    }
  }, [])

  // Mensaje más conciso después de acciones
  const getWelcomeMessage = () => {
    const hasActions = messages.some(m => m.actions && m.actions.length > 0)
    if (hasActions) {
      return '¿En qué más puedo ayudarte?'
    }
    return '¡Hola! 👋 Soy tu asistente de Nementium.ai. Puedo ayudarte con:\n\n• Preguntas sobre cómo usar la aplicación\n• Información sobre modelos tributarios y plazos\n• Dudas sobre Hacienda y Seguridad Social\n• Enviar notificaciones a tus contactos\n\n¿En qué puedo ayudarte?'
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      // Preparar historial para la API
      const conversationHistory = messages.slice(-10).map(m => ({
        role: m.role,
        content: m.content
      }))

      const response = await fetchWithAuth('http://localhost:8000/assistant/chat', {
        token,
        onLogout,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input.trim(),
          conversation_history: conversationHistory
        })
      })

      if (!response.ok) {
        throw new Error(`Error ${response.status}`)
      }

      const data = await response.json()

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.response,
        timestamp: new Date(),
        actions: data.actions_executed
      }

      setMessages(prev => [...prev, assistantMessage])

      // Si el chat está cerrado, marcar como no leído
      if (!isOpen) {
        setHasUnread(true)
      }

      // Volver a enfocar el input después de recibir la respuesta
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus()
        }
      }, 100)

    } catch (error: any) {
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Lo siento, ha ocurrido un error: ${error.message}. Por favor, intenta de nuevo.`,
        timestamp: new Date()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const toggleChat = () => {
    setIsOpen(!isOpen)
    if (!isOpen) {
      setHasUnread(false)
    }
  }

  // Formatear contenido con saltos de línea
  const formatContent = (content: string) => {
    return content.split('\n').map((line, i) => (
      <span key={i}>
        {line}
        {i < content.split('\n').length - 1 && <br />}
      </span>
    ))
  }

  return (
    <>
      {/* Botón flotante */}
      <button
        onClick={toggleChat}
        style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          width: '60px',
          height: '60px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)',
          color: 'white',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(37, 99, 235, 0.4)',
          transition: 'transform 0.2s, box-shadow 0.2s',
          zIndex: 9999,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'scale(1.1)'
          e.currentTarget.style.boxShadow = '0 6px 24px rgba(37, 99, 235, 0.5)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'scale(1)'
          e.currentTarget.style.boxShadow = '0 4px 20px rgba(37, 99, 235, 0.4)'
        }}
        aria-label={isOpen ? 'Cerrar asistente' : 'Abrir asistente'}
      >
        {isOpen ? (
          <X size={28} />
        ) : (
          <>
            <MessageCircle size={28} />
            {hasUnread && (
              <span
                style={{
                  position: 'absolute',
                  top: '8px',
                  right: '8px',
                  width: '12px',
                  height: '12px',
                  background: '#ef4444',
                  borderRadius: '50%',
                  border: '2px solid white',
                }}
              />
            )}
          </>
        )}
      </button>

      {/* Panel del chat */}
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            bottom: '100px',
            right: '24px',
            width: '400px',
            maxWidth: 'calc(100vw - 48px)',
            height: '550px',
            maxHeight: 'calc(100vh - 140px)',
            background: 'white',
            borderRadius: '16px',
            boxShadow: '0 10px 40px rgba(0, 0, 0, 0.15)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            zIndex: 9998,
            animation: 'slideUp 0.3s ease-out',
          }}
        >
          {/* Header */}
          <div
            style={{
              background: 'linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)',
              color: 'white',
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                background: 'rgba(255,255,255,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Bot size={24} />
            </div>
            <div>
              <h3 style={{ 
                margin: 0, 
                fontSize: '16px', 
                fontWeight: 600,
                color: '#ffffff',
                textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
              }}>
                Asistente Nementium
              </h3>
              <p style={{ 
                margin: 0, 
                fontSize: '12px', 
                color: 'rgba(255, 255, 255, 0.95)',
                textShadow: '0 1px 1px rgba(0, 0, 0, 0.2)'
              }}>
                Siempre disponible para ayudarte
              </p>
            </div>
          </div>

          {/* Mensajes */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              background: '#f8fafc',
            }}
          >
            {messages.map((message) => (
              <div
                key={message.id}
                style={{
                  display: 'flex',
                  flexDirection: message.role === 'user' ? 'row-reverse' : 'row',
                  gap: '8px',
                  alignItems: 'flex-start',
                }}
              >
                {/* Avatar */}
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: message.role === 'user' ? '#e5e7eb' : '#2563eb',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  {message.role === 'user' ? (
                    <User size={16} color="#6b7280" />
                  ) : (
                    <Bot size={16} color="white" />
                  )}
                </div>

                {/* Burbuja */}
                <div
                  style={{
                    maxWidth: '80%',
                    padding: '12px 16px',
                    borderRadius: message.role === 'user' 
                      ? '16px 16px 4px 16px' 
                      : '16px 16px 16px 4px',
                    background: message.role === 'user' ? '#2563eb' : 'white',
                    color: message.role === 'user' ? 'white' : '#1f2937',
                    fontSize: '14px',
                    lineHeight: '1.5',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                  }}
                >
                  {formatContent(message.content)}

                  {/* Acciones ejecutadas - Pestaña replegable */}
                  {message.actions && message.actions.length > 0 && (
                    <div
                      style={{
                        marginTop: '8px',
                        paddingTop: '8px',
                        borderTop: '1px solid #e5e7eb',
                      }}
                    >
                      <button
                        onClick={() => {
                          const newExpanded = new Set(expandedActions)
                          if (newExpanded.has(message.id)) {
                            newExpanded.delete(message.id)
                          } else {
                            newExpanded.add(message.id)
                          }
                          setExpandedActions(newExpanded)
                        }}
                        style={{
                          width: '100%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '6px 8px',
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          borderRadius: '8px',
                          fontSize: '11px',
                          color: '#166534',
                          fontWeight: 500,
                          transition: 'background 0.2s',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = '#f0fdf4'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'transparent'
                        }}
                      >
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <CheckCircle2 size={12} />
                          {message.actions.length} herramienta{message.actions.length > 1 ? 's' : ''} usada{message.actions.length > 1 ? 's' : ''}
                        </span>
                        <span style={{ fontSize: '10px' }}>
                          {expandedActions.has(message.id) ? '▼' : '▶'}
                        </span>
                      </button>
                      {expandedActions.has(message.id) && (
                        <div
                          style={{
                            marginTop: '6px',
                            display: 'flex',
                            flexWrap: 'wrap',
                            gap: '4px',
                          }}
                        >
                          {message.actions.map((action, i) => (
                            <span
                              key={i}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                                padding: '2px 8px',
                                background: '#dcfce7',
                                color: '#166534',
                                borderRadius: '12px',
                                fontSize: '11px',
                              }}
                            >
                              <CheckCircle2 size={12} />
                              {action.tool}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Indicador de escribiendo */}
            {isLoading && (
              <div
                style={{
                  display: 'flex',
                  gap: '8px',
                  alignItems: 'flex-start',
                }}
              >
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: '#2563eb',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Bot size={16} color="white" />
                </div>
                <div
                  style={{
                    padding: '12px 16px',
                    borderRadius: '16px 16px 16px 4px',
                    background: 'white',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <Loader2 size={16} className="animate-spin" style={{ color: '#2563eb' }} />
                  <span style={{ fontSize: '14px', color: '#6b7280' }}>
                    Pensando...
                  </span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            style={{
              padding: '16px',
              borderTop: '1px solid #e5e7eb',
              background: 'white',
              display: 'flex',
              gap: '8px',
              alignItems: 'flex-end',
            }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Escribe tu mensaje..."
              disabled={isLoading}
              rows={1}
              style={{
                flex: 1,
                padding: '12px 16px',
                borderRadius: '24px',
                border: '1px solid #e5e7eb',
                fontSize: '14px',
                resize: 'none',
                maxHeight: '120px',
                outline: 'none',
                fontFamily: 'inherit',
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = '#2563eb'
                e.currentTarget.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.1)'
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = '#e5e7eb'
                e.currentTarget.style.boxShadow = 'none'
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              style={{
                width: '44px',
                height: '44px',
                borderRadius: '50%',
                background: input.trim() && !isLoading ? '#2563eb' : '#e5e7eb',
                color: input.trim() && !isLoading ? 'white' : '#9ca3af',
                border: 'none',
                cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background 0.2s',
              }}
            >
              <Send size={22} />
            </button>
          </form>
        </div>
      )}

      {/* Estilos de animación */}
      <style>{`
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </>
  )
}

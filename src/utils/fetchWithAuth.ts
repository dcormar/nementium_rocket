/**
 * Wrapper de fetch que inyecta el token de Supabase Auth
 * y detecta respuestas 401 para disparar logout.
 */

export async function fetchWithAuth(
  url: string,
  options: RequestInit & { token?: string; onLogout?: () => void } = {}
): Promise<Response> {
  const { token, onLogout, ...fetchOptions } = options

  const headers = new Headers(fetchOptions.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  })

  // 401 = token inválido o expirado → logout silencioso
  if (response.status === 401 && onLogout) {
    onLogout()
  }

  return response
}

/**
 * Wrapper de fetch que detecta errores 401 (token expirado)
 * y llama a onLogout para redirigir al usuario al login
 */
export async function fetchWithAuth(
  url: string,
  options: RequestInit & { token?: string; onLogout?: () => void } = {}
): Promise<Response> {
  const { token, onLogout, ...fetchOptions } = options;

  // Agregar el token al header si está presente
  const headers = new Headers(fetchOptions.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  // Si recibimos un 401, el token ha expirado
  if (response.status === 401 && onLogout) {
    // Mostrar mensaje al usuario antes de redirigir
    alert('Tu sesión ha expirado. Por favor, inicia sesión nuevamente.');
    onLogout();
  }

  return response;
}


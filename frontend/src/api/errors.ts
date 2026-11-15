export interface ApiError {
  code: string
  message: string
  field: string | null
}

export async function readApiError(response: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await response.json()
  }
  catch {
    body = null
  }
  return normalizeApiError(body, response.status, response.statusText)
}

export function normalizeApiError(body: unknown, status: number, statusText = ''): ApiError {
  const error: ApiError = {
    code: `http.${status}`,
    message: statusText || 'Request failed.',
    field: null,
  }
  if (typeof body !== 'object' || body === null)
    return error
  if ('code' in body && typeof body.code === 'string')
    error.code = body.code
  if ('message' in body && typeof body.message === 'string')
    error.message = body.message
  if ('field' in body && typeof body.field === 'string')
    error.field = body.field
  return error
}

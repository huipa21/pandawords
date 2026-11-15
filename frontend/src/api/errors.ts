export interface ApiError {
  code: string
  message: string
  field: string | null
  /** Bundle rejections: failed stage and short, path-free problems safe to show. */
  stage?: string
  problems?: string[]
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
  if ('stage' in body && typeof body.stage === 'string')
    error.stage = body.stage
  if ('problems' in body && Array.isArray(body.problems))
    error.problems = body.problems.filter((problem): problem is string => typeof problem === 'string').slice(0, 20)
  return error
}

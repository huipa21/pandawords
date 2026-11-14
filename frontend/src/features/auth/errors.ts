import type { ApiError } from '@/api/client'

export class AuthRequestError extends Error {
  constructor(readonly error: ApiError) {
    super(error.code)
  }
}

export function transportError(): never {
  throw new AuthRequestError({ code: 'transport', message: '', field: null })
}

export function errorKey(code: string) {
  return `errors.${code.replaceAll('.', '_')}`
}

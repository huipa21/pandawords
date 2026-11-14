import type { components } from '../src/api/schema'
import { Buffer } from 'node:buffer'
import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { createApiClient } from '../src/api/client'
import { fillCredential, login, requiredCredential } from './review-session.helpers'

// An answer-free calendar, not a filename/alt/source containing the fixture answer.
const CALENDAR = 'iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAIAAABt+uBvAAABNUlEQVR4nO3bQW6DMBRAwbjK/a/s7koXhpeERWgzs0VWpCeD8BcZc84b+74OriFQs4OCQEGgIFAQKAgUBAoCBYHCfe/CGLX031meSu2gIFAQKAgUBAoCBYGCQEGgIFAQKAgUBAoCBYGCQEGg9wQaf3DtkyPXnx+bz38fM8Z6fHnNtWObLi8Wu8WCQEGgIFAQKAgUBAoCBYGCQEGgIFAQKIy9w/qvM+6nWKa4v7bs2Bi73S+49ngruMWCQKFvsVMef5Bd9X99dlAQKAgUBAoCBYGCQO99D5oXfbt5nB0UBArGHRvjjjXjjlM8g4JAQaAgUBAoCBQECgIFgYJAQaAgUDDu2Bh3rBl3nOIZFAQKAgWBgkBBoCBQECg4asRRww4KAoXXv/v/EHZQECgIFAQKAgWBbse+AY3DUrjVhP21AAAAAElFTkSuQmCC'

test('fixture image review authenticates blobs, persists preferences and confirms exactly once after retry', async ({ page, baseURL }) => {
  test.setTimeout(120_000)
  expect(process.env.LLM_DAILY_BUDGET).toBe('0')
  expect(process.env.AUDIO_NETWORK_ENABLED).toBe('false')
  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ theme: 'system', locale: 'en' }))
  })
  await page.goto('/login')
  const admin = await login(page, requiredCredential('ADMIN_USERNAME'), requiredCredential('ADMIN_PASSWORD'))
  await expect(page).toHaveURL('/projects')
  const adminApi = createApiClient({
    baseUrl: baseURL,
    auth: {
      getAccessToken: () => admin.access_token,
      refresh: async () => null,
      logout: () => {},
    },
  })
  let learnerId: string | undefined
  let projectId: string | undefined
  let senseId: string | undefined
  let imageId: string | undefined
  let api: ReturnType<typeof createApiClient> | undefined
  try {
    const username = `e2e_image_${randomUUID().replaceAll('-', '')}`
    const created = await adminApi.POST('/api/admin/users', {
      body: { username, role: 'user' },
    })
    const learner = created.data
    expect(created.response.ok).toBe(true)
    if (!learner?.temporary_password || learner.user.id === admin.user.id)
      throw new Error('An isolated learner and temporary password are required.')
    learnerId = learner.user.id
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page).toHaveURL('/login')
    await login(page, username, learner.temporary_password)
    await expect(page).toHaveURL('/change-password')
    await fillCredential(page.getByLabel(/^Current password\b/), learner.temporary_password)
    await fillCredential(page.getByLabel(/^New password\b/), randomUUID())
    const changed = page.waitForResponse(response => response.url().endsWith('/api/auth/password') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Change password', exact: true }).click()
    const changedResponse = await changed
    expect(changedResponse.ok()).toBe(true)
    const auth = await changedResponse.json() as components['schemas']['AuthRead']
    expect(auth.user.id).toBe(learnerId)
    await expect(page).toHaveURL('/projects')
    api = createApiClient({
      baseUrl: baseURL,
      auth: {
        getAccessToken: () => auth.access_token,
        refresh: async () => null,
        logout: () => {},
      },
    })
    const project = await api.POST('/api/projects', {
      body: {
        name: `e2e-image-${randomUUID()}`,
        description: '',
        target_lang: 'en',
        source_lang: 'zh',
      },
    })
    projectId = project.data?.id
    if (!projectId)
      throw new Error('Missing isolated project.')
    const candidate = await api.POST('/api/dictionary/candidates', {
      body: { text: 'schedule' },
    })
    const word = candidate.data?.candidates[0]
    const sense = word?.lexemes[0]?.senses[0]
    if (!word || !sense)
      throw new Error('Run with the offline fixture lexicon containing schedule.')
    const added = await api.POST('/api/projects/{id}/dictionary', {
      params: {
        path: { id: projectId },
      },
      body: {
        lemma_key: word.lemma.id,
        selected_senses: [sense.id],
      },
    })
    senseId = added.data?.selected_sense_ids?.[0]
    if (!senseId)
      throw new Error('Missing fixture sense.')
    // Legitimate private content leaves only image recall eligible; no random/bypass flag.
    const overridden = await api.PUT('/api/dictionary/{table}/{id}/override', {
      params: {
        path: { table: 'sense', id: senseId },
      },
      body: {
        fields: {
          definition: '',
          gloss: { zh: '' },
          examples: [],
        },
      },
    })
    expect(overridden.response.ok).toBe(true)
    execFileSync('uv', [
      'run',
      '--no-sync',
      'python',
      '-m',
      'scripts.seed_image_review',
      learnerId,
      projectId,
      senseId,
    ], {
      cwd: `${fileURLToPath(new URL('../..', import.meta.url))}\\backend`,
      env: process.env,
      stdio: 'pipe',
    })
    const uploaded = await page.request.post(`/api/images/senses/${encodeURIComponent(senseId)}`, {
      headers: {
        'Authorization': `Bearer ${auth.access_token}`,
        'Content-Type': 'image/png',
        'request-id': randomUUID().replaceAll('-', ''),
      },
      data: Buffer.from(CALENDAR, 'base64'),
    })
    expect(uploaded.ok()).toBe(true)
    imageId = (await uploaded.json() as components['schemas']['MediaRead']).id
    await page.goto(`/projects/${encodeURIComponent(projectId)}/plan`)
    const settings = page.getByTestId('review-media-settings')
    const images = settings.getByRole('switch', { name: 'Enable image exercises', exact: true })
    const audio = settings.getByRole('switch', { name: 'Enable audio exercises', exact: true })
    await expect(images).toHaveAttribute('aria-checked', 'true')
    await expect(audio).toHaveAttribute('aria-checked', 'true')
    await images.focus()
    await page.keyboard.press('Space')
    await audio.focus()
    await page.keyboard.press('Space')
    await settings.getByRole('radio', { name: 'British English', exact: true }).check()
    await settings.getByRole('button', { name: 'Save review media preferences', exact: true }).click()
    await expect(settings.getByRole('status')).toContainText('Saved.')
    const disabled = await api.GET('/api/auth/me/review-preferences')
    expect(disabled.data).toEqual({ review_images_enabled: false, review_audio_enabled: false, accent: 'UK' })
    const unavailable = await api.POST('/api/exercise-attempts', {
      body: { project_id: projectId, sense_id: senseId },
    })
    expect(unavailable.response.status).toBe(409)
    await images.focus()
    await page.keyboard.press('Space')
    const saved = page.waitForResponse(response => response.url().endsWith('/api/auth/me/review-preferences') && response.request().method() === 'PATCH')
    await settings.getByRole('button', { name: 'Save review media preferences', exact: true }).click()
    expect((await saved).ok()).toBe(true)
    const mediaPath = `**/api/media/${encodeURIComponent(imageId)}`
    await page.route(mediaPath, route => route.fulfill({
      status: 404,
      json: { code: 'media.not_found' },
    }), { times: 1 })
    const issuance = page.waitForResponse(response => response.url().endsWith('/api/exercise-attempts') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Start review', exact: true }).click()
    const issued = await issuance
    expect(issued.ok()).toBe(true)
    const attempt = await issued.json() as components['schemas']['AttemptRead']
    expect(attempt.exercise).toBe('image2word')
    expect(attempt.prompt.media_id).toBe(imageId)
    expect(JSON.stringify(attempt.prompt).toLowerCase()).not.toContain('schedule')
    const exercise = page.getByTestId('review-exercise')
    const imageRegion = page.getByTestId('review-image')
    await expect(imageRegion).toContainText('This image is unavailable.')
    const delivery = page.waitForResponse(response => response.url().includes('/api/media/') && response.ok())
    await imageRegion.getByRole('button', { name: 'Retry', exact: true }).click()
    const delivered = await delivery
    expect(delivered.request().headers().authorization).toBe(`Bearer ${auth.access_token}`)
    const image = imageRegion.getByRole('img', { name: 'Private vocabulary image', exact: true })
    await expect(image).toBeVisible()
    await expect.poll(() => image.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(96)
    const blob = await image.getAttribute('src')
    expect(blob).toMatch(/^blob:/)
    // A changed preference does not invalidate this already-issued image exercise.
    expect((await api.PATCH('/api/auth/me/review-preferences', {
      body: { review_images_enabled: false },
    })).response.ok).toBe(true)
    const removed = await api.DELETE('/api/images/senses/{sense_id}/{image_id}', {
      params: {
        path: { sense_id: senseId, image_id: imageId },
      },
    })
    expect(removed.response.ok).toBe(true)
    imageId = undefined
    await page.reload()
    await expect(imageRegion).toContainText('This image is unavailable.')
    await imageRegion.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(imageRegion).toContainText('This image is unavailable.')
    const input = exercise.getByRole('textbox')
    await input.fill('schedule')
    const grading = page.waitForResponse(response => response.url().endsWith(`/${attempt.id}/answer`) && response.request().method() === 'POST')
    await input.press('Enter')
    expect((await grading).ok()).toBe(true)
    await expect(exercise.getByText('Correct', { exact: true })).toBeVisible()
    const confirmPath = `**/api/exercise-attempts/${attempt.id}/confirm`
    let durable: components['schemas']['AttemptConfirmed'] | undefined
    await page.route(confirmPath, async (route) => {
      const response = await route.fetch()
      durable = await response.json() as components['schemas']['AttemptConfirmed']
      await route.abort('failed')
    }, { times: 1 })
    await exercise.getByRole('button', { name: 'Confirm rating and continue', exact: true }).click()
    await expect(page.getByTestId('review-retry')).toBeVisible()
    await page.getByTestId('review-retry').click()
    await expect(page.getByTestId('review-empty')).toBeVisible()
    expect(durable?.status).toBe('confirmed')
    const recovered = await api.GET('/api/exercise-attempts/{attempt_id}', {
      params: {
        path: { attempt_id: attempt.id },
      },
    })
    if (recovered.data?.status !== 'confirmed' || !durable)
      throw new Error('Confirmation must return the original durable receipt.')
    expect(recovered.data.receipt).toEqual(durable.receipt)
    const plan = await api.GET('/api/projects/{id}/study-plan', {
      params: {
        path: { id: projectId },
      },
    })
    expect(plan.data?.today).toEqual({ new: 0, reviews: 1 })
    await page.reload()
    await expect(page.getByTestId('review-empty')).toBeVisible()
    expect((await api.GET('/api/projects/{id}/study-plan', {
      params: {
        path: { id: projectId },
      },
    })).data?.today).toEqual({ new: 0, reviews: 1 })
  }
  finally {
    try {
      if (api && imageId && senseId) {
        await api.DELETE('/api/images/senses/{sense_id}/{image_id}', {
          params: {
            path: { sense_id: senseId, image_id: imageId },
          },
        })
      }
      if (api && projectId) {
        expect((await api.DELETE('/api/projects/{id}', {
          params: {
            path: { id: projectId },
          },
        })).response.ok).toBe(true)
      }
    }
    finally {
      if (learnerId) {
        const disabled = await adminApi.PATCH('/api/admin/users/{id}', {
          params: {
            path: { id: learnerId },
          },
          body: { disabled: true, reset_password: false },
        })
        expect(disabled.data?.user.disabled).toBe(true)
      }
    }
  }
})

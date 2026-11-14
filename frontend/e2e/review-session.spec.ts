import type { components } from '../src/api/schema'
import { randomUUID } from 'node:crypto'
import process from 'node:process'
import { expect, test } from '@playwright/test'
import { createApiClient } from '../src/api/client'
import { fillCredential, login, requiredCredential } from './review-session.helpers'

const FIXTURE_DEFINITION = 'A plan listing times for activities.'

test('fixture review persists an overridden rating exactly once across reload and confirmation retry', async ({ page, baseURL }) => {
  test.setTimeout(120_000)
  expect(process.env.LLM_DAILY_BUDGET, 'Run the stack and test with LLM disabled.').toBe('0')
  expect(process.env.AUDIO_NETWORK_ENABLED, 'Run the stack and test with external audio disabled.').toBe('false')
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
  let api: ReturnType<typeof createApiClient> | undefined
  try {
    const username = `e2e_review_${randomUUID().replaceAll('-', '')}`
    const created = await adminApi.POST('/api/admin/users', {
      body: { username, role: 'user' },
    })
    expect(created.response.ok, 'Create an isolated learner.').toBe(true)
    const learner = created.data
    if (!learner || learner.user.username !== username || learner.user.id === admin.user.id)
      throw new Error('Creation did not return the isolated review learner.')
    learnerId = learner.user.id
    if (!learner.temporary_password)
      throw new Error('Learner creation must issue a temporary password.')
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page).toHaveURL('/login')
    const pending = await login(page, username, learner.temporary_password)
    expect(pending.user.id === learnerId && pending.user.must_change_password).toBe(true)
    await expect(page).toHaveURL('/change-password')
    await fillCredential(page.getByLabel(/^Current password\b/), learner.temporary_password)
    await fillCredential(page.getByLabel(/^New password\b/), randomUUID())
    const changed = page.waitForResponse(response =>
      response.url().endsWith('/api/auth/password') && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: 'Change password', exact: true }).click()
    const changedResponse = await changed
    expect(changedResponse.ok(), 'Complete the mandatory password change.').toBe(true)
    const auth = await changedResponse.json() as components['schemas']['AuthRead']
    expect(auth.user.id === learnerId && !auth.user.must_change_password).toBe(true)
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
        name: `e2e-review-${randomUUID()}`,
        description: '',
        target_lang: 'en',
        source_lang: 'zh',
        plan: { daily_new: 1, review_cap: null, exam_date: null },
      },
    })
    expect(project.response.ok, 'Create only the isolated review project.').toBe(true)
    projectId = project.data?.id
    if (!projectId)
      throw new Error('Project creation must return its ID.')

    // Fixture nouns share POS and Zipf band 4, so offline fallback choices are safe.
    const senses: string[] = []
    for (const word of [
      'schedule',
      'bank',
      'decision',
      'cat',
    ]) {
      const candidates = await api.POST('/api/dictionary/candidates', {
        body: { text: word },
      })
      expect(candidates.response.ok, `Load fixture candidate: ${word}.`).toBe(true)
      const candidate = candidates.data?.candidates[0]
      const sense = candidate?.lexemes[0]?.senses[0]
      if (!candidate || !sense)
        throw new Error(`Missing fixture noun: ${word}.`)
      const added = await api.POST('/api/projects/{id}/dictionary', {
        params: {
          path: { id: projectId },
        },
        body: {
          lemma_key: candidate.lemma.id,
          selected_senses: [sense.id],
        },
      })
      expect(added.response.ok, `Add fixture noun: ${word}.`).toBe(true)
      const senseId = added.data?.selected_sense_ids?.[0]
      if (!senseId)
        throw new Error(`Adding ${word} must return its selected sense ID.`)
      senses.push(senseId)
    }
    const order = await api.PUT('/api/projects/{id}/study-plan/order', {
      params: {
        path: { id: projectId },
      },
      body: { sense_ids: senses },
    })
    expect(order.response.ok, 'Review the known schedule fixture first.').toBe(true)
    const before = await api.GET('/api/projects/{id}/study-plan', {
      params: {
        path: { id: projectId },
      },
    })
    expect(before.data?.today).toEqual({ new: 0, reviews: 0 })
    expect(before.data?.new).toBe(4)
    expect(before.data?.queue_total).toBe(1)
    expect(before.data?.queue[0]?.memory.sense_id).toBe(senses[0])

    await page.goto(`/projects/${encodeURIComponent(projectId)}`)
    await page.getByRole('button', { name: 'Study plan', exact: true }).click()
    await expect(page.getByTestId('project-plan')).toBeVisible()
    const issuance = page.waitForResponse(response =>
      response.url().endsWith('/api/exercise-attempts') && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: 'Start review', exact: true }).click()
    const issued = await issuance
    expect(issued.ok(), 'Issue a real offline exercise.').toBe(true)
    const attempt = await issued.json() as components['schemas']['AttemptRead']
    expect(attempt.status).toBe('open')
    expect(attempt.sense_id).toBe(senses[0])
    expect(attempt.kind).toBe('recognition')
    expect(attempt.prompt.input).toBe('choice')
    expect(attempt.prompt.choices.length).toBeGreaterThanOrEqual(2)
    // Choose by public exercise type and fixture knowledge, never a private answer key.
    expect(['def2word', 'word2def']).toContain(attempt.exercise)
    const answer = attempt.exercise === 'def2word'
      ? 'schedule'
      : FIXTURE_DEFINITION
    expect(attempt.prompt.text).toContain(attempt.exercise === 'def2word'
      ? FIXTURE_DEFINITION
      : 'schedule')
    const exercise = page.getByTestId('review-exercise')
    await expect(page.getByTestId('review-session')).toBeVisible()
    await expect(exercise).toHaveAttribute('data-attempt-id', attempt.id)
    await expect(exercise).toHaveAttribute('data-status', 'open')
    const choiceIndex = attempt.prompt.choices.findIndex(choice => choice.label === answer)
    expect(choiceIndex, 'A public choice must match the known fixture answer.').toBeGreaterThanOrEqual(0)
    await exercise.getByRole('button', { name: `${choiceIndex + 1}. ${answer}`, exact: true }).click()
    const grading = page.waitForResponse(response =>
      response.url().endsWith(`/${encodeURIComponent(attempt.id)}/answer`) && response.request().method() === 'POST',
    )
    await exercise.getByRole('button', { name: 'Submit answer', exact: true }).click()
    const gradedResponse = await grading
    expect(gradedResponse.ok(), 'Grade the known fixture answer.').toBe(true)
    const graded = await gradedResponse.json() as components['schemas']['AttemptRead']
    if (graded.status !== 'graded')
      throw new Error('Answering must return server feedback.')
    expect(graded.feedback.correct).toBe(true)
    expect(graded.feedback.answer).toBe(answer)
    await expect(exercise).toHaveAttribute('data-status', 'graded')
    await expect(exercise.getByText('Correct', { exact: true })).toBeVisible()
    const ratingNames = ['again', 'hard', 'good', 'easy'] as const
    const suggested = ratingNames[graded.auto_rating - 1]!
    await expect(exercise.locator(`[data-rating="${suggested}"]`)).toHaveAttribute('aria-pressed', 'true')
    await expect(exercise.getByText(`Suggested rating: ${suggested[0]!.toUpperCase()}${suggested.slice(1)}`, { exact: true })).toBeVisible()
    const finalRating = graded.auto_rating === 4
      ? 3
      : 4
    const finalName = ratingNames[finalRating - 1]!
    await exercise.locator(`[data-rating="${finalName}"]`).click()
    await expect(exercise.locator(`[data-rating="${finalName}"]`)).toHaveAttribute('aria-pressed', 'true')
    const confirmation = page.waitForResponse(response =>
      response.url().endsWith(`/${encodeURIComponent(attempt.id)}/confirm`) && response.request().method() === 'POST',
    )
    await exercise.getByRole('button', { name: 'Confirm rating and continue', exact: true }).click()
    const confirmedResponse = await confirmation
    expect(confirmedResponse.ok(), 'Persist the final rating and receipt.').toBe(true)
    const confirmed = await confirmedResponse.json() as components['schemas']['AttemptRead']
    if (confirmed.status !== 'confirmed')
      throw new Error('Confirmation must return a durable receipt.')
    expect(confirmed.receipt.attempt_id).toBe(attempt.id)
    expect(confirmed.receipt.auto_rating).toBe(graded.auto_rating)
    expect(confirmed.receipt.rating).toBe(finalRating)
    expect(confirmed.receipt.correct).toBe(true)
    expect(confirmed.receipt.is_introduction).toBe(true)
    expect(confirmedResponse.request().postDataJSON()).toEqual({ rating: finalRating })
    await expect(page.getByTestId('review-empty')).toBeVisible()
    await expect(page.getByTestId('review-error')).toHaveCount(0)
    await expect(page.getByRole('progressbar', { name: 'Review progress' })).toHaveAttribute('value', '1')

    const after = await api.GET('/api/projects/{id}/study-plan', {
      params: {
        path: { id: projectId },
      },
    })
    expect(after.data?.today).toEqual({ new: 1, reviews: 0 })
    expect(after.data?.new).toBe(3)
    expect(after.data?.remaining_new_allowance).toBe(0)
    expect(after.data?.queue_total).toBe(0)
    expect(after.data?.queue).toEqual([])
    await page.reload()
    await expect(page.getByTestId('review-empty')).toBeVisible()
    await expect(page.getByRole('progressbar', { name: 'Review progress' })).toHaveAttribute('value', '1')
    await expect(page.getByText('1 new · 0 review', { exact: true })).toBeVisible()
    const recovered = await api.GET('/api/exercise-attempts/{attempt_id}', {
      params: {
        path: { attempt_id: attempt.id },
      },
    })
    expect(recovered.data?.status).toBe('confirmed')
    if (recovered.data?.status !== 'confirmed')
      throw new Error('Reload must retain the confirmed attempt.')
    expect(recovered.data.receipt).toEqual(confirmed.receipt)
    const retried = await api.POST('/api/exercise-attempts/{attempt_id}/confirm', {
      params: {
        path: { attempt_id: attempt.id },
      },
      body: { rating: finalRating },
    })
    expect(retried.response.ok, 'An identical confirmation retry must succeed.').toBe(true)
    if (retried.data?.status !== 'confirmed')
      throw new Error('Retry must recover the same durable receipt.')
    expect(retried.data.receipt).toEqual(confirmed.receipt)
    const afterRetry = await api.GET('/api/projects/{id}/study-plan', {
      params: {
        path: { id: projectId },
      },
    })
    expect(afterRetry.data?.today).toEqual(after.data?.today)
    expect(afterRetry.data?.new).toBe(3)
    expect(afterRetry.data?.queue_total).toBe(0)
    await page.reload()
    await expect(page.getByTestId('review-empty')).toBeVisible()
    await expect(page.getByRole('progressbar', { name: 'Review progress' })).toHaveAttribute('value', '1')
  }
  finally {
    // Disable the learner even if project cleanup fails; retain their review history.
    try {
      if (projectId && api) {
        const removed = await api.DELETE('/api/projects/{id}', {
          params: {
            path: { id: projectId },
          },
        })
        expect(removed.response.ok, 'Delete only the isolated review project.').toBe(true)
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
        expect(disabled.data?.user.disabled === true, 'Disable only the isolated review learner.').toBe(true)
      }
    }
  }
})

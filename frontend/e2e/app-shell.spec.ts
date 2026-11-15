import type { Page } from '@playwright/test'
import type { components } from '../src/api/schema'
import { Buffer } from 'node:buffer'
import { expect, test } from '@playwright/test'

async function openShell(page: Page, locale: 'en' | 'zh-CN') {
  const session: components['schemas']['AuthRead'] = {
    access_token: 'ui-layout-test',
    token_type: 'bearer',
    user: {
      id: 'user:ui-layout-test',
      username: 'ui-layout-test',
      email: '',
      full_name: '',
      avatar: '',
      role: 'user',
      disabled: false,
      must_change_password: false,
      source_lang: 'zh',
      target_lang: 'en',
      prefs: {
        theme: 'light',
        locale,
        accent: 'US',
        desired_retention: 0.9,
        review_images_enabled: true,
        review_audio_enabled: true,
      },
    },
  }
  await page.addInitScript((language) => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ theme: 'light', locale: language }))
  }, locale)
  await page.route(url => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') {
      await route.fulfill({ json: session })
    }
    else if (path === '/api/auth/me/profile') {
      const body: components['schemas']['ProfileUpdate'] = route.request().postDataJSON()
      if (body.email === 'fail@example.com') {
        await route.fulfill({
          status: 503,
          json: { code: 'generic', message: 'Failed' },
        })
        return
      }
      session.user = {
        ...session.user,
        ...body,
      }
      await route.fulfill({ json: session.user })
    }
    else if (path === '/api/auth/password') {
      session.access_token = 'rotated-ui-layout-test'
      await route.fulfill({ json: session })
    }
    else if (path === '/api/auth/logout') {
      await route.fulfill({ status: 204 })
    }
    else if (path === '/api/projects') {
      await route.fulfill({
        json: {
          items: [],
          page: 1,
          page_size: 20,
          total: 0,
        },
      })
    }
    else {
      await route.abort()
      throw new Error(`Unexpected API request in UI-only test: ${path}`)
    }
  })
  await page.goto('/projects')
  await expect(page.getByTestId('projects-page')).toBeVisible()
}

for (const locale of ['en', 'zh-CN'] as const) {
  test(`desktop shell separates panels and left-aligns menu labels (${locale})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await openShell(page, locale)
    const header = page.getByRole('banner')
    const sidebar = page.locator('aside')
    const main = page.locator('#main-content')
    const headerBox = await header.boundingBox()
    const sidebarBox = await sidebar.boundingBox()
    const mainBox = await main.boundingBox()
    expect(headerBox).not.toBeNull()
    expect(sidebarBox).not.toBeNull()
    expect(mainBox).not.toBeNull()
    expect(headerBox!.x).toBeGreaterThan(0)
    expect(headerBox!.y).toBeGreaterThan(0)
    expect(sidebarBox!.y).toBeGreaterThan(headerBox!.y + headerBox!.height)
    expect(mainBox!.x).toBeGreaterThan(sidebarBox!.x + sidebarBox!.width)
    expect(mainBox!.y).toBe(sidebarBox!.y)
    expect(mainBox!.x + mainBox!.width).toBeCloseTo(headerBox!.x + headerBox!.width)
    await expect(page.locator('.bg-page').first()).toHaveCSS('background-color', 'rgb(238, 238, 238)')
    for (const panel of [header, sidebar, main]) {
      const style = await panel.evaluate(element => ({
        radius: Number.parseFloat(getComputedStyle(element).borderRadius),
        background: getComputedStyle(element).backgroundColor,
      }))
      expect(style.radius).toBeGreaterThan(0)
      expect(style.background).toBe('rgb(255, 255, 255)')
    }
    const brand = header.getByRole('link', { name: 'PandaWords', exact: true })
    const iconBox = await brand.locator('svg').boundingBox()
    expect(iconBox).not.toBeNull()
    const labelStart = await brand.evaluate((element) => {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
      while (walker.nextNode()) {
        if (walker.currentNode.textContent?.includes('PandaWords')) {
          const range = document.createRange()
          range.selectNodeContents(walker.currentNode)
          return range.getBoundingClientRect().left
        }
      }
      throw new Error('Missing brand text')
    })
    expect(iconBox!.x + iconBox!.width).toBeLessThanOrEqual(labelStart)
    const links = sidebar.locator('a')
    for (const link of await links.all()) {
      const icon = await link.locator('svg').boundingBox()
      const box = await link.boundingBox()
      expect(icon!.x - box!.x).toBeGreaterThanOrEqual(0)
      expect(icon!.x - box!.x).toBeLessThanOrEqual(16)
      expect(box!.height).toBeGreaterThanOrEqual(44)
    }
    await expect(sidebar.locator('[aria-current="page"]')).toHaveAttribute('href', '/projects')
    const active = await sidebar.locator('[aria-current="page"]').evaluate(element => ({
      foreground: getComputedStyle(element).color,
      background: getComputedStyle(element).backgroundColor,
    }))
    expect(active).toEqual({ foreground: 'rgb(25, 118, 210)', background: 'rgb(227, 242, 253)' })
    await expect(page.locator('.bottom-navigation')).toBeHidden()
  })
}

test('responsive shell keeps mobile links centered without horizontal overflow', async ({ page }) => {
  await openShell(page, 'en')
  for (const width of [320, 390, 1023, 1024]) {
    await page.setViewportSize({ width, height: 844 })
    const mobile = width < 1024
    const sidebar = page.locator('aside')
    const bottom = page.locator('.bottom-navigation')
    if (mobile) {
      await expect(sidebar).toBeHidden()
      await expect(bottom).toBeVisible()
      await expect(bottom.locator('a')).toHaveCount(5)
      for (const link of await bottom.locator('a').all()) {
        expect(await link.evaluate(element => getComputedStyle(element).justifyContent)).toBe('center')
      }
      const main = await page.locator('#main-content').boundingBox()
      const navigation = await bottom.boundingBox()
      expect(main!.y + main!.height).toBeLessThanOrEqual(navigation!.y)
    }
    else {
      await expect(sidebar).toBeVisible()
      await expect(bottom).toBeHidden()
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  }
})

test('panel styling preserves the existing dark-theme toggle', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openShell(page, 'en')
  await page.getByRole('button', { name: /^Theme: Light/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  for (const panel of [
    page.getByRole('banner'),
    page.locator('aside'),
    page.locator('#main-content'),
  ]) {
    await expect(panel).toHaveCSS('background-color', 'rgb(26, 26, 26)')
  }
  await expect(page.locator('aside [aria-current="page"]')).toHaveCSS('color', 'rgb(100, 181, 246)')
  await page.getByRole('button', { name: /^Theme: Dark/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
})

test('header menus, persistent profile, avatar and password change work together', async ({ page }) => {
  await openShell(page, 'en')
  const header = page.getByRole('banner')
  await expect(header.getByRole('button', { name: 'Account menu' })).toHaveText('U')
  await expect(header.getByRole('button', { name: 'Sign out' })).toHaveCount(0)
  await expect(header.locator('a[href="/change-password"]')).toHaveCount(0)
  await header.getByRole('button', { name: 'Choose language' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('menuitem')).toHaveCount(2)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('menuitem')).toHaveCount(0)
  await header.getByRole('button', { name: 'Choose language' }).click()
  await expect(page.getByRole('menuitem')).toHaveCount(2)
  await expect(page.getByRole('menuitem', { name: 'English', exact: true })).toBeVisible()
  const chinese = page.getByRole('menuitem', { name: '简体中文', exact: true })
  expect((await chinese.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  await chinese.click()
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  await header.getByRole('button', { name: '选择语言' }).click()
  await page.getByRole('menuitem', { name: 'English', exact: true }).click()
  await header.getByRole('button', { name: 'Account menu' }).click()
  await expect(page.getByRole('menuitem')).toHaveCount(2)
  await page.getByRole('menuitem', { name: 'Profile', exact: true }).click()
  await expect(page.getByTestId('profile-page')).toBeVisible()
  await expect(page.locator('#profile-id')).toHaveAttribute('readonly')
  await expect(page.locator('#profile-username')).toHaveAttribute('readonly')
  await page.getByLabel('Email address', { exact: true }).fill('fail@example.com')
  await page.getByLabel('Full Name', { exact: true }).fill('Updated Name')
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save profile', exact: true })).toBeEnabled()
  await expect(page.getByLabel('Full Name', { exact: true })).toHaveValue('Updated Name')
  await page.getByLabel('Email address', { exact: true }).fill('updated@example.com')
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  await expect(header.getByRole('button', { name: 'Account menu' })).toHaveText('UN')
  await page.locator('#profile-avatar').setInputFiles({
    name: 'avatar.png',
    mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSioAAAAASUVORK5CYII=', 'base64'),
  })
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  await expect(header.getByRole('button', { name: 'Account menu' }).locator('img')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Email address', { exact: true })).toHaveValue('updated@example.com')
  await expect(page.getByLabel('Full Name', { exact: true })).toHaveValue('Updated Name')
  await expect(header.getByRole('button', { name: 'Account menu' }).locator('img')).toBeVisible()
  await page.getByLabel('Current password', { exact: true }).fill('current-password')
  await page.getByLabel('New password', { exact: true }).fill('changed-password')
  await page.getByRole('button', { name: 'Change password', exact: true }).click()
  await expect(page.getByLabel('New password', { exact: true })).toHaveValue('')
  await expect(page).toHaveURL('/profile')
  await page.getByRole('button', { name: 'Use initials instead', exact: true }).click()
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  await expect(header.getByRole('button', { name: 'Account menu' })).toHaveText('UN')
  await header.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL('/login')
})

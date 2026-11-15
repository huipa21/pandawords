// 63f1b3902f8d0cf1a5c3fe4fcd2c3ff70ef2b2a6
import { createHash } from 'node:crypto';
import { expect, test } from '@playwright/test';
test('production manifest/icons install and offline shell never cache private traffic; online login is unchanged', async ({
  page,
  context,
  request
}) => {
  const manifestResponse = await request.get('/manifest.v1.webmanifest');
  expect(manifestResponse.ok()).toBe(true);
  const manifest = await manifestResponse.json();
  expect(manifest).toMatchObject({
    id: '/',
    name: 'PandaWords',
    short_name: 'PandaWords',
    start_url: '/',
    scope: '/',
    display: 'standalone'
  });
  expect(manifest.theme_color).toMatch(/^#[\da-f]{6}$/i);
  expect(manifest.background_color).toMatch(/^#[\da-f]{6}$/i);
  expect(manifest.icons).toHaveLength(2);
  for (const icon of manifest.icons) {
    const response = await request.get(icon.src);
    expect(response.headers()['content-type']).toContain('image/png');
    const png = await response.body();
    expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
    expect(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`).toBe(icon.sizes);
    expect(icon.purpose).toContain('maskable');
  }
  const workerSource = await (await request.get('/sw.js')).text();
  const precache = JSON.parse(workerSource.match(/^const precache = (.+)$/m)[1]);
  const publicFiles = ['/index.html', '/manifest.v1.webmanifest', '/pwa-install.v1.js', '/icons/panda.v1.192.png', '/icons/panda.v1.512.png'];
  expect(precache.length).toBeGreaterThan(5);
  for (const entry of precache) {
    if (!publicFiles.includes(entry.url)) {
      expect(entry.url.startsWith('/assets/')).toBe(true);
      expect(entry.url).toMatch(/-[\w-]{8,}\.\w+$/);
      expect(['js', 'css', 'woff', 'woff2', 'png', 'svg', 'webp']).toContain(entry.url.split('.').at(-1));
    }
    const response = await request.get(entry.url);
    expect(response.ok()).toBe(true);
    expect(entry.integrity).toBe(`sha256-${createHash('sha256').update(await response.body()).digest('base64')}`);
  }
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/auth/login') {
      await route.fulfill({
        json: {
          access_token: 'test-token',
          token_type: 'bearer',
          user: {
            id: 'user:test',
            username: 'test-learner',
            role: 'user',
            must_change_password: false
          }
        }
      });
    } else if (path === '/api/auth/refresh') {
      await route.fulfill({
        status: 401,
        json: {
          code: 'auth.unauthorized',
          message: 'Unauthorized'
        }
      });
    } else if (path === '/api/projects') {
      await route.fulfill({
        json: {
          items: [],
          total: 0,
          page: 1,
          page_size: 20
        }
      });
    } else {
      await route.fulfill({
        json: {
          secret: 'private-response-never-cache'
        }
      });
    }
  });
  await page.goto('/projects/private-route');
  await expect(page).toHaveURL(/\/login$/);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  const cdp = await context.newCDPSession(page);
  expect((await cdp.send('Page.getAppManifest')).errors).toEqual([]);
  expect((await cdp.send('Page.getInstallabilityErrors')).installabilityErrors).toEqual([]);
  await cdp.detach();
  await expect(page.locator('#username')).toBeVisible();
  await page.locator('#username').fill('test-learner');
  await page.locator('#password').fill('test-password');
  await page.locator('form button[type="submit"]').click();
  await expect(page).toHaveURL(/\/projects$/);
  await page.evaluate(async () => {
    await fetch('/api/private-record', {
      headers: {
        Authorization: 'Bearer test-token'
      }
    });
    await fetch('/api/media/owner-image');
    await fetch('/_media/private-image');
    await fetch('/media/private-image');
  });
  const cached = await page.evaluate(async () => {
    const result = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      for (const key of await cache.keys()) {
        var _response$headers$get;
        const response = await cache.match(key);
        const text = response !== null && response !== void 0 && (_response$headers$get = response.headers.get('content-type')) !== null && _response$headers$get !== void 0 && _response$headers$get.includes('text/html') ? await response.text() : '';
        result.push({
          url: new URL(key.url).pathname,
          text
        });
      }
    }
    return result;
  });
  expect(cached.length).toBeGreaterThan(5);
  expect(cached.some(entry => entry.url === '/index.html')).toBe(true);
  expect(cached.map(entry => entry.url).sort()).toEqual(precache.map(entry => entry.url).sort());
  for (const entry of cached) {
    expect(entry.text).not.toContain('private-response-never-cache');
    expect(entry.text).not.toContain('test-learner');
  }
  await context.unroute('**/api/**');
  await context.setOffline(true);
  try {
    await page.goto('/projects/private-route');
    await expect(page.locator('#username')).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
    expect(await page.evaluate(() => document.querySelectorAll('script[src]').length)).toBeGreaterThan(0);
    expect(await page.evaluate(async () => {
      try {
        await fetch('/api/media/owner-image', {
          headers: {
            Authorization: 'Bearer test-token'
          }
        });
        return 'unexpected-response';
      } catch {
        return 'network-unavailable';
      }
    })).toBe('network-unavailable');
  } finally {
    await context.setOffline(false);
  }
});
test('captures an early install event and invokes the native prompt from the keyboard', async ({
  page,
  context
}) => {
  let releaseApp;
  let appRequested;
  const gate = new Promise(resolve => releaseApp = resolve);
  const requested = new Promise(resolve => appRequested = resolve);
  await context.route(/\/assets\/index-[^/]+\.js$/, async route => {
    appRequested();
    await gate;
    await route.continue();
  });
  await context.route('**/api/**', route => route.fulfill({
    status: 401,
    json: {
      code: 'auth.unauthorized'
    }
  }));
  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({
      locale: 'en',
      theme: 'light'
    }));
  });
  try {
    await page.goto('/login', {
      waitUntil: 'commit'
    });
    await requested;
    await page.waitForFunction(() => '__pandawordsInstall' in window);
    expect(await page.evaluate(() => {
      const state = window;
      state.testInstallCalls = 0;
      const event = Object.assign(new Event('beforeinstallprompt', {
        cancelable: true
      }), {
        prompt: async () => {
          var _state$testInstallCal;
          state.testInstallCalls = ((_state$testInstallCal = state.testInstallCalls) !== null && _state$testInstallCal !== void 0 ? _state$testInstallCal : 0) + 1;
        },
        userChoice: Promise.resolve({
          outcome: 'accepted'
        })
      });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    })).toBe(true);
  } finally {
    releaseApp();
  }
  const install = page.getByRole('button', {
    name: 'Install',
    exact: true
  });
  await expect(install).toBeVisible();
  await install.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.testInstallCalls)).toBe(1);
  await expect(install).toHaveCount(0);
  await expect(page.locator('#username')).toBeVisible();
});
for (const locale of ['en', 'zh-CN']) {
  for (const width of [320, 1280]) {
    test(`install prompt keyboard, localization and layout: ${locale} ${width}`, async ({
      page,
      context
    }) => {
      await page.setViewportSize({
        width,
        height: 800
      });
      await context.route('**/api/**', route => route.fulfill({
        status: 401,
        json: {
          code: 'auth.unauthorized'
        }
      }));
      await page.addInitScript(language => {
        localStorage.setItem('pandawords.preferences', JSON.stringify({
          locale: language,
          theme: 'light'
        }));
        window.addEventListener('beforeinstallprompt', event => {
          if (event.isTrusted) {
            event.preventDefault();
            event.stopImmediatePropagation();
          }
        });
      }, locale);
      await page.goto('/login');
      await expect(page.locator('#username')).toBeVisible();
      await expect(page.locator('#pwa-install-title')).toHaveCount(0);
      await page.evaluate(() => {
        const event = Object.assign(new Event('beforeinstallprompt', {
          cancelable: true
        }), {
          prompt: async () => {},
          userChoice: Promise.resolve({
            outcome: 'accepted'
          })
        });
        window.dispatchEvent(event);
      });
      const title = page.getByRole('heading', {
        name: locale === 'en' ? 'Install PandaWords' : '安装 PandaWords'
      });
      await expect(title).toBeVisible();
      const install = page.getByRole('button', {
        name: locale === 'en' ? 'Install' : '安装',
        exact: true
      });
      const dismiss = page.getByRole('button', {
        name: locale === 'en' ? 'Not now' : '暂不安装',
        exact: true
      });
      for (const control of [install, dismiss]) {
        const bounds = await control.boundingBox();
        expect(bounds.height).toBeGreaterThanOrEqual(44);
        expect(bounds.width).toBeGreaterThanOrEqual(44);
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await install.focus();
      await page.keyboard.press('Tab');
      await expect(dismiss).toBeFocused();
      const focus = await dismiss.evaluate(element => {
        const style = getComputedStyle(element);
        const tokens = getComputedStyle(document.documentElement);
        return {
          style: style.outlineStyle,
          width: style.outlineWidth,
          offset: style.outlineOffset,
          tokenWidth: tokens.getPropertyValue('--pw-focus-ring-width').trim(),
          tokenOffset: tokens.getPropertyValue('--pw-focus-ring-offset').trim()
        };
      });
      expect(focus.style).toBe('solid');
      expect(focus.width).toBe(focus.tokenWidth);
      expect(focus.offset).toBe(focus.tokenOffset);
      await page.keyboard.press('Enter');
      await expect(title).toHaveCount(0);
      await expect(page.locator('#username')).toBeVisible();
      await page.reload();
      await page.evaluate(() => window.dispatchEvent(new Event('beforeinstallprompt')));
      await expect(title).toHaveCount(0);
    });
  }
}
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJuYW1lcyI6WyJjcmVhdGVIYXNoIiwiZXhwZWN0IiwidGVzdCIsInBhZ2UiLCJjb250ZXh0IiwicmVxdWVzdCIsIm1hbmlmZXN0UmVzcG9uc2UiLCJnZXQiLCJvayIsInRvQmUiLCJtYW5pZmVzdCIsImpzb24iLCJ0b01hdGNoT2JqZWN0IiwiaWQiLCJuYW1lIiwic2hvcnRfbmFtZSIsInN0YXJ0X3VybCIsInNjb3BlIiwiZGlzcGxheSIsInRoZW1lX2NvbG9yIiwidG9NYXRjaCIsImJhY2tncm91bmRfY29sb3IiLCJpY29ucyIsInRvSGF2ZUxlbmd0aCIsImljb24iLCJyZXNwb25zZSIsInNyYyIsImhlYWRlcnMiLCJ0b0NvbnRhaW4iLCJwbmciLCJib2R5Iiwic3ViYXJyYXkiLCJ0b1N0cmluZyIsInJlYWRVSW50MzJCRSIsInNpemVzIiwicHVycG9zZSIsIndvcmtlclNvdXJjZSIsInRleHQiLCJwcmVjYWNoZSIsIkpTT04iLCJwYXJzZSIsIm1hdGNoIiwicHVibGljRmlsZXMiLCJsZW5ndGgiLCJ0b0JlR3JlYXRlclRoYW4iLCJlbnRyeSIsImluY2x1ZGVzIiwidXJsIiwic3RhcnRzV2l0aCIsInNwbGl0IiwiYXQiLCJpbnRlZ3JpdHkiLCJ1cGRhdGUiLCJkaWdlc3QiLCJyb3V0ZSIsInBhdGgiLCJVUkwiLCJwYXRobmFtZSIsImZ1bGZpbGwiLCJhY2Nlc3NfdG9rZW4iLCJ0b2tlbl90eXBlIiwidXNlciIsInVzZXJuYW1lIiwicm9sZSIsIm11c3RfY2hhbmdlX3Bhc3N3b3JkIiwic3RhdHVzIiwiY29kZSIsIm1lc3NhZ2UiLCJpdGVtcyIsInRvdGFsIiwicGFnZV9zaXplIiwic2VjcmV0IiwiZ290byIsInRvSGF2ZVVSTCIsImV2YWx1YXRlIiwibmF2aWdhdG9yIiwic2VydmljZVdvcmtlciIsInJlYWR5IiwicmVsb2FkIiwicG9sbCIsImNvbnRyb2xsZXIiLCJjZHAiLCJuZXdDRFBTZXNzaW9uIiwic2VuZCIsImVycm9ycyIsInRvRXF1YWwiLCJpbnN0YWxsYWJpbGl0eUVycm9ycyIsImRldGFjaCIsImxvY2F0b3IiLCJ0b0JlVmlzaWJsZSIsImZpbGwiLCJjbGljayIsImZldGNoIiwiQXV0aG9yaXphdGlvbiIsImNhY2hlZCIsInJlc3VsdCIsImNhY2hlcyIsImtleXMiLCJjYWNoZSIsIm9wZW4iLCJrZXkiLCJfcmVzcG9uc2UkaGVhZGVycyRnZXQiLCJwdXNoIiwic29tZSIsIm1hcCIsInNvcnQiLCJub3QiLCJ1bnJvdXRlIiwic2V0T2ZmbGluZSIsImRvY3VtZW50IiwicXVlcnlTZWxlY3RvckFsbCIsInJlbGVhc2VBcHAiLCJhcHBSZXF1ZXN0ZWQiLCJnYXRlIiwiUHJvbWlzZSIsInJlc29sdmUiLCJyZXF1ZXN0ZWQiLCJjb250aW51ZSIsImFkZEluaXRTY3JpcHQiLCJsb2NhbFN0b3JhZ2UiLCJzZXRJdGVtIiwic3RyaW5naWZ5IiwibG9jYWxlIiwidGhlbWUiLCJ3YWl0VW50aWwiLCJ3YWl0Rm9yRnVuY3Rpb24iLCJ3aW5kb3ciLCJzdGF0ZSIsInRlc3RJbnN0YWxsQ2FsbHMiLCJldmVudCIsIk9iamVjdCIsImFzc2lnbiIsIkV2ZW50IiwiY2FuY2VsYWJsZSIsInByb21wdCIsIl9zdGF0ZSR0ZXN0SW5zdGFsbENhbCIsInVzZXJDaG9pY2UiLCJvdXRjb21lIiwiZGlzcGF0Y2hFdmVudCIsImRlZmF1bHRQcmV2ZW50ZWQiLCJpbnN0YWxsIiwiZ2V0QnlSb2xlIiwiZXhhY3QiLCJmb2N1cyIsImtleWJvYXJkIiwicHJlc3MiLCJ0b0hhdmVDb3VudCIsIndpZHRoIiwic2V0Vmlld3BvcnRTaXplIiwiaGVpZ2h0IiwibGFuZ3VhZ2UiLCJhZGRFdmVudExpc3RlbmVyIiwiaXNUcnVzdGVkIiwicHJldmVudERlZmF1bHQiLCJzdG9wSW1tZWRpYXRlUHJvcGFnYXRpb24iLCJ0aXRsZSIsImRpc21pc3MiLCJjb250cm9sIiwiYm91bmRzIiwiYm91bmRpbmdCb3giLCJ0b0JlR3JlYXRlclRoYW5PckVxdWFsIiwieCIsInRvQmVMZXNzVGhhbk9yRXF1YWwiLCJkb2N1bWVudEVsZW1lbnQiLCJzY3JvbGxXaWR0aCIsImlubmVyV2lkdGgiLCJ0b0JlRm9jdXNlZCIsImVsZW1lbnQiLCJzdHlsZSIsImdldENvbXB1dGVkU3R5bGUiLCJ0b2tlbnMiLCJvdXRsaW5lU3R5bGUiLCJvdXRsaW5lV2lkdGgiLCJvZmZzZXQiLCJvdXRsaW5lT2Zmc2V0IiwidG9rZW5XaWR0aCIsImdldFByb3BlcnR5VmFsdWUiLCJ0cmltIiwidG9rZW5PZmZzZXQiXSwic291cmNlcyI6WyJwd2Euc3BlYy50cyJdLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgeyBjcmVhdGVIYXNoIH0gZnJvbSAnbm9kZTpjcnlwdG8nXG5pbXBvcnQgeyBleHBlY3QsIHRlc3QgfSBmcm9tICdAcGxheXdyaWdodC90ZXN0J1xuXG50ZXN0KCdwcm9kdWN0aW9uIG1hbmlmZXN0L2ljb25zIGluc3RhbGwgYW5kIG9mZmxpbmUgc2hlbGwgbmV2ZXIgY2FjaGUgcHJpdmF0ZSB0cmFmZmljOyBvbmxpbmUgbG9naW4gaXMgdW5jaGFuZ2VkJywgYXN5bmMgKHsgcGFnZSwgY29udGV4dCwgcmVxdWVzdCB9KSA9PiB7XG4gIGNvbnN0IG1hbmlmZXN0UmVzcG9uc2UgPSBhd2FpdCByZXF1ZXN0LmdldCgnL21hbmlmZXN0LnYxLndlYm1hbmlmZXN0JylcbiAgZXhwZWN0KG1hbmlmZXN0UmVzcG9uc2Uub2soKSkudG9CZSh0cnVlKVxuICBjb25zdCBtYW5pZmVzdCA9IGF3YWl0IG1hbmlmZXN0UmVzcG9uc2UuanNvbigpXG4gIGV4cGVjdChtYW5pZmVzdCkudG9NYXRjaE9iamVjdCh7XG4gICAgaWQ6ICcvJyxcbiAgICBuYW1lOiAnUGFuZGFXb3JkcycsXG4gICAgc2hvcnRfbmFtZTogJ1BhbmRhV29yZHMnLFxuICAgIHN0YXJ0X3VybDogJy8nLFxuICAgIHNjb3BlOiAnLycsXG4gICAgZGlzcGxheTogJ3N0YW5kYWxvbmUnLFxuICB9KVxuICBleHBlY3QobWFuaWZlc3QudGhlbWVfY29sb3IpLnRvTWF0Y2goL14jW1xcZGEtZl17Nn0kL2kpXG4gIGV4cGVjdChtYW5pZmVzdC5iYWNrZ3JvdW5kX2NvbG9yKS50b01hdGNoKC9eI1tcXGRhLWZdezZ9JC9pKVxuICBleHBlY3QobWFuaWZlc3QuaWNvbnMpLnRvSGF2ZUxlbmd0aCgyKVxuICBmb3IgKGNvbnN0IGljb24gb2YgbWFuaWZlc3QuaWNvbnMpIHtcbiAgICBjb25zdCByZXNwb25zZSA9IGF3YWl0IHJlcXVlc3QuZ2V0KGljb24uc3JjKVxuICAgIGV4cGVjdChyZXNwb25zZS5oZWFkZXJzKClbJ2NvbnRlbnQtdHlwZSddKS50b0NvbnRhaW4oJ2ltYWdlL3BuZycpXG4gICAgY29uc3QgcG5nID0gYXdhaXQgcmVzcG9uc2UuYm9keSgpXG4gICAgZXhwZWN0KHBuZy5zdWJhcnJheSgwLCA4KS50b1N0cmluZygnaGV4JykpLnRvQmUoJzg5NTA0ZTQ3MGQwYTFhMGEnKVxuICAgIGV4cGVjdChgJHtwbmcucmVhZFVJbnQzMkJFKDE2KX14JHtwbmcucmVhZFVJbnQzMkJFKDIwKX1gKS50b0JlKGljb24uc2l6ZXMpXG4gICAgZXhwZWN0KGljb24ucHVycG9zZSkudG9Db250YWluKCdtYXNrYWJsZScpXG4gIH1cbiAgY29uc3Qgd29ya2VyU291cmNlID0gYXdhaXQgKGF3YWl0IHJlcXVlc3QuZ2V0KCcvc3cuanMnKSkudGV4dCgpXG4gIGNvbnN0IHByZWNhY2hlID0gSlNPTi5wYXJzZSh3b3JrZXJTb3VyY2UubWF0Y2goL15jb25zdCBwcmVjYWNoZSA9ICguKykkL20pIVsxXSEpIGFzIHsgdXJsOiBzdHJpbmcsIGludGVncml0eTogc3RyaW5nIH1bXVxuICBjb25zdCBwdWJsaWNGaWxlcyA9IFtcbiAgICAnL2luZGV4Lmh0bWwnLFxuICAgICcvbWFuaWZlc3QudjEud2VibWFuaWZlc3QnLFxuICAgICcvcHdhLWluc3RhbGwudjEuanMnLFxuICAgICcvaWNvbnMvcGFuZGEudjEuMTkyLnBuZycsXG4gICAgJy9pY29ucy9wYW5kYS52MS41MTIucG5nJyxcbiAgXVxuICBleHBlY3QocHJlY2FjaGUubGVuZ3RoKS50b0JlR3JlYXRlclRoYW4oNSlcbiAgZm9yIChjb25zdCBlbnRyeSBvZiBwcmVjYWNoZSkge1xuICAgIGlmICghcHVibGljRmlsZXMuaW5jbHVkZXMoZW50cnkudXJsKSkge1xuICAgICAgZXhwZWN0KGVudHJ5LnVybC5zdGFydHNXaXRoKCcvYXNzZXRzLycpKS50b0JlKHRydWUpXG4gICAgICBleHBlY3QoZW50cnkudXJsKS50b01hdGNoKC8tW1xcdy1dezgsfVxcLlxcdyskLylcbiAgICAgIGV4cGVjdChbXG4gICAgICAgICdqcycsXG4gICAgICAgICdjc3MnLFxuICAgICAgICAnd29mZicsXG4gICAgICAgICd3b2ZmMicsXG4gICAgICAgICdwbmcnLFxuICAgICAgICAnc3ZnJyxcbiAgICAgICAgJ3dlYnAnLFxuICAgICAgXSkudG9Db250YWluKGVudHJ5LnVybC5zcGxpdCgnLicpLmF0KC0xKSlcbiAgICB9XG4gICAgY29uc3QgcmVzcG9uc2UgPSBhd2FpdCByZXF1ZXN0LmdldChlbnRyeS51cmwpXG4gICAgZXhwZWN0KHJlc3BvbnNlLm9rKCkpLnRvQmUodHJ1ZSlcbiAgICBleHBlY3QoZW50cnkuaW50ZWdyaXR5KS50b0JlKGBzaGEyNTYtJHtjcmVhdGVIYXNoKCdzaGEyNTYnKS51cGRhdGUoYXdhaXQgcmVzcG9uc2UuYm9keSgpKS5kaWdlc3QoJ2Jhc2U2NCcpfWApXG4gIH1cbiAgYXdhaXQgY29udGV4dC5yb3V0ZSgnKiovYXBpLyoqJywgYXN5bmMgKHJvdXRlKSA9PiB7XG4gICAgY29uc3QgcGF0aCA9IG5ldyBVUkwocm91dGUucmVxdWVzdCgpLnVybCgpKS5wYXRobmFtZVxuICAgIGlmIChwYXRoID09PSAnL2FwaS9hdXRoL2xvZ2luJykge1xuICAgICAgYXdhaXQgcm91dGUuZnVsZmlsbCh7XG4gICAgICAgIGpzb246IHtcbiAgICAgICAgICBhY2Nlc3NfdG9rZW46ICd0ZXN0LXRva2VuJyxcbiAgICAgICAgICB0b2tlbl90eXBlOiAnYmVhcmVyJyxcbiAgICAgICAgICB1c2VyOiB7XG4gICAgICAgICAgICBpZDogJ3VzZXI6dGVzdCcsXG4gICAgICAgICAgICB1c2VybmFtZTogJ3Rlc3QtbGVhcm5lcicsXG4gICAgICAgICAgICByb2xlOiAndXNlcicsXG4gICAgICAgICAgICBtdXN0X2NoYW5nZV9wYXNzd29yZDogZmFsc2UsXG4gICAgICAgICAgfSxcbiAgICAgICAgfSxcbiAgICAgIH0pXG4gICAgfVxuICAgIGVsc2UgaWYgKHBhdGggPT09ICcvYXBpL2F1dGgvcmVmcmVzaCcpIHtcbiAgICAgIGF3YWl0IHJvdXRlLmZ1bGZpbGwoe1xuICAgICAgICBzdGF0dXM6IDQwMSxcbiAgICAgICAganNvbjogeyBjb2RlOiAnYXV0aC51bmF1dGhvcml6ZWQnLCBtZXNzYWdlOiAnVW5hdXRob3JpemVkJyB9LFxuICAgICAgfSlcbiAgICB9XG4gICAgZWxzZSBpZiAocGF0aCA9PT0gJy9hcGkvcHJvamVjdHMnKSB7XG4gICAgICBhd2FpdCByb3V0ZS5mdWxmaWxsKHtcbiAgICAgICAganNvbjoge1xuICAgICAgICAgIGl0ZW1zOiBbXSxcbiAgICAgICAgICB0b3RhbDogMCxcbiAgICAgICAgICBwYWdlOiAxLFxuICAgICAgICAgIHBhZ2Vfc2l6ZTogMjAsXG4gICAgICAgIH0sXG4gICAgICB9KVxuICAgIH1cbiAgICBlbHNlIHtcbiAgICAgIGF3YWl0IHJvdXRlLmZ1bGZpbGwoe1xuICAgICAgICBqc29uOiB7IHNlY3JldDogJ3ByaXZhdGUtcmVzcG9uc2UtbmV2ZXItY2FjaGUnIH0sXG4gICAgICB9KVxuICAgIH1cbiAgfSlcbiAgYXdhaXQgcGFnZS5nb3RvKCcvcHJvamVjdHMvcHJpdmF0ZS1yb3V0ZScpXG4gIGF3YWl0IGV4cGVjdChwYWdlKS50b0hhdmVVUkwoL1xcL2xvZ2luJC8pXG4gIGF3YWl0IHBhZ2UuZXZhbHVhdGUoKCkgPT4gbmF2aWdhdG9yLnNlcnZpY2VXb3JrZXIucmVhZHkpXG4gIGF3YWl0IHBhZ2UucmVsb2FkKClcbiAgYXdhaXQgZXhwZWN0LnBvbGwoKCkgPT4gcGFnZS5ldmFsdWF0ZSgoKSA9PiAhIW5hdmlnYXRvci5zZXJ2aWNlV29ya2VyLmNvbnRyb2xsZXIpKS50b0JlKHRydWUpXG4gIGNvbnN0IGNkcCA9IGF3YWl0IGNvbnRleHQubmV3Q0RQU2Vzc2lvbihwYWdlKVxuICBleHBlY3QoKGF3YWl0IGNkcC5zZW5kKCdQYWdlLmdldEFwcE1hbmlmZXN0JykpLmVycm9ycykudG9FcXVhbChbXSlcbiAgZXhwZWN0KChhd2FpdCBjZHAuc2VuZCgnUGFnZS5nZXRJbnN0YWxsYWJpbGl0eUVycm9ycycpKS5pbnN0YWxsYWJpbGl0eUVycm9ycykudG9FcXVhbChbXSlcbiAgYXdhaXQgY2RwLmRldGFjaCgpXG4gIGF3YWl0IGV4cGVjdChwYWdlLmxvY2F0b3IoJyN1c2VybmFtZScpKS50b0JlVmlzaWJsZSgpXG4gIGF3YWl0IHBhZ2UubG9jYXRvcignI3VzZXJuYW1lJykuZmlsbCgndGVzdC1sZWFybmVyJylcbiAgYXdhaXQgcGFnZS5sb2NhdG9yKCcjcGFzc3dvcmQnKS5maWxsKCd0ZXN0LXBhc3N3b3JkJylcbiAgYXdhaXQgcGFnZS5sb2NhdG9yKCdmb3JtIGJ1dHRvblt0eXBlPVwic3VibWl0XCJdJykuY2xpY2soKVxuICBhd2FpdCBleHBlY3QocGFnZSkudG9IYXZlVVJMKC9cXC9wcm9qZWN0cyQvKVxuICBhd2FpdCBwYWdlLmV2YWx1YXRlKGFzeW5jICgpID0+IHtcbiAgICBhd2FpdCBmZXRjaCgnL2FwaS9wcml2YXRlLXJlY29yZCcsIHtcbiAgICAgIGhlYWRlcnM6IHsgQXV0aG9yaXphdGlvbjogJ0JlYXJlciB0ZXN0LXRva2VuJyB9LFxuICAgIH0pXG4gICAgYXdhaXQgZmV0Y2goJy9hcGkvbWVkaWEvb3duZXItaW1hZ2UnKVxuICAgIGF3YWl0IGZldGNoKCcvX21lZGlhL3ByaXZhdGUtaW1hZ2UnKVxuICAgIGF3YWl0IGZldGNoKCcvbWVkaWEvcHJpdmF0ZS1pbWFnZScpXG4gIH0pXG4gIGNvbnN0IGNhY2hlZCA9IGF3YWl0IHBhZ2UuZXZhbHVhdGUoYXN5bmMgKCkgPT4ge1xuICAgIGNvbnN0IHJlc3VsdDogeyB1cmw6IHN0cmluZywgdGV4dD86IHN0cmluZyB9W10gPSBbXVxuICAgIGZvciAoY29uc3QgbmFtZSBvZiBhd2FpdCBjYWNoZXMua2V5cygpKSB7XG4gICAgICBjb25zdCBjYWNoZSA9IGF3YWl0IGNhY2hlcy5vcGVuKG5hbWUpXG4gICAgICBmb3IgKGNvbnN0IGtleSBvZiBhd2FpdCBjYWNoZS5rZXlzKCkpIHtcbiAgICAgICAgY29uc3QgcmVzcG9uc2UgPSBhd2FpdCBjYWNoZS5tYXRjaChrZXkpXG4gICAgICAgIGNvbnN0IHRleHQgPSByZXNwb25zZT8uaGVhZGVycy5nZXQoJ2NvbnRlbnQtdHlwZScpPy5pbmNsdWRlcygndGV4dC9odG1sJylcbiAgICAgICAgICA/IGF3YWl0IHJlc3BvbnNlLnRleHQoKVxuICAgICAgICAgIDogJydcbiAgICAgICAgcmVzdWx0LnB1c2goeyB1cmw6IG5ldyBVUkwoa2V5LnVybCkucGF0aG5hbWUsIHRleHQgfSlcbiAgICAgIH1cbiAgICB9XG4gICAgcmV0dXJuIHJlc3VsdFxuICB9KVxuICBleHBlY3QoY2FjaGVkLmxlbmd0aCkudG9CZUdyZWF0ZXJUaGFuKDUpXG4gIGV4cGVjdChjYWNoZWQuc29tZShlbnRyeSA9PiBlbnRyeS51cmwgPT09ICcvaW5kZXguaHRtbCcpKS50b0JlKHRydWUpXG4gIGV4cGVjdChjYWNoZWQubWFwKGVudHJ5ID0+IGVudHJ5LnVybCkuc29ydCgpKS50b0VxdWFsKHByZWNhY2hlLm1hcChlbnRyeSA9PiBlbnRyeS51cmwpLnNvcnQoKSlcbiAgZm9yIChjb25zdCBlbnRyeSBvZiBjYWNoZWQpIHtcbiAgICBleHBlY3QoZW50cnkudGV4dCkubm90LnRvQ29udGFpbigncHJpdmF0ZS1yZXNwb25zZS1uZXZlci1jYWNoZScpXG4gICAgZXhwZWN0KGVudHJ5LnRleHQpLm5vdC50b0NvbnRhaW4oJ3Rlc3QtbGVhcm5lcicpXG4gIH1cbiAgYXdhaXQgY29udGV4dC51bnJvdXRlKCcqKi9hcGkvKionKVxuICBhd2FpdCBjb250ZXh0LnNldE9mZmxpbmUodHJ1ZSlcbiAgdHJ5IHtcbiAgICBhd2FpdCBwYWdlLmdvdG8oJy9wcm9qZWN0cy9wcml2YXRlLXJvdXRlJylcbiAgICBhd2FpdCBleHBlY3QocGFnZS5sb2NhdG9yKCcjdXNlcm5hbWUnKSkudG9CZVZpc2libGUoKVxuICAgIGF3YWl0IGV4cGVjdChwYWdlKS50b0hhdmVVUkwoL1xcL2xvZ2luJC8pXG4gICAgZXhwZWN0KGF3YWl0IHBhZ2UuZXZhbHVhdGUoKCkgPT4gZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnc2NyaXB0W3NyY10nKS5sZW5ndGgpKS50b0JlR3JlYXRlclRoYW4oMClcbiAgICBleHBlY3QoYXdhaXQgcGFnZS5ldmFsdWF0ZShhc3luYyAoKSA9PiB7XG4gICAgICB0cnkge1xuICAgICAgICBhd2FpdCBmZXRjaCgnL2FwaS9tZWRpYS9vd25lci1pbWFnZScsIHtcbiAgICAgICAgICBoZWFkZXJzOiB7IEF1dGhvcml6YXRpb246ICdCZWFyZXIgdGVzdC10b2tlbicgfSxcbiAgICAgICAgfSlcbiAgICAgICAgcmV0dXJuICd1bmV4cGVjdGVkLXJlc3BvbnNlJ1xuICAgICAgfVxuICAgICAgY2F0Y2gge1xuICAgICAgICByZXR1cm4gJ25ldHdvcmstdW5hdmFpbGFibGUnXG4gICAgICB9XG4gICAgfSkpLnRvQmUoJ25ldHdvcmstdW5hdmFpbGFibGUnKVxuICB9XG4gIGZpbmFsbHkge1xuICAgIGF3YWl0IGNvbnRleHQuc2V0T2ZmbGluZShmYWxzZSlcbiAgfVxufSlcblxudGVzdCgnY2FwdHVyZXMgYW4gZWFybHkgaW5zdGFsbCBldmVudCBhbmQgaW52b2tlcyB0aGUgbmF0aXZlIHByb21wdCBmcm9tIHRoZSBrZXlib2FyZCcsIGFzeW5jICh7IHBhZ2UsIGNvbnRleHQgfSkgPT4ge1xuICBsZXQgcmVsZWFzZUFwcCE6ICgpID0+IHZvaWRcbiAgbGV0IGFwcFJlcXVlc3RlZCE6ICgpID0+IHZvaWRcbiAgY29uc3QgZ2F0ZSA9IG5ldyBQcm9taXNlPHZvaWQ+KHJlc29sdmUgPT4gcmVsZWFzZUFwcCA9IHJlc29sdmUpXG4gIGNvbnN0IHJlcXVlc3RlZCA9IG5ldyBQcm9taXNlPHZvaWQ+KHJlc29sdmUgPT4gYXBwUmVxdWVzdGVkID0gcmVzb2x2ZSlcbiAgYXdhaXQgY29udGV4dC5yb3V0ZSgvXFwvYXNzZXRzXFwvaW5kZXgtW14vXStcXC5qcyQvLCBhc3luYyAocm91dGUpID0+IHtcbiAgICBhcHBSZXF1ZXN0ZWQoKVxuICAgIGF3YWl0IGdhdGVcbiAgICBhd2FpdCByb3V0ZS5jb250aW51ZSgpXG4gIH0pXG4gIGF3YWl0IGNvbnRleHQucm91dGUoJyoqL2FwaS8qKicsIHJvdXRlID0+IHJvdXRlLmZ1bGZpbGwoe1xuICAgIHN0YXR1czogNDAxLFxuICAgIGpzb246IHsgY29kZTogJ2F1dGgudW5hdXRob3JpemVkJyB9LFxuICB9KSlcbiAgYXdhaXQgcGFnZS5hZGRJbml0U2NyaXB0KCgpID0+IHtcbiAgICBsb2NhbFN0b3JhZ2Uuc2V0SXRlbSgncGFuZGF3b3Jkcy5wcmVmZXJlbmNlcycsIEpTT04uc3RyaW5naWZ5KHsgbG9jYWxlOiAnZW4nLCB0aGVtZTogJ2xpZ2h0JyB9KSlcbiAgfSlcbiAgdHJ5IHtcbiAgICBhd2FpdCBwYWdlLmdvdG8oJy9sb2dpbicsIHsgd2FpdFVudGlsOiAnY29tbWl0JyB9KVxuICAgIGF3YWl0IHJlcXVlc3RlZFxuICAgIGF3YWl0IHBhZ2Uud2FpdEZvckZ1bmN0aW9uKCgpID0+ICdfX3BhbmRhd29yZHNJbnN0YWxsJyBpbiB3aW5kb3cpXG4gICAgZXhwZWN0KGF3YWl0IHBhZ2UuZXZhbHVhdGUoKCkgPT4ge1xuICAgICAgY29uc3Qgc3RhdGUgPSB3aW5kb3cgYXMgV2luZG93ICYgeyB0ZXN0SW5zdGFsbENhbGxzPzogbnVtYmVyIH1cbiAgICAgIHN0YXRlLnRlc3RJbnN0YWxsQ2FsbHMgPSAwXG4gICAgICBjb25zdCBldmVudCA9IE9iamVjdC5hc3NpZ24obmV3IEV2ZW50KCdiZWZvcmVpbnN0YWxscHJvbXB0JywgeyBjYW5jZWxhYmxlOiB0cnVlIH0pLCB7XG4gICAgICAgIHByb21wdDogYXN5bmMgKCkgPT4geyBzdGF0ZS50ZXN0SW5zdGFsbENhbGxzID0gKHN0YXRlLnRlc3RJbnN0YWxsQ2FsbHMgPz8gMCkgKyAxIH0sXG4gICAgICAgIHVzZXJDaG9pY2U6IFByb21pc2UucmVzb2x2ZSh7IG91dGNvbWU6ICdhY2NlcHRlZCcgfSksXG4gICAgICB9KVxuICAgICAgd2luZG93LmRpc3BhdGNoRXZlbnQoZXZlbnQpXG4gICAgICByZXR1cm4gZXZlbnQuZGVmYXVsdFByZXZlbnRlZFxuICAgIH0pKS50b0JlKHRydWUpXG4gIH1cbiAgZmluYWxseSB7XG4gICAgcmVsZWFzZUFwcCgpXG4gIH1cbiAgY29uc3QgaW5zdGFsbCA9IHBhZ2UuZ2V0QnlSb2xlKCdidXR0b24nLCB7IG5hbWU6ICdJbnN0YWxsJywgZXhhY3Q6IHRydWUgfSlcbiAgYXdhaXQgZXhwZWN0KGluc3RhbGwpLnRvQmVWaXNpYmxlKClcbiAgYXdhaXQgaW5zdGFsbC5mb2N1cygpXG4gIGF3YWl0IHBhZ2Uua2V5Ym9hcmQucHJlc3MoJ0VudGVyJylcbiAgYXdhaXQgZXhwZWN0LnBvbGwoKCkgPT4gcGFnZS5ldmFsdWF0ZSgoKSA9PiAod2luZG93IGFzIFdpbmRvdyAmIHsgdGVzdEluc3RhbGxDYWxscz86IG51bWJlciB9KS50ZXN0SW5zdGFsbENhbGxzKSkudG9CZSgxKVxuICBhd2FpdCBleHBlY3QoaW5zdGFsbCkudG9IYXZlQ291bnQoMClcbiAgYXdhaXQgZXhwZWN0KHBhZ2UubG9jYXRvcignI3VzZXJuYW1lJykpLnRvQmVWaXNpYmxlKClcbn0pXG5cbmZvciAoY29uc3QgbG9jYWxlIG9mIFsnZW4nLCAnemgtQ04nXSBhcyBjb25zdCkge1xuICBmb3IgKGNvbnN0IHdpZHRoIG9mIFszMjAsIDEyODBdKSB7XG4gICAgdGVzdChgaW5zdGFsbCBwcm9tcHQga2V5Ym9hcmQsIGxvY2FsaXphdGlvbiBhbmQgbGF5b3V0OiAke2xvY2FsZX0gJHt3aWR0aH1gLCBhc3luYyAoeyBwYWdlLCBjb250ZXh0IH0pID0+IHtcbiAgICAgIGF3YWl0IHBhZ2Uuc2V0Vmlld3BvcnRTaXplKHsgd2lkdGgsIGhlaWdodDogODAwIH0pXG4gICAgICBhd2FpdCBjb250ZXh0LnJvdXRlKCcqKi9hcGkvKionLCByb3V0ZSA9PiByb3V0ZS5mdWxmaWxsKHtcbiAgICAgICAgc3RhdHVzOiA0MDEsXG4gICAgICAgIGpzb246IHsgY29kZTogJ2F1dGgudW5hdXRob3JpemVkJyB9LFxuICAgICAgfSkpXG4gICAgICBhd2FpdCBwYWdlLmFkZEluaXRTY3JpcHQoKGxhbmd1YWdlKSA9PiB7XG4gICAgICAgIGxvY2FsU3RvcmFnZS5zZXRJdGVtKCdwYW5kYXdvcmRzLnByZWZlcmVuY2VzJywgSlNPTi5zdHJpbmdpZnkoeyBsb2NhbGU6IGxhbmd1YWdlLCB0aGVtZTogJ2xpZ2h0JyB9KSlcbiAgICAgICAgd2luZG93LmFkZEV2ZW50TGlzdGVuZXIoJ2JlZm9yZWluc3RhbGxwcm9tcHQnLCAoZXZlbnQpID0+IHtcbiAgICAgICAgICBpZiAoZXZlbnQuaXNUcnVzdGVkKSB7XG4gICAgICAgICAgICBldmVudC5wcmV2ZW50RGVmYXVsdCgpXG4gICAgICAgICAgICBldmVudC5zdG9wSW1tZWRpYXRlUHJvcGFnYXRpb24oKVxuICAgICAgICAgIH1cbiAgICAgICAgfSlcbiAgICAgIH0sIGxvY2FsZSlcbiAgICAgIGF3YWl0IHBhZ2UuZ290bygnL2xvZ2luJylcbiAgICAgIGF3YWl0IGV4cGVjdChwYWdlLmxvY2F0b3IoJyN1c2VybmFtZScpKS50b0JlVmlzaWJsZSgpXG4gICAgICBhd2FpdCBleHBlY3QocGFnZS5sb2NhdG9yKCcjcHdhLWluc3RhbGwtdGl0bGUnKSkudG9IYXZlQ291bnQoMClcbiAgICAgIGF3YWl0IHBhZ2UuZXZhbHVhdGUoKCkgPT4ge1xuICAgICAgICBjb25zdCBldmVudCA9IE9iamVjdC5hc3NpZ24obmV3IEV2ZW50KCdiZWZvcmVpbnN0YWxscHJvbXB0JywgeyBjYW5jZWxhYmxlOiB0cnVlIH0pLCB7XG4gICAgICAgICAgcHJvbXB0OiBhc3luYyAoKSA9PiB7fSxcbiAgICAgICAgICB1c2VyQ2hvaWNlOiBQcm9taXNlLnJlc29sdmUoeyBvdXRjb21lOiAnYWNjZXB0ZWQnIH0pLFxuICAgICAgICB9KVxuICAgICAgICB3aW5kb3cuZGlzcGF0Y2hFdmVudChldmVudClcbiAgICAgIH0pXG4gICAgICBjb25zdCB0aXRsZSA9IHBhZ2UuZ2V0QnlSb2xlKCdoZWFkaW5nJywge1xuICAgICAgICBuYW1lOiBsb2NhbGUgPT09ICdlbidcbiAgICAgICAgICA/ICdJbnN0YWxsIFBhbmRhV29yZHMnXG4gICAgICAgICAgOiAn5a6J6KOFIFBhbmRhV29yZHMnLFxuICAgICAgfSlcbiAgICAgIGF3YWl0IGV4cGVjdCh0aXRsZSkudG9CZVZpc2libGUoKVxuICAgICAgY29uc3QgaW5zdGFsbCA9IHBhZ2UuZ2V0QnlSb2xlKCdidXR0b24nLCB7XG4gICAgICAgIG5hbWU6IGxvY2FsZSA9PT0gJ2VuJ1xuICAgICAgICAgID8gJ0luc3RhbGwnXG4gICAgICAgICAgOiAn5a6J6KOFJyxcbiAgICAgICAgZXhhY3Q6IHRydWUsXG4gICAgICB9KVxuICAgICAgY29uc3QgZGlzbWlzcyA9IHBhZ2UuZ2V0QnlSb2xlKCdidXR0b24nLCB7XG4gICAgICAgIG5hbWU6IGxvY2FsZSA9PT0gJ2VuJ1xuICAgICAgICAgID8gJ05vdCBub3cnXG4gICAgICAgICAgOiAn5pqC5LiN5a6J6KOFJyxcbiAgICAgICAgZXhhY3Q6IHRydWUsXG4gICAgICB9KVxuICAgICAgZm9yIChjb25zdCBjb250cm9sIG9mIFtpbnN0YWxsLCBkaXNtaXNzXSkge1xuICAgICAgICBjb25zdCBib3VuZHMgPSBhd2FpdCBjb250cm9sLmJvdW5kaW5nQm94KClcbiAgICAgICAgZXhwZWN0KGJvdW5kcyEuaGVpZ2h0KS50b0JlR3JlYXRlclRoYW5PckVxdWFsKDQ0KVxuICAgICAgICBleHBlY3QoYm91bmRzIS53aWR0aCkudG9CZUdyZWF0ZXJUaGFuT3JFcXVhbCg0NClcbiAgICAgICAgZXhwZWN0KGJvdW5kcyEueCkudG9CZUdyZWF0ZXJUaGFuT3JFcXVhbCgwKVxuICAgICAgICBleHBlY3QoYm91bmRzIS54ICsgYm91bmRzIS53aWR0aCkudG9CZUxlc3NUaGFuT3JFcXVhbCh3aWR0aClcbiAgICAgIH1cbiAgICAgIGV4cGVjdChhd2FpdCBwYWdlLmV2YWx1YXRlKCgpID0+IGRvY3VtZW50LmRvY3VtZW50RWxlbWVudC5zY3JvbGxXaWR0aCA8PSB3aW5kb3cuaW5uZXJXaWR0aCkpLnRvQmUodHJ1ZSlcbiAgICAgIGF3YWl0IGluc3RhbGwuZm9jdXMoKVxuICAgICAgYXdhaXQgcGFnZS5rZXlib2FyZC5wcmVzcygnVGFiJylcbiAgICAgIGF3YWl0IGV4cGVjdChkaXNtaXNzKS50b0JlRm9jdXNlZCgpXG4gICAgICBjb25zdCBmb2N1cyA9IGF3YWl0IGRpc21pc3MuZXZhbHVhdGUoKGVsZW1lbnQpID0+IHtcbiAgICAgICAgY29uc3Qgc3R5bGUgPSBnZXRDb21wdXRlZFN0eWxlKGVsZW1lbnQpXG4gICAgICAgIGNvbnN0IHRva2VucyA9IGdldENvbXB1dGVkU3R5bGUoZG9jdW1lbnQuZG9jdW1lbnRFbGVtZW50KVxuICAgICAgICByZXR1cm4ge1xuICAgICAgICAgIHN0eWxlOiBzdHlsZS5vdXRsaW5lU3R5bGUsXG4gICAgICAgICAgd2lkdGg6IHN0eWxlLm91dGxpbmVXaWR0aCxcbiAgICAgICAgICBvZmZzZXQ6IHN0eWxlLm91dGxpbmVPZmZzZXQsXG4gICAgICAgICAgdG9rZW5XaWR0aDogdG9rZW5zLmdldFByb3BlcnR5VmFsdWUoJy0tcHctZm9jdXMtcmluZy13aWR0aCcpLnRyaW0oKSxcbiAgICAgICAgICB0b2tlbk9mZnNldDogdG9rZW5zLmdldFByb3BlcnR5VmFsdWUoJy0tcHctZm9jdXMtcmluZy1vZmZzZXQnKS50cmltKCksXG4gICAgICAgIH1cbiAgICAgIH0pXG4gICAgICBleHBlY3QoZm9jdXMuc3R5bGUpLnRvQmUoJ3NvbGlkJylcbiAgICAgIGV4cGVjdChmb2N1cy53aWR0aCkudG9CZShmb2N1cy50b2tlbldpZHRoKVxuICAgICAgZXhwZWN0KGZvY3VzLm9mZnNldCkudG9CZShmb2N1cy50b2tlbk9mZnNldClcbiAgICAgIGF3YWl0IHBhZ2Uua2V5Ym9hcmQucHJlc3MoJ0VudGVyJylcbiAgICAgIGF3YWl0IGV4cGVjdCh0aXRsZSkudG9IYXZlQ291bnQoMClcbiAgICAgIGF3YWl0IGV4cGVjdChwYWdlLmxvY2F0b3IoJyN1c2VybmFtZScpKS50b0JlVmlzaWJsZSgpXG4gICAgICBhd2FpdCBwYWdlLnJlbG9hZCgpXG4gICAgICBhd2FpdCBwYWdlLmV2YWx1YXRlKCgpID0+IHdpbmRvdy5kaXNwYXRjaEV2ZW50KG5ldyBFdmVudCgnYmVmb3JlaW5zdGFsbHByb21wdCcpKSlcbiAgICAgIGF3YWl0IGV4cGVjdCh0aXRsZSkudG9IYXZlQ291bnQoMClcbiAgICB9KVxuICB9XG59XG4iXSwibWFwcGluZ3MiOiJBQUFBLFNBQVNBLFVBQVUsUUFBUSxhQUFhO0FBQ3hDLFNBQVNDLE1BQU0sRUFBRUMsSUFBSSxRQUFRLGtCQUFrQjtBQUUvQ0EsSUFBSSxDQUFDLDRHQUE0RyxFQUFFLE9BQU87RUFBRUMsSUFBSTtFQUFFQyxPQUFPO0VBQUVDO0FBQVEsQ0FBQyxLQUFLO0VBQ3ZKLE1BQU1DLGdCQUFnQixHQUFHLE1BQU1ELE9BQU8sQ0FBQ0UsR0FBRyxDQUFDLDBCQUEwQixDQUFDO0VBQ3RFTixNQUFNLENBQUNLLGdCQUFnQixDQUFDRSxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUNDLElBQUksQ0FBQyxJQUFJLENBQUM7RUFDeEMsTUFBTUMsUUFBUSxHQUFHLE1BQU1KLGdCQUFnQixDQUFDSyxJQUFJLENBQUMsQ0FBQztFQUM5Q1YsTUFBTSxDQUFDUyxRQUFRLENBQUMsQ0FBQ0UsYUFBYSxDQUFDO0lBQzdCQyxFQUFFLEVBQUUsR0FBRztJQUNQQyxJQUFJLEVBQUUsWUFBWTtJQUNsQkMsVUFBVSxF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
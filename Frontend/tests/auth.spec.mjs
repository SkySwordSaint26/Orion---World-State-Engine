import { test, expect } from 'playwright/test';

const user = { id: 'auth-test-author', email: 'demo@example.com' };
const reply = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
const enterCredentials = async page => {
  await page.getByLabel('Email Address').fill(user.email);
  await page.getByLabel('Password', { exact: true }).fill('orion-demo');
};

test('login uses the frontend origin and waits for the current user before entering the archive', async ({ page }) => {
  let releaseLogin, releaseUser;
  const loginReady = new Promise(resolve => { releaseLogin = resolve; });
  const userReady = new Promise(resolve => { releaseUser = resolve; });
  const requests = [];
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    requests.push({ url: request.url(), method: request.method() });
    if (request.url().endsWith('/auth/login')) {
      expect(request.postDataJSON()).toEqual({ email: user.email, password: 'orion-demo' });
      await loginReady;
      return reply(route, { access_token: 'auth-test-token', token_type: 'bearer' });
    }
    if (request.url().endsWith('/auth/me')) {
      await userReady;
      return reply(route, user);
    }
    return reply(route, []);
  });
  await page.goto('/signin');
  await enterCredentials(page);
  await page.getByRole('button', { name: 'Unlock', exact: true }).click();
  await expect(page.getByLabel('Email Address')).toHaveValue(user.email);
  await expect(page.getByRole('button', { name: 'Unlock', exact: true })).toBeDisabled();
  releaseLogin();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('orion_token'))).toBe('auth-test-token');
  await expect(page).toHaveURL(/\/signin$/);
  releaseUser();
  await expect(page).toHaveURL(/\/worlds$/);
  const origin = new URL(page.url()).origin;
  expect(requests.every(request => new URL(request.url).origin === origin)).toBe(true);
  expect(requests.some(request => request.method === 'OPTIONS')).toBe(false);
  await page.reload();
  await expect(page).toHaveURL(/\/worlds$/);
  await expect(page.getByRole('button', { name: 'Open creator profile' })).toBeVisible();
});

test('duplicate registration shows the backend explanation and lets the author sign in', async ({ page }) => {
  await page.route('**/api/v1/**', route => {
    if (route.request().url().endsWith('/auth/register')) return reply(route, { detail: 'A user with this email already exists.' }, 400);
    if (route.request().url().endsWith('/auth/login')) return reply(route, { access_token: 'auth-test-token', token_type: 'bearer' });
    if (route.request().url().endsWith('/auth/me')) return reply(route, user);
    return reply(route, []);
  });
  await page.goto('/signin');
  await page.getByRole('button', { name: 'Forge an entry', exact: true }).click();
  await enterCredentials(page);
  await page.getByRole('button', { name: 'Register', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('A user with this email already exists.');
  await expect(page.getByLabel('Email Address')).toHaveValue(user.email);
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('orion-demo');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('button', { name: 'Unlock', exact: true }).click();
  await expect(page).toHaveURL(/\/worlds$/);
});

test('a failed current-user lookup clears the provisional token and preserves credentials for retry', async ({ page }) => {
  let failUser = true;
  await page.route('**/api/v1/**', route => {
    if (route.request().url().endsWith('/auth/login')) return reply(route, { access_token: 'auth-test-token', token_type: 'bearer' });
    if (route.request().url().endsWith('/auth/me')) return failUser ? reply(route, { detail: 'Account lookup unavailable.' }, 503) : reply(route, user);
    return reply(route, []);
  });
  await page.goto('/signin');
  await enterCredentials(page);
  await page.getByRole('button', { name: 'Unlock', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Account lookup unavailable.');
  expect(await page.evaluate(() => localStorage.getItem('orion_token'))).toBeNull();
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('orion-demo');
  failUser = false;
  await page.getByRole('button', { name: 'Unlock', exact: true }).click();
  await expect(page).toHaveURL(/\/worlds$/);
});

test('a stalled sign-in times out with the form intact and connection errors remain retryable', async ({ page }) => {
  let stalled = true;
  await page.route('**/api/v1/auth/login', route => {
    if (!stalled) return route.abort('connectionrefused');
    // Deliberately leave this request unanswered to exercise the real request deadline.
  });
  await page.goto('/signin');
  await enterCredentials(page);
  await page.getByRole('button', { name: 'Unlock', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('The Orion backend did not respond in time.', { timeout: 20_000 });
  await expect(page.getByRole('button', { name: 'Unlock', exact: true })).toBeEnabled();
  await expect(page.getByLabel('Email Address')).toHaveValue(user.email);
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('orion-demo');
  stalled = false;
  await page.getByRole('button', { name: 'Unlock', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Cannot reach the Orion backend.');
  await expect(page.getByRole('button', { name: 'Unlock', exact: true })).toBeEnabled();
});

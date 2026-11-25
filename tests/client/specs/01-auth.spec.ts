import { expect, test } from '@playwright/test';
import { ADMIN, AGENT_WITH_BALANCE, login, loginAdmin, shot, toastError } from './helpers';

test('protected pages send a signed-out visitor to /login', async ({ page }, info) => {
  for (const path of ['/dashboard', '/agent', '/coupons', '/search-ticket']) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login/);
  }
  await shot(page, info, 'redirected-to-login');
});

test('login page shows the form', async ({ page }, info) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: "Let's Get Started" })).toBeVisible();
  await expect(page.getByPlaceholder('Enter Phone Number')).toBeVisible();
  await expect(page.getByPlaceholder('Enter Your Pin')).toBeVisible();
  await shot(page, info, 'login-form');
});

test('empty form is refused and stays on /login', async ({ page }, info) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page).toHaveURL(/\/login/);
  await shot(page, info, 'empty');
});

test('short phone (9 digits) and short PIN (3 digits) are refused', async ({ page }, info) => {
  await login(page, '190000300', '1234');
  await expect(page).toHaveURL(/\/login/);
  await shot(page, info, 'short-phone');
  await login(page, ADMIN.phone, '123');
  await expect(page).toHaveURL(/\/login/);
  await shot(page, info, 'short-pin');
});

test('wrong PIN is rejected with an error', async ({ page }, info) => {
  await login(page, ADMIN.phone, '9999');
  await expect(page).toHaveURL(/\/login/);
  await expect(toastError(page).or(page.locator('.alert-danger'))).toBeVisible();
  await shot(page, info, 'wrong-pin');
});

test('unknown phone is rejected', async ({ page }, info) => {
  await login(page, '1999999999', '1234');
  await expect(page).toHaveURL(/\/login/);
  await expect(toastError(page).or(page.locator('.alert-danger'))).toBeVisible();
  await shot(page, info, 'unknown-phone');
});

test('a booking agent cannot use the admin portal', async ({ page }, info) => {
  await login(page, AGENT_WITH_BALANCE, '1234');
  await expect(page).not.toHaveURL(/\/(dashboard|agent)/);
  await shot(page, info, 'agent-refused');
});

test('admin logs in and lands on the dashboard; signed-in /login bounces back', async ({ page }, info) => {
  await loginAdmin(page);
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await shot(page, info, 'dashboard');
  await page.goto('/login');
  await expect(page).not.toHaveURL(/\/login/);
});

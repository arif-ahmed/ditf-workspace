import { expect, Page, test } from '@playwright/test';
import { loginAdmin, openList, shot, submit, toastError, toastSuccess } from './helpers';

test.beforeEach(async ({ page }) => loginAdmin(page));

const form = (page: Page) => ({
  code: page.getByPlaceholder('e.g. FAIR10 (no spaces)'),
  desc: page.getByPlaceholder('Who it is for (only shown here)'),
  type: page.locator('select.form-control').first(),
  value: page.locator('input[type=number]').nth(0),
  max: page.locator('input[type=number]').nth(1),
  min: page.locator('input[type=number]').nth(2),
});
const newCode = () => 'PW' + Date.now().toString(36).toUpperCase().slice(-6);

test('coupon list: search finds the seeded coupons by code', async ({ page }, info) => {
  await openList(page, '/coupons'); // later pages fill with coupons from earlier runs, so the seeded ones are found by search
  const search = page.locator('input[placeholder="Search here"]');
  await search.fill('DgePay10');
  await search.press('Enter'); // search applies on Enter
  await expect(page.locator('table tbody tr')).toHaveCount(1);
  await expect(page.locator('table')).toContainText('DgePay10');
  await shot(page, info, 'search-DgePay10');
  await search.fill('TAKA50');
  await search.press('Enter');
  await expect(page.locator('table tbody tr', { hasText: 'DgePay10' })).toHaveCount(0);
  await expect(page.locator('table')).toContainText('TAKA50');
  await shot(page, info, 'search-TAKA50');
});

test('create a percentage coupon, find it in the list', async ({ page }, info) => {
  const code = newCode();
  await page.goto('/coupons/add');
  const f = form(page);
  await f.code.fill(code);
  await f.desc.fill('playwright percent coupon');
  await f.value.fill('15');
  await f.max.fill('50');
  await f.min.fill('100');
  await shot(page, info, 'filled');
  await submit(page);
  await expect(toastSuccess(page).first()).toBeVisible();
  await openList(page, '/coupons');
  await page.locator('input[placeholder="Search here"]').fill(code);
  await page.locator('input[placeholder=\"Search here\"]').press('Enter'); // search applies on Enter
  await expect(page.locator('table tbody tr', { hasText: code })).toHaveCount(1);
  await shot(page, info, 'created');
});

test('create a fixed-amount coupon (Taka)', async ({ page }, info) => {
  const code = newCode();
  await page.goto('/coupons/add');
  const f = form(page);
  await f.code.fill(code);
  await f.type.selectOption({ index: 1 });
  await f.value.fill('25');
  await submit(page);
  await expect(page).toHaveURL(/\/coupons(\?|$)/);
  await shot(page, info, 'taka-created');
});

test('validation: empty code, empty value, percent over 100 and zero are refused', async ({ page }, info) => {
  await page.goto('/coupons/add');
  const f = form(page);
  await submit(page);
  await expect(page).toHaveURL(/\/coupons\/add/);
  await shot(page, info, 'empty');
  await f.code.fill(newCode());
  await f.value.fill('150'); // percent: max 100
  await submit(page);
  await expect(page).toHaveURL(/\/coupons\/add/);
  await shot(page, info, 'over-100');
  await f.value.fill('0');
  await submit(page);
  await expect(page).toHaveURL(/\/coupons\/add/);
  await shot(page, info, 'zero');
});

test('validation: code with spaces and a code that already exists are refused', async ({ page }, info) => {
  await page.goto('/coupons/add');
  const f = form(page);
  await f.code.fill('has space');
  await f.value.fill('5');
  await submit(page);
  await expect(page).toHaveURL(/\/coupons\/add/);
  await shot(page, info, 'code-with-space');
  await f.code.fill('DgePay10'); // seeded
  await submit(page);
  await expect(toastError(page).or(page.locator('.text-danger').first())).toBeVisible();
  await expect(page).toHaveURL(/\/coupons\/add/);
  await shot(page, info, 'duplicate-code');
});

test('validation: end date before start date is refused', async ({ page }, info) => {
  await page.goto('/coupons/add');
  const f = form(page);
  await f.code.fill(newCode());
  await f.value.fill('5');
  await page.locator('input[type=datetime-local]').nth(0).fill('2030-01-10T10:00');
  await page.locator('input[type=datetime-local]').nth(1).fill('2030-01-01T10:00');
  await submit(page);
  await expect(page).toHaveURL(/\/coupons\/add/);
  await shot(page, info, 'end-before-start');
});

test('edit: open a coupon, switch it inactive and save', async ({ page }, info) => {
  const code = newCode();
  await page.goto('/coupons/add');
  await form(page).code.fill(code);
  await form(page).value.fill('5');
  await submit(page);
  await openList(page, '/coupons');
  await page.locator('input[placeholder="Search here"]').fill(code);
  await page.locator('input[placeholder=\"Search here\"]').press('Enter'); // search applies on Enter
  await expect(page.locator('table tbody tr')).toHaveCount(1); // wait for the filter to settle
  const row = page.locator('table tbody tr', { hasText: code }).first();
  await row.locator('a.btn-icon-only').click();
  await row.getByText('Edit').click();
  await expect(page).toHaveURL(/\/coupons\/edit\//);
  await expect(page.getByRole('heading', { name: 'Edit Coupon' })).toBeVisible();
  await shot(page, info, 'edit-open');
  await page.locator('label[for=couponActive]').click();
  await submit(page);
  await expect(page).toHaveURL(/\/coupons(\?|$)/);
  await shot(page, info, 'saved');
});

test('Cancel on the coupon form returns to the list', async ({ page }) => {
  await page.goto('/coupons/add');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL(/\/coupons(\?|$)/);
});

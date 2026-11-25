import { expect, test } from '@playwright/test';
import { loginAdmin, shot, submit } from './helpers';

test.beforeEach(async ({ page }) => loginAdmin(page));

test('search ticket: seeded ticket shows its details', async ({ page }, info) => {
  await page.goto('/search-ticket');
  await page.getByPlaceholder('Enter Ticket Number').fill('7700000001');
  await submit(page);
  await expect(page.locator('app-root')).toContainText('7700000001');
  await expect(page.getByText('Ticket Details', { exact: false })).toBeVisible();
  await shot(page, info, 'found');
});

test('search ticket: a scanned ticket shows its scan history', async ({ page }, info) => {
  await page.goto('/search-ticket');
  await page.getByPlaceholder('Enter Ticket Number').fill('7700000004'); // paid and already scanned
  await submit(page);
  await expect(page.getByText('Scanned History', { exact: false })).toBeVisible();
  await shot(page, info, 'scan-history');
});

test('search ticket: empty field and unknown number show no ticket', async ({ page }, info) => {
  await page.goto('/search-ticket');
  await submit(page);
  await expect(page.getByText('Ticket Details', { exact: false })).toHaveCount(0);
  await shot(page, info, 'empty');
  await page.getByPlaceholder('Enter Ticket Number').fill('0000000000');
  await submit(page);
  await expect(page.getByText('Ticket Details', { exact: false })).toHaveCount(0);
  await shot(page, info, 'unknown');
});

test('dashboard: figures render and the date filter can be opened', async ({ page }, info) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await page.waitForTimeout(1500);
  await shot(page, info, 'today');
  await page.locator('input').first().click(); // date range picker
  await shot(page, info, 'date-picker');
});

test('leader board lists referral users', async ({ page }, info) => {
  await page.goto('/referral-leader-board');
  await expect(page.locator('table tbody tr').first()).toBeVisible();
  await shot(page, info, 'leader-board');
});

test('agents list: Export does not break the page', async ({ page }, info) => {
  await page.goto('/agent');
  await page.getByRole('button', { name: 'Export' }).click();
  await page.waitForTimeout(1500);
  await expect(page.getByRole('heading', { name: 'Booking Agents' })).toBeVisible();
  await shot(page, info, 'after-export');
});

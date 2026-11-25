import { expect, Page, test } from '@playwright/test';
import { shot } from './helpers';

// Seed data (docs/local-dev.md section 6); run scripts\seed\seed.ps1 first.
async function search(page: Page, phone: string, ref: string) {
  await page.goto('/find-ticket');
  await page.locator('#phone').fill(phone);
  await page.locator('#reference').fill(ref);
  await page.getByRole('button', { name: 'Find ticket' }).click();
}

test('paid, not-yet-scanned ticket is found', async ({ page }, info) => {
  await search(page, '01711000001', '7700000001');
  await expect(page.getByText('7700000001').first()).toBeVisible();
  await expect(page.locator('img[src*="arrow-download"]').first()).toBeVisible();
  await shot(page, info, 'found');
});

test('already-scanned ticket is refused', async ({ page }, info) => {
  await search(page, '01711000004', '7700000004');
  await expect(page.locator('p.text-danger')).toContainText('already been used');
  await shot(page, info, 'already-used');
});

test('wrong phone for a real ticket is not found', async ({ page }, info) => {
  await search(page, '01799999999', '7700000001');
  await expect(page.locator('p.text-danger')).toContainText('No ticket found');
  await shot(page, info, 'not-found');
});

test('invalid form (short phone, empty reference) sends nothing', async ({ page }, info) => {
  await page.goto('/find-ticket');
  await page.locator('#phone').fill('0171');
  await page.getByRole('button', { name: 'Find ticket' }).click();
  await expect(page.locator('p.text-danger')).toHaveCount(0);
  await expect(page.locator('img[src*="arrow-download"]')).toHaveCount(0);
  await shot(page, info, 'invalid-form');
});

test('"Book ticket" link returns to the booking page', async ({ page }, info) => {
  await page.goto('/find-ticket');
  await page.getByRole('link', { name: 'Book', exact: false }).click();
  await expect(page).toHaveURL(/trade-fair-booking/);
  await shot(page, info, 'back-to-booking');
});

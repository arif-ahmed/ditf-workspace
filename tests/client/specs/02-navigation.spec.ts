import { expect, test } from '@playwright/test';
import { loginAdmin, shot } from './helpers';

// Every screen reachable from the menu: path -> its page title. Seeded data fills the lists.
const SCREENS: [string, string, string][] = [
  ['dashboard', '/dashboard', 'Dashboard'],
  ['agents', '/agent', 'Booking Agents'],
  ['topup', '/topup-withdraw?type=1', 'Topup'],
  ['withdraw', '/topup-withdraw?type=2', 'Withdraw'],
  ['qr-scanners', '/qr-scanner-user', 'QR Scanner'],
  ['scanning-users', '/scanning-users', 'QR Scanner'],
  ['referral-users', '/referral-users', 'Referral Users'],
  ['ticket-generators', '/ticket-generator', 'Ticket Generator'],
  ['merchant-stalls', '/merchant-stall', 'Merchant Stall'],
  ['admin-staff', '/admin-staff-list', 'Admin Staff'],
  ['coupons', '/coupons', 'Coupons'],
  ['search-ticket', '/search-ticket', 'Ticket Number'],
  ['staff-qr', '/staff-qr-generator', 'Staff QR Generator'],
  ['ticket-batches', '/user-ticket-genarator', 'User Ticket Generate'],
  ['leader-board', '/referral-leader-board', 'Refferal Leader Board'],
];

test.beforeEach(async ({ page }) => loginAdmin(page));

for (const [name, path, title] of SCREENS) {
  test(`screen loads: ${name}`, async ({ page }, info) => {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: title, exact: false }).first()).toBeVisible();
    await expect(page.locator('app-root')).not.toContainText('Something went wrong');
    await page.waitForTimeout(800); // let the list fill before the screenshot
    await shot(page, info, name);
  });
}

test('menu: Dashboard link and the Users dropdown open their pages', async ({ page }, info) => {
  await page.getByRole('link', { name: 'Dashboard' }).first().click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.locator('a.dropdown-toggle').first().click();
  await shot(page, info, 'users-menu-open');
  await page.getByRole('link', { name: 'Booking Agents' }).first().click();
  await expect(page).toHaveURL(/\/agent/);
});

test('unknown route leaves the user signed in (no crash)', async ({ page }, info) => {
  await page.goto('/no-such-page');
  await shot(page, info, 'unknown-route');
  await expect(page.locator('app-root')).toBeAttached();
});

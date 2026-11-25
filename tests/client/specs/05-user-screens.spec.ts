import { expect, test } from '@playwright/test';
import { fillPerson, loginAdmin, openList, shot, submit, toastError, uniquePhone } from './helpers';

// The people screens share one shape: a list, an Add form (first/last name, phone, PIN) and the same validation.
// [name, list path, add button, add path, seeded phone that already exists, has PIN field]
const SCREENS: [string, string, string, string, string, boolean][] = [
  ['admin-staff', '/admin-staff-list', 'Add Staff', '/admin-staff-list/add', '1900005001', true],
  ['qr-scanner', '/qr-scanner-user', 'Add QR Scanner', '/qr-scanner-user/add', '1900007001', true],
  ['ticket-generator', '/ticket-generator', 'Add Ticket Generator', '/ticket-generator/add', '1900008001', true],
  ['referral-user', '/referral-users', 'Add Referral Users', '/referral-users/add', '', false],
];

test.beforeEach(async ({ page }) => loginAdmin(page));

for (const [name, list, addButton, add, existing, hasPin] of SCREENS) {
  test.describe(name, () => {
    test('list loads with seeded rows; the Add button opens the form', async ({ page }, info) => {
      await openList(page, list);
      await expect(page.locator('table tbody tr')).not.toHaveCount(0);
      await shot(page, info, 'list');
      await page.getByRole('button', { name: addButton }).click();
      await expect(page).toHaveURL(new RegExp(add.replace(/\//g, '\\/')));
      await shot(page, info, 'add-form');
    });

    test('valid person is created and returns to the list', async ({ page }, info) => {
      await page.goto(add);
      await fillPerson(page, { first: 'Pw', last: name, pin: hasPin ? '4321' : null });
      await shot(page, info, 'filled');
      await submit(page);
      await expect(page).not.toHaveURL(new RegExp(add.replace(/\//g, '\\/') + '$'));
      await shot(page, info, 'created');
    });

    test('empty form and short phone are refused', async ({ page }, info) => {
      await page.goto(add);
      await submit(page);
      await expect(page).toHaveURL(new RegExp(add.replace(/\//g, '\\/')));
      await shot(page, info, 'empty');
      await fillPerson(page, { phone: '18123', pin: hasPin ? '4321' : null });
      await submit(page);
      await expect(page).toHaveURL(new RegExp(add.replace(/\//g, '\\/')));
      await shot(page, info, 'short-phone');
    });

    if (hasPin) {
      test('3-digit PIN is refused', async ({ page }, info) => {
        await page.goto(add);
        await fillPerson(page, { phone: uniquePhone(), pin: '123' });
        await submit(page);
        await expect(page).toHaveURL(new RegExp(add.replace(/\//g, '\\/')));
        await shot(page, info, 'short-pin');
      });
    }

    if (existing) {
      test('an existing phone number is rejected', async ({ page }, info) => {
        await page.goto(add);
        await fillPerson(page, { phone: existing, pin: hasPin ? '4321' : null });
        await submit(page);
        await expect(toastError(page)).toBeVisible();
        await expect(page).toHaveURL(new RegExp(add.replace(/\//g, '\\/')));
        await shot(page, info, 'duplicate-phone');
      });
    }

    test('Cancel returns to the list', async ({ page }, info) => {
      await page.goto(add);
      await page.getByRole('button', { name: 'Cancel' }).click();
      await expect(page).toHaveURL(new RegExp(list.replace(/\//g, '\\/') + '(\\?|$)'));
      await shot(page, info, 'cancelled');
    });
  });
}

test('scanning users screen opens its Add form', async ({ page }, info) => {
  await page.goto('/scanning-users');
  await page.getByRole('button', { name: 'Add QR Scanner' }).click();
  await expect(page).toHaveURL(/\/scanning-users\/add/);
  await shot(page, info, 'scanning-add');
  await submit(page);
  await expect(page).toHaveURL(/\/scanning-users\/add/);
});

test('referral user detail shows after clicking a row', async ({ page }, info) => {
  await openList(page, '/referral-users');
  await page.locator('table tbody tr a').first().click();
  await expect(page).toHaveURL(/\/referral-users\/view\//);
  await page.waitForTimeout(800);
  await shot(page, info, 'referral-detail');
});

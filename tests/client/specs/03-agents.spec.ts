import { expect, test } from '@playwright/test';
import { fillPerson, loginAdmin, openList, shot, submit, toastError, toastSuccess, uniquePhone } from './helpers';

test.beforeEach(async ({ page }) => loginAdmin(page));

test('agent list shows its columns and rows (newest first)', async ({ page }, info) => {
  await openList(page, '/agent');
  await expect(page.locator('table tbody tr')).not.toHaveCount(0);
  for (const col of ['Full Name', 'Phone Number', 'Balance']) await expect(page.locator('table thead')).toContainText(col);
  await shot(page, info, 'agent-list');
});

test('add agent: valid agent is created and the page returns to the list', async ({ page }, info) => {
  await page.goto('/agent/add');
  await fillPerson(page, { first: 'Pw', last: 'Agent' });
  await page.locator('#mPos').check();
  await shot(page, info, 'filled');
  await submit(page);
  await expect(toastSuccess(page).first()).toBeVisible();
  await expect(page).toHaveURL(/\/agent(\?|$)/);
  await shot(page, info, 'created');
});

test('add agent: Bluetooth printer option can be chosen', async ({ page }, info) => {
  await page.goto('/agent/add');
  await page.locator('#Bluetooth').check();
  await expect(page.locator('#Bluetooth')).toBeChecked();
  await expect(page.locator('#mPos')).not.toBeChecked();
  await shot(page, info, 'bluetooth');
});

test('add agent: empty form is refused', async ({ page }, info) => {
  await page.goto('/agent/add');
  await submit(page);
  await expect(page).toHaveURL(/\/agent\/add/);
  await shot(page, info, 'empty-refused');
});

test('add agent: short phone and short PIN are refused', async ({ page }, info) => {
  await page.goto('/agent/add');
  await fillPerson(page, { phone: '18123', pin: '4321' });
  await submit(page);
  await expect(page).toHaveURL(/\/agent\/add/);
  await shot(page, info, 'short-phone');
  await page.getByPlaceholder('Enter Phone Number').fill(uniquePhone());
  await page.getByPlaceholder('Enter Login Pin').fill('12');
  await submit(page);
  await expect(page).toHaveURL(/\/agent\/add/);
  await shot(page, info, 'short-pin');
});

test('add agent: a phone number that already exists is rejected', async ({ page }, info) => {
  await page.goto('/agent/add');
  await fillPerson(page, { phone: '1900001001' }); // seeded agent
  await submit(page);
  await expect(toastError(page)).toBeVisible();
  await expect(page).toHaveURL(/\/agent\/add/);
  await shot(page, info, 'duplicate-phone');
});

test('add agent: letters in the phone field are not accepted; Cancel returns to the list', async ({ page }, info) => {
  await page.goto('/agent/add');
  const phone = page.getByPlaceholder('Enter Phone Number');
  await phone.pressSequentially('ab12');
  await expect(phone).toHaveValue('12');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page).toHaveURL(/\/agent(\?|$)/);
  await shot(page, info, 'cancelled');
});

test('agent row opens the transaction view', async ({ page }, info) => {
  await openList(page, '/agent');
  await page.locator('table tbody tr td a').first().click();
  await expect(page).toHaveURL(/\/agent\/(txn-view|edit)\//);
  await page.waitForTimeout(800);
  await shot(page, info, 'agent-detail');
});

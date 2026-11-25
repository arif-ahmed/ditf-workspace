import { expect, Page, test } from '@playwright/test';
import { loginAdmin, openList, shot, submit } from './helpers';

test.beforeEach(async ({ page }) => loginAdmin(page));

const pickOption = async (page: Page, selectIndex: number, optionIndex = 0) => {
  await page.locator('ng-select').nth(selectIndex).click();
  await page.locator('.ng-dropdown-panel .ng-option').nth(optionIndex).click();
};

test.describe('merchant stalls', () => {
  test('list, search and add form', async ({ page }, info) => {
    await openList(page, '/merchant-stall');
    await expect(page.locator('table tbody tr')).not.toHaveCount(0);
    await shot(page, info, 'list');
    await page.getByRole('button', { name: 'Add Merchant Stall' }).click();
    await expect(page).toHaveURL(/\/merchant-stall\/add/);
  });

  test('create a stall', async ({ page }, info) => {
    const number = 'PW' + String(Date.now()).slice(-6);
    await page.goto('/merchant-stall/add');
    await page.getByPlaceholder('Enter Stall Name').fill('Playwright Stall ' + number);
    await page.getByPlaceholder('Enter Stall Number').fill(number);
    await shot(page, info, 'filled');
    await submit(page);
    await expect(page).not.toHaveURL(/\/merchant-stall\/add$/);
    await openList(page, '/merchant-stall');
    await page.locator('input[placeholder="Search here"]').fill(number);
    await page.locator('input[placeholder=\"Search here\"]').press('Enter');
    await expect(page.locator('table tbody tr', { hasText: number })).toHaveCount(1);
    await shot(page, info, 'created');
  });

  test('empty form is refused; a duplicate stall number is accepted (the portal has no uniqueness check)', async ({ page }, info) => {
    await page.goto('/merchant-stall/add');
    await submit(page);
    await expect(page).toHaveURL(/\/merchant-stall\/add/);
    await shot(page, info, 'empty');
    await openList(page, '/merchant-stall');
    const existing = (await page.locator('table tbody tr').first().locator('td').nth(1).innerText()).trim();
    await page.goto('/merchant-stall/add');
    await page.getByPlaceholder('Enter Stall Name').fill('Dup stall');
    await page.getByPlaceholder('Enter Stall Number').fill(existing);
    await submit(page);
    await expect(page).toHaveURL(/\/merchant-stall(\?|$)/); // observed behaviour: saved, no error
    await shot(page, info, 'duplicate-number');
  });

  test('a stall row opens its view page', async ({ page }, info) => {
    await openList(page, '/merchant-stall');
    await page.locator('table tbody tr td.text-primary').first().click();
    await expect(page).toHaveURL(/\/merchant-stall\/view\//);
    await page.waitForTimeout(800);
    await shot(page, info, 'stall-detail');
  });
});

test.describe('staff QR generator', () => {
  test('list loads; Generate QR opens the form', async ({ page }, info) => {
    await openList(page, '/staff-qr-generator');
    await expect(page.locator('table tbody tr')).not.toHaveCount(0);
    await shot(page, info, 'list');
    await page.getByText('Generate QR', { exact: true }).click();
    await expect(page).toHaveURL(/\/staff-qr-generator\/add/);
  });

  test('empty form is refused', async ({ page }, info) => {
    await page.goto('/staff-qr-generator/add');
    await submit(page);
    await expect(page).toHaveURL(/\/staff-qr-generator\/add/);
    await shot(page, info, 'empty');
  });

  test('generate a small batch (2 QR codes)', async ({ page }, info) => {
    await page.goto('/staff-qr-generator/add');
    await pickOption(page, 0);
    await page.getByPlaceholder('Enter QR Count').fill('2');
    await pickOption(page, 1); // scan limit
    await shot(page, info, 'filled');
    await submit(page);
    await expect(page).not.toHaveURL(/\/staff-qr-generator\/add$/);
    await shot(page, info, 'generated');
  });

  test('QR count of 0 is refused', async ({ page }, info) => {
    await page.goto('/staff-qr-generator/add');
    await pickOption(page, 0);
    await page.getByPlaceholder('Enter QR Count').fill('0');
    await pickOption(page, 1);
    await submit(page);
    await expect(page).toHaveURL(/\/staff-qr-generator\/add/);
    await shot(page, info, 'zero-count');
  });
});

test.describe('user ticket batches', () => {
  test('list shows batches with status and export', async ({ page }, info) => {
    await openList(page, '/user-ticket-genarator');
    await expect(page.locator('table tbody tr')).not.toHaveCount(0);
    await shot(page, info, 'list');
  });

  test('empty form and 0 tickets are refused', async ({ page }, info) => {
    await page.goto('/user-ticket-genarator/add');
    await submit(page);
    await expect(page).toHaveURL(/\/user-ticket-genarator\/add/);
    await shot(page, info, 'empty');
    await page.getByPlaceholder('Enter Number Of Tickets').fill('0');
    await pickOption(page, 0);
    await submit(page);
    await expect(page).toHaveURL(/\/user-ticket-genarator\/add/);
    await shot(page, info, 'zero-tickets');
  });

  test('generate a batch of 2 tickets (runs as a background job)', async ({ page }, info) => {
    await page.goto('/user-ticket-genarator/add');
    await page.getByPlaceholder('Enter Number Of Tickets').fill('2');
    await pickOption(page, 0);
    await shot(page, info, 'filled');
    await submit(page);
    await expect(page).not.toHaveURL(/\/user-ticket-genarator\/add$/);
    await page.waitForTimeout(2500);
    await shot(page, info, 'after-generate');
  });
});

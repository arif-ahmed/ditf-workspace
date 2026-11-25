import { expect, Page, test } from '@playwright/test';
import { fillPerson, loginAdmin, shot, submit, toastError, toastSuccess } from './helpers';

test.beforeEach(async ({ page }) => loginAdmin(page));

/** Creates a fresh agent (balance 0) and returns its name, so every case has its own agent and a known balance. */
async function createAgent(page: Page) {
  const name = 'Pw' + Date.now().toString(36);
  await page.goto('/agent/add');
  await fillPerson(page, { first: name, last: 'Wallet' });
  await submit(page);
  await expect(toastSuccess(page).first()).toBeVisible();
  return `${name} Wallet`;
}
async function pickAgent(page: Page, name: string) {
  await page.locator('ng-select').click();
  await page.keyboard.type(name.split(' ')[0]);
  await page.locator('.ng-dropdown-panel .ng-option', { hasText: name }).first().click();
}
const amount = (page: Page) => page.getByPlaceholder('Enter Amount');
const balance = async (page: Page) => {
  const m = (await page.locator('app-root').innerText()).match(/Balance[^\d-]*(-?[\d,]+(\.\d+)?)/i);
  return m ? Number(m[1].replace(/,/g, '')) : NaN;
};

test('topup: choosing an agent shows the balance; topup raises it', async ({ page }, info) => {
  const agent = await createAgent(page);
  await page.goto('/topup-withdraw?type=1');
  await pickAgent(page, agent);
  await expect.poll(() => balance(page)).toBe(0);
  await shot(page, info, '1-agent-chosen');
  await amount(page).fill('150');
  await submit(page);
  await expect(toastSuccess(page).first()).toBeVisible();
  await shot(page, info, '2-after-topup');
  await page.goto('/topup-withdraw?type=1');
  await pickAgent(page, agent);
  await expect.poll(() => balance(page)).toBe(150);
});

test('topup: no agent or no amount is refused', async ({ page }, info) => {
  const agent = await createAgent(page);
  await page.goto('/topup-withdraw?type=1');
  await submit(page);
  await expect(toastSuccess(page)).toHaveCount(0);
  await shot(page, info, 'nothing-chosen');
  await pickAgent(page, agent);
  await submit(page);
  await expect(toastSuccess(page)).toHaveCount(0);
  await shot(page, info, 'no-amount');
});

test('topup: zero amount is refused and the balance stays 0', async ({ page }, info) => {
  const agent = await createAgent(page);
  await page.goto('/topup-withdraw?type=1');
  await pickAgent(page, agent);
  await amount(page).fill('0');
  await submit(page);
  await expect(toastSuccess(page)).toHaveCount(0);
  await shot(page, info, 'zero');
});

test('topup: letters instead of an amount are refused', async ({ page }, info) => {
  const agent = await createAgent(page);
  await page.goto('/topup-withdraw?type=1');
  await pickAgent(page, agent);
  await amount(page).fill('abc');
  await submit(page);
  await expect(toastSuccess(page)).toHaveCount(0);
  await shot(page, info, 'letters');
});

test('withdraw: part of the balance succeeds, more than the balance is refused', async ({ page }, info) => {
  const agent = await createAgent(page);
  await page.goto('/topup-withdraw?type=1');
  await pickAgent(page, agent);
  await amount(page).fill('100');
  await submit(page);
  await expect(toastSuccess(page).first()).toBeVisible();

  await page.goto('/topup-withdraw?type=2');
  await pickAgent(page, agent);
  await amount(page).fill('40');
  await submit(page);
  await expect(toastSuccess(page).first()).toBeVisible();
  await shot(page, info, '1-withdrawn');

  await page.goto('/topup-withdraw?type=2');
  await pickAgent(page, agent);
  await expect.poll(() => balance(page)).toBe(60);
  await amount(page).fill('61'); // one more than is left
  await submit(page);
  await expect(toastError(page).first()).toBeVisible();
  await shot(page, info, '2-over-balance');
});

test('withdraw: agent with zero balance cannot be debited', async ({ page }, info) => {
  const agent = await createAgent(page);
  await page.goto('/topup-withdraw?type=2');
  await pickAgent(page, agent);
  await amount(page).fill('1');
  await submit(page);
  await expect(toastError(page).first()).toBeVisible();
  await shot(page, info, 'zero-balance-refused');
});

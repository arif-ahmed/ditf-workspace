import { expect, Page, TestInfo } from '@playwright/test';

/** Seed logins (scripts/seed, docs/local-dev.md section 6). All PINs are 1234. The portal wants the phone without the leading 0 / +880. */
export const ADMIN = { phone: '1900003001', pin: '1234' };
export const AGENT_WITH_BALANCE = '1900001001';
export const AGENT_NO_BALANCE = '1900001010';

/** Full-page screenshot of the current page, attached to the HTML report. */
export async function shot(page: Page, info: TestInfo, name: string) {
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await info.attach(name, { path: file, contentType: 'image/png' });
}

export async function login(page: Page, phone = ADMIN.phone, pin = ADMIN.pin) {
  await page.goto('/login');
  await page.getByPlaceholder('Enter Phone Number').fill(phone);
  await page.getByPlaceholder('Enter Your Pin').fill(pin);
  await page.getByRole('button', { name: 'Sign In' }).click();
}

/** Logs in as the seeded admin and waits for the dashboard. */
export async function loginAdmin(page: Page) {
  await login(page);
  await expect(page).toHaveURL(/\/dashboard/);
}

/** A fresh 10-digit phone per call, so rows created by earlier runs never collide. */
let seq = 0;
export const uniquePhone = () => '18' + String(Date.now() + seq++).slice(-8);

export const toastError = (page: Page) => page.locator('.toast-error');
export const toastSuccess = (page: Page) => page.locator('.toast-success');

/** Clicks the form's Submit button. */
export const submit = (page: Page) => page.getByRole('button', { name: 'Submit' }).click();

/** Fills the standard "first name / last name / phone / PIN" form that most Add screens share (fields found by placeholder). */
export async function fillPerson(
  page: Page,
  { first = 'Pw', last = 'Test', phone = uniquePhone(), pin = '4321' }: { first?: string; last?: string; phone?: string; pin?: string | null } = {},
) {
  if (first !== undefined) await page.getByPlaceholder('Enter First Name').fill(first);
  if (last !== undefined) await page.getByPlaceholder('Enter Last Name').fill(last);
  await page.getByPlaceholder('Enter Phone Number').fill(phone);
  if (pin !== null) await page.getByPlaceholder('Enter Login Pin').fill(pin);
  return phone;
}

/** Opens a list screen and waits until its table (or the empty-state text) has rendered. */
export async function openList(page: Page, path: string) {
  await page.goto(path);
  await expect(page.locator('table tbody tr, :text("No Data Found")').first()).toBeVisible();
}

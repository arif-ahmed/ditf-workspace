import { expect, Page, TestInfo } from '@playwright/test';

/** Full-page screenshot of the current page, attached to the HTML report. */
export async function shot(page: Page, info: TestInfo, name: string) {
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await info.attach(name, { path: file, contentType: 'image/png' });
}

export async function openBooking(page: Page, query = '') {
  await page.goto(`/trade-fair-booking${query}`);
  // prices come from the API: the line shows them once booking-config has answered (seed: adult 200, child 100)
  await expect(page.getByText('Ticket price(')).toContainText('200');
}

/** Picks a count in the ng-select of the "Adult" or "Child" row (desktop table). */
export async function pickCount(page: Page, row: 'Adult' | 'Child', n: number) {
  await page.locator('table.table-class tbody tr', { hasText: row }).first().locator('ng-select').click();
  await page.locator('.ng-dropdown-panel .ng-option', { hasText: new RegExp(`^\\s*${n}\\s*$`) }).click();
}

export async function fillBooking(page: Page, { adult = 1, child = 0, phone = '01711000001' } = {}) {
  if (adult) await pickCount(page, 'Adult', adult);
  if (child) await pickCount(page, 'Child', child);
  await page.getByPlaceholder('Enter Mobile No').fill(phone);
}

/** The value cell of a payment-summary row ("Total Amount", "VAT" = "VAT (Inclusive 5%)"). */
export function summary(page: Page, label: 'Total Amount' | 'VAT') {
  return page.locator('table.table-class tr', { hasText: label }).first().locator('td').nth(1);
}

/** A fresh 11-digit phone per run, so paid bookings do not collide. */
export const phoneFor = () => '017' + String(Date.now()).slice(-8);

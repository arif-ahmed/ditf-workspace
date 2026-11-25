import { expect, test } from '@playwright/test';
import { fillBooking, openBooking, phoneFor, shot } from './helpers';

// Needs the stack started with -MockPayments: pay goes to the mock checkout page (:18081) with Pay / Fail buttons.
// These cases create real bookings in the dev database.

test('pay: booking -> mock checkout -> Pay -> payment successful, ticket ready, found again', async ({ page }, info) => {
  const phone = phoneFor();
  await openBooking(page);
  await fillBooking(page, { adult: 2, child: 1, phone });
  await shot(page, info, '1-form-filled');
  await page.getByRole('button', { name: 'Pay Now' }).click();

  await expect(page).toHaveURL(/18081\/pay\//);
  await shot(page, info, '2-mock-checkout');
  await page.getByRole('button', { name: 'Pay', exact: true }).click();

  await expect(page).toHaveURL(/\/txn-status/);
  await expect(page.getByRole('heading', { name: 'Payment Successful!' })).toBeVisible();
  await shot(page, info, '3-payment-successful');
  // the PDF is made right after payment; the page polls until the download arrow shows
  await expect(page.locator('img[src*="arrow-download"]').first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('3 Quantity')).toBeVisible();
  await shot(page, info, '4-ticket-ready');

  const ticket = (await page.locator('h4.text-black').first().innerText()).trim();
  expect(ticket).toMatch(/\d+/);

  await page.getByRole('link', { name: 'Find my ticket', exact: false }).click();
  await page.locator('#phone').fill(phone);
  await page.locator('#reference').fill(ticket);
  await page.getByRole('button', { name: 'Find ticket' }).click();
  await expect(page.getByText(ticket).first()).toBeVisible();
  await shot(page, info, '5-find-ticket-result');
});

test('pay: Fail on the mock checkout -> payment failed, Try Again returns to booking', async ({ page }, info) => {
  await openBooking(page);
  await fillBooking(page, { adult: 1, phone: phoneFor() });
  await page.getByRole('button', { name: 'Pay Now' }).click();
  await expect(page).toHaveURL(/18081\/pay\//);
  await page.getByRole('button', { name: 'Fail' }).click();

  await expect(page).toHaveURL(/\/txn-status/);
  await expect(page.getByRole('heading', { name: 'Payment Failed!' })).toBeVisible();
  await shot(page, info, '1-payment-failed');
  await page.getByRole('button', { name: 'Try Again' }).click();
  await expect(page).toHaveURL(/trade-fair-booking/);
  await shot(page, info, '2-back-to-booking');
});

test('txn-status without a (valid) booking id shows the session-expired state', async ({ page }, info) => {
  await page.goto('/txn-status');
  await expect(page.getByRole('heading', { name: 'Session Expired' })).toBeVisible();
  await shot(page, info, 'session-expired');
  await page.goto('/txn-status?booking_master_id=does-not-exist');
  await expect(page.getByRole('heading', { name: 'Session Expired' })).toBeVisible();
});

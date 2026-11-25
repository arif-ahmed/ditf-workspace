import { expect, test } from '@playwright/test';
import { fillBooking, openBooking, pickCount, shot, summary } from './helpers';

test('booking page loads with prices and the form', async ({ page }, info) => {
  await openBooking(page);
  await expect(page.getByRole('heading', { name: 'Trade Fair Ticket Booking' })).toBeVisible();
  await expect(page.getByText('Ticket price(')).toContainText('100');
  await expect(page.getByRole('button', { name: 'Pay Now' })).toBeEnabled();
  await shot(page, info, 'booking-loaded');
});

test('root and unknown URLs redirect to the booking page', async ({ page }, info) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/trade-fair-booking$/);
  await page.goto('/no-such-page');
  await expect(page).toHaveURL(/\/trade-fair-booking$/);
  await shot(page, info, 'redirected');
});

test('totals follow the ticket counts (VAT 5% inclusive)', async ({ page }, info) => {
  await openBooking(page);
  await pickCount(page, 'Adult', 2);
  await expect(summary(page, 'Total Amount')).toContainText('400.00');
  await expect(summary(page, 'VAT')).toContainText('20.00');
  await shot(page, info, 'two-adults');
  await pickCount(page, 'Child', 1);
  await expect(summary(page, 'Total Amount')).toContainText('500.00');
  await expect(summary(page, 'VAT')).toContainText('25.00');
  await shot(page, info, 'two-adults-one-child');
});

test('Pay Now with no phone / a short phone shows an error and stays on the page', async ({ page }, info) => {
  await openBooking(page);
  await page.getByRole('button', { name: 'Pay Now' }).click();
  await expect(page.locator('.toast-error')).toBeVisible();
  await shot(page, info, 'error-no-phone');
  await expect(page).toHaveURL(/trade-fair-booking/);

  await fillBooking(page, { adult: 1, phone: '0171100' });
  await page.getByRole('button', { name: 'Pay Now' }).click();
  await expect(page.locator('.toast-error').last()).toBeVisible();
  await shot(page, info, 'error-short-phone');
});

test('coupon from the link discounts the total; an unknown coupon is flagged', async ({ page }, info) => {
  await openBooking(page, `?code=${Buffer.from('DgePay10').toString('base64')}`);
  await pickCount(page, 'Adult', 2); // 10% of 400 = 40, capped at 15
  await expect(page.getByText('Coupon Discount').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Applied' })).toBeVisible();
  await shot(page, info, 'coupon-applied');

  await openBooking(page, `?code=${Buffer.from('NOPE').toString('base64')}`);
  await pickCount(page, 'Adult', 1);
  await expect(page.locator('small.text-danger').first()).toBeVisible();
  await shot(page, info, 'coupon-invalid');
});

test('referral code: seeded one is applied, unknown one is rejected', async ({ page }, info) => {
  await openBooking(page);
  const ref = page.getByPlaceholder('Enter Refferal');
  await ref.fill('001');
  await page.getByRole('button', { name: 'Apply' }).last().click();
  await expect(page.getByRole('button', { name: 'Applied' })).toBeVisible();
  await shot(page, info, 'referral-valid');
  await page.getByLabel('Clear').click();
  await ref.fill('zzz-unknown');
  await page.getByRole('button', { name: 'Apply' }).last().click();
  await expect(page.locator('small.text-danger').last()).toBeVisible();
  await shot(page, info, 'referral-invalid');
});

test('language toggle switches to Bangla and back', async ({ page }, info) => {
  await openBooking(page);
  await page.locator('label.toggle-label').click();
  await expect(page.getByRole('heading', { name: 'বাণিজ্য মেলার টিকেট বুকিং' })).toBeVisible();
  await shot(page, info, 'bangla');
  await page.locator('label.toggle-label').click();
  await expect(page.getByRole('heading', { name: 'Trade Fair Ticket Booking' })).toBeVisible();
});

test('terms link opens the terms page; back returns to booking', async ({ page }, info) => {
  await openBooking(page);
  await page.getByRole('checkbox').check();
  await page.locator('span.text-primary.pointer').click();
  await expect(page).toHaveURL(/terms-and-conditions/);
  await expect(page.getByRole('heading', { name: 'Terms And Conditions' })).toBeVisible();
  await shot(page, info, 'terms');
  await page.locator('img[src*="back-white"]').click();
  await expect(page).toHaveURL(/trade-fair-booking/);
});

test('"Find my ticket" link goes to the find-ticket page', async ({ page }, info) => {
  await openBooking(page);
  await page.getByRole('link', { name: 'Find my ticket', exact: false }).click();
  await expect(page).toHaveURL(/find-ticket/);
  await shot(page, info, 'find-ticket-opened');
});

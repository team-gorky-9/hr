import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, timezoneId: 'Europe/Moscow' });
page.setDefaultTimeout(10_000);
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.clock.install({ time: new Date('2026-11-20T10:00:00+03:00') });
  await page.goto(process.env.TEST_URL || 'http://127.0.0.1:5189');
  console.log('Loaded page');
  await page.getByRole('button', { name: 'Кабинет HR-менеджера', exact: true }).click();
  await page.getByText('Фролов Денис', { exact: true }).click();
  await page.getByRole('button', { name: 'Направить в департамент', exact: true }).click();
  await page.getByRole('button', { name: 'Направить', exact: true }).click();
  console.log('Forwarded candidate');
  const bar = page.getByRole('progressbar', { name: 'Срок ответа департамента' });
  await bar.waitFor();
  assert.equal(await bar.getAttribute('aria-valuenow'), '0');
  assert.equal(await bar.getAttribute('aria-valuemax'), '10');
  assert.equal(await bar.locator('div').evaluate(el => el.style.width), '0%');
  const original = await page.evaluate(() => localStorage.getItem('hr:profile-handoff:v1:c1'));
  assert.equal(JSON.parse(original).dueOn, '2026-12-04');

  for (const [day, elapsed, color] of [
    ['2026-11-30', 6, 'rgb(21, 128, 61)'],
    ['2026-12-01', 7, 'rgb(217, 119, 6)'],
    ['2026-12-07', 11, 'rgb(155, 28, 28)'],
  ]) {
    await page.clock.setFixedTime(new Date(`${day}T10:00:00+03:00`));
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await page.waitForFunction(expected => document.querySelector('[role="progressbar"]')?.getAttribute('aria-valuetext') === expected,
      `Прошло ${elapsed} из 10 рабочих дней`);
    assert.equal(await bar.locator('div').evaluate(el => getComputedStyle(el).backgroundColor), color);
    assert.equal(await bar.locator('div').evaluate(el => el.style.width), `${Math.min(elapsed * 10, 100)}%`);
  }
  await bar.scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'handoff-overdue.local.png', animations: 'disabled' });
  assert.equal(await bar.evaluate(el => Math.round(el.firstElementChild.getBoundingClientRect().width / el.getBoundingClientRect().width * 100)), 100);
  await page.getByRole('button', { name: 'Продлить срок', exact: true }).click();
  console.log('Opened extension');
  await page.getByLabel('Новый срок', { exact: true }).fill('2026-12-11');
  await page.getByLabel('Причина продления', { exact: true }).fill('Руководитель в командировке');
  await page.getByRole('button', { name: 'Продлить срок', exact: true }).click();
  await bar.waitFor();
  assert.equal(await bar.getAttribute('aria-valuetext'), 'Прошло 11 из 15 рабочих дней');
  assert.equal(await bar.locator('div').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(21, 128, 61)');
  await bar.scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'handoff-extended.local.png', animations: 'disabled' });

  const saved = await page.evaluate(() => localStorage.getItem('hr:profile-handoff:v1:c1'));
  await page.getByRole('button', { name: 'Демо: показать истёкший срок', exact: true }).click();
  assert.equal(await bar.getAttribute('aria-valuetext'), 'Прошло 11 из 10 рабочих дней');
  assert.equal(await page.evaluate(() => localStorage.getItem('hr:profile-handoff:v1:c1')), saved);
  await page.reload();
  await page.getByRole('button', { name: 'Кабинет HR-менеджера', exact: true }).click();
  await page.getByText('Фролов Денис', { exact: true }).click();
  await bar.waitFor();
  assert.equal(await bar.getAttribute('aria-valuetext'), 'Прошло 11 из 15 рабочих дней');
  await page.getByRole('button', { name: 'Единая база', exact: true }).last().click();
  await page.getByText('Ковалёва Анна', { exact: true }).click();
  assert.equal(await bar.count(), 0, 'another candidate must not inherit the timer');
  assert.deepEqual(errors, []);
  console.log('PASS: date changes, colors, width, extension, preview isolation, reload and candidate isolation');
} catch (error) {
  await page.screenshot({ path: 'handoff-failure.local.png' });
  console.error((await page.locator('body').innerText()).slice(-6000));
  throw error;
} finally {
  await browser.close();
}

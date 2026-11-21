import assert from 'node:assert/strict';
import { test } from 'node:test';
import { addWorkingDays, deadlineProgress, moscowDay } from '../src/components/hr/handoffDeadline.ts';

test('forwarding starts at day zero, skips weekends, then warns and expires', () => {
  const sentOn = '2026-11-20'; // Friday; due on Friday, December 4.
  assert.equal(addWorkingDays(sentOn, 10), '2026-12-04');
  for (const [day, elapsed, percent, status] of [
    ['2026-11-20', 0, 0, 'on_track'],
    ['2026-11-22', 0, 0, 'on_track'],
    ['2026-11-23', 1, 10, 'on_track'],
    ['2026-11-30', 6, 60, 'on_track'],
    ['2026-12-01', 7, 70, 'due_soon'],
    ['2026-12-04', 10, 100, 'due_soon'],
    ['2026-12-05', 10, 100, 'overdue'],
    ['2026-12-07', 11, 100, 'overdue'],
  ] as const) {
    const value = deadlineProgress(sentOn, '2026-12-04', day);
    assert.equal(value.elapsed, elapsed, day);
    assert.equal(value.percent, percent, day);
    assert.equal(value.status, status, day);
  }
});

test('calendar holidays and working Saturdays match the product calendar', () => {
  assert.equal(addWorkingDays('2026-11-03', 1), '2026-11-05');
  assert.equal(addWorkingDays('2025-10-31', 1), '2025-11-01');
  assert.equal(addWorkingDays('2026-12-30', 1), '2027-01-11');
});

test('extension restores the status without resetting the original sent date', () => {
  const value = deadlineProgress('2026-11-20', '2026-12-11', '2026-12-07');
  assert.equal(value.elapsed, 11);
  assert.equal(value.total, 15);
  assert.equal(value.status, 'on_track');
  assert.equal(deadlineProgress('2026-11-20', '2026-12-11', '2026-12-08').status, 'due_soon');
});

test('Moscow midnight advances the date independently of the device time zone', () => {
  assert.equal(moscowDay(new Date('2026-11-22T20:59:59Z')), '2026-11-22');
  assert.equal(moscowDay(new Date('2026-11-22T21:00:00Z')), '2026-11-23');
});

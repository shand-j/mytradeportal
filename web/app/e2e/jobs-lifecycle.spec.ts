import { test, expect } from './fixtures';
import { createCustomer, createJob, startJobFromBoard, completeJobFromBoard } from './helpers';

function jobCardInColumn(page, reference: string, column: string) {
  return page
    .locator('div.rounded-xl.border', { has: page.locator('span', { hasText: new RegExp(`^${column}$`) }) })
    .locator('div.rounded-lg', { hasText: reference })
    .first();
}

test('create a job and move it through the board', async ({ page, testId }) => {
  const customerName = await createCustomer(page, testId);
  const reference = await createJob(page, customerName, testId);

  await page.goto('/jobs');
  await expect(jobCardInColumn(page, reference, 'Scheduled')).toBeVisible();

  await startJobFromBoard(page, reference);
  await expect(jobCardInColumn(page, reference, 'In Progress')).toBeVisible();

  await completeJobFromBoard(page, reference);
  await expect(jobCardInColumn(page, reference, 'Completed')).toBeVisible();
});

import { test as base, expect } from '@playwright/test';

export interface TestFixtures {
  /** A short unique token for the current test; use it in customer/quote references to avoid collisions. */
  testId: string;
}

export const test = base.extend<TestFixtures>({
  testId: async ({}, use) => {
    const id = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    await use(id);
  },
});

export { expect };

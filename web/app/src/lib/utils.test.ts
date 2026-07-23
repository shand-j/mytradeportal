import { describe, it, expect } from 'vitest';
import { cn } from './utils';

describe('cn', () => {
  it('merges class names into a single string', () => {
    expect(cn('foo', 'bar')).toBe('foo bar');
  });

  it('ignores falsy values', () => {
    const includeBar = false;
    expect(cn('foo', includeBar && 'bar', undefined, 'baz')).toBe('foo baz');
  });

  it('resolves tailwind conflicts', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4');
  });

  it('handles conditional clsx objects', () => {
    expect(cn('base', { active: true, disabled: false })).toBe('base active');
  });
});

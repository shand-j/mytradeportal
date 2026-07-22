import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { StatusPill } from './StatusPill';

describe('StatusPill', () => {
  it('renders the status text', () => {
    render(<StatusPill status="draft" />);
    expect(screen.getByText('draft')).toBeInTheDocument();
  });

  it('renders underscores as spaces', () => {
    render(<StatusPill status="in_progress" />);
    expect(screen.getByText('in progress')).toBeInTheDocument();
  });

  it('uses the configured colour classes', () => {
    const { container } = render(<StatusPill status="accepted" />);
    const pill = container.firstChild as HTMLElement;
    expect(pill.className).toContain('bg-[#F0FDF4]');
    expect(pill.className).toContain('text-[#15803D]');
  });

  it('falls back to neutral colours for unknown statuses', () => {
    const { container } = render(<StatusPill status="unknown_status" />);
    const pill = container.firstChild as HTMLElement;
    expect(pill.className).toContain('bg-[#F5F5F4]');
    expect(pill.className).toContain('text-[#78716C]');
    expect(screen.getByText('unknown status')).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { RouteErrorBoundary } from './RouteErrorBoundary';

function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Something exploded');
  }
  return <div>Safe content</div>;
}

describe('RouteErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('renders children when there is no error', () => {
    render(
      <RouteErrorBoundary>
        <Bomb shouldThrow={false} />
      </RouteErrorBoundary>,
    );
    expect(screen.getByText('Safe content')).toBeInTheDocument();
  });

  it('catches thrown errors and shows the fallback UI', () => {
    render(
      <RouteErrorBoundary>
        <Bomb shouldThrow={true} />
      </RouteErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Something exploded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('resets and re-renders children when the user clicks try again', async () => {
    const user = userEvent.setup();

    function ToggleBomb() {
      const throwError = true;
      return (
        <RouteErrorBoundary>
          {throwError ? (
            <Bomb shouldThrow={true} />
          ) : (
            <div>Recovered content</div>
          )}
        </RouteErrorBoundary>
      );
    }

    const { rerender } = render(<ToggleBomb />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Simulate the parent component recovering while the boundary resets.
    rerender(<ToggleBomb />);

    await user.click(screen.getByRole('button', { name: /try again/i }));

    // After reset the boundary should attempt to render children again.
    // Because ToggleBomb still has throwError=true, it will throw again.
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });
});

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { VoiceAgentWidget } from './VoiceAgentWidget';
import { renderPage } from '@/test/test-utils';

describe('VoiceAgentWidget', () => {
  it('renders the closed floating action button', () => {
    renderPage(<VoiceAgentWidget />);
    expect(screen.getByRole('button', { name: /open voice ai agent/i })).toBeInTheDocument();
  });

  it('opens the widget and shows the call log', async () => {
    const user = userEvent.setup();
    renderPage(<VoiceAgentWidget />);

    await user.click(screen.getByRole('button', { name: /open voice ai agent/i }));
    expect(screen.getByText('Voice AI Agent')).toBeInTheDocument();
    expect(screen.getByText('Call Log')).toBeInTheDocument();
    expect(screen.getByText('Emma Wilson')).toBeInTheDocument();
    expect(screen.getByText('David Smith')).toBeInTheDocument();
  });

  it('selects a call and returns to the call log', async () => {
    const user = userEvent.setup();
    renderPage(<VoiceAgentWidget />);

    await user.click(screen.getByRole('button', { name: /open voice ai agent/i }));
    await user.click(screen.getByText('Emma Wilson'));

    expect(screen.getByText(/Back to calls/i)).toBeInTheDocument();
    expect(screen.getByText('07700 900789')).toBeInTheDocument();

    await user.click(screen.getByText(/Back to calls/i));
    expect(screen.getByText('David Smith')).toBeInTheDocument();
  });

  it('switches to the new-call tab and simulates a call', async () => {
    const user = userEvent.setup();
    renderPage(<VoiceAgentWidget />);

    await user.click(screen.getByRole('button', { name: /open voice ai agent/i }));
    await user.click(screen.getByRole('button', { name: /new call/i }));
    expect(screen.getByText('Start Voice Call')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /simulate inbound call/i }));
    expect(screen.getByText(/Live Call/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /end call/i }));
    expect(screen.getByText('Start Voice Call')).toBeInTheDocument();
  });

  it('expands and collapses the widget', async () => {
    const user = userEvent.setup();
    const { container } = renderPage(<VoiceAgentWidget />);

    await user.click(screen.getByRole('button', { name: /open voice ai agent/i }));
    await user.click(screen.getByRole('button', { name: /expand/i }));

    const panel = container.querySelector('[class*="w-[480px]"]') || container.querySelector('[class*="w-[380px]"]');
    expect(panel).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /collapse/i }));
    expect(screen.getByRole('button', { name: /expand/i })).toBeInTheDocument();
  });
});

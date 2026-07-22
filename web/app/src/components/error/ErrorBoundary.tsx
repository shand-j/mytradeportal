import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Catches JavaScript errors anywhere in its child component tree and renders a
 * fallback UI instead of crashing the whole app. Use this around route pages or
 * any complex component whose data shape you do not fully trust.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, info.componentStack);
  }

  private handleReset = () => {
    this.props.onReset?.();
    this.setState({ hasError: false, error: null });
  };

  override render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-[50vh] flex items-center justify-center p-6">
          <div className="max-w-md w-full bg-white rounded-xl border border-[#E7E5E4] p-6 shadow-sm text-center">
            <div className="mx-auto w-12 h-12 rounded-full bg-[#FEF2F2] flex items-center justify-center mb-4">
              <AlertTriangle className="w-6 h-6 text-[#DC2626]" />
            </div>
            <h2 className="text-lg font-semibold text-[#1C1917] mb-2">
              Something went wrong
            </h2>
            <p className="text-sm text-[#78716C] mb-4">
              This part of the page could not be displayed. You can try again or
              refresh the page.
            </p>
            {this.state.error && (
              <pre className="text-left text-xs bg-[#F5F4F0] rounded-lg p-3 mb-4 overflow-auto text-[#57534E]">
                {this.state.error.message}
              </pre>
            )}
            <Button
              onClick={this.handleReset}
              className="bg-[#1C1917] hover:bg-[#292524] text-white"
            >
              <RotateCcw className="w-4 h-4 mr-2" />
              Try again
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

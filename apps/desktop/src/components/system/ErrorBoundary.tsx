import type { ErrorInfo, ReactNode } from "react";
import { Component } from "react";
import { PageState } from "./PageState";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Route render failed", error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <PageState
          tone="error"
          title="Page failed"
          body={this.state.error.message}
          meta="ROUTE_RENDER_ERROR"
        />
      );
    }

    return this.props.children;
  }
}


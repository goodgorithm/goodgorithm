import { Component, type ErrorInfo, type ReactNode } from "react";

import styles from "./FeedStatus.module.css";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// React has no hook-based equivalent to this - a class component is the
// only way to catch a render/lifecycle error in the tree below it.
// Without it, any uncaught exception (a malformed post shape, a null-ref
// in a rarely-hit branch, anything) unmounts the *entire* React tree with
// no recovery path and no diagnostic trail. Wraps just the feed/content-
// page area, not the whole <main>, so the header/nav survive a crash
// below it and stay usable.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // No error-reporting service wired up - this is at least a real,
    // findable trail in the console instead of a silent blank page.
    console.error("Goodgorithm crashed:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className={styles.notice}>
          <p>Something went wrong.</p>
          <p className={styles.detail}>
            <small>{this.state.error.message}</small>
          </p>
          <button type="button" className={styles.action} onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

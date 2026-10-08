import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback: (error: Error) => ReactNode
}

interface State {
  error: Error | null
}

/** Shows `fallback` when rendering (including a rejected `use` promise) throws below it. */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null }

  static getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error : new Error(String(error)) }
  }

  override render(): ReactNode {
    return this.state.error ? this.props.fallback(this.state.error) : this.props.children
  }
}

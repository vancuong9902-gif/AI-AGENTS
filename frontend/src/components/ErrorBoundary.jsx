import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 240, gap: 16, padding: 32 }}>
          <div style={{ fontSize: 48 }}>⚠️</div>
          <h2>Đã xảy ra lỗi giao diện</h2>
          <p>{this.state.error?.message || "Vui lòng tải lại trang."}</p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.reload();
            }}
          >
            🔄 Tải lại trang
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

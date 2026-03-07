import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./App.css";

// Перехватывает ошибки рендера и показывает их вместо белого экрана
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: 32, fontFamily: "monospace", color: "#DC2626",
          background: "#FEF2F2", minHeight: "100vh"
        }}>
          <h2>Ошибка — скопируй текст ниже и отправь разработчику</h2>
          <pre style={{ whiteSpace: "pre-wrap", marginTop: 16, fontSize: 12,
            background: "#fff", padding: 16, borderRadius: 8, border: "1px solid #FECACA" }}>
            {this.state.error.toString()}
            {"\n\n--- Stack ---\n"}
            {this.state.error.stack}
          </pre>
          <button
            onClick={() => this.setState({ error: null })}
            style={{ marginTop: 16, padding: "8px 16px", cursor: "pointer",
              background: "#2563EB", color: "#fff", border: "none", borderRadius: 6 }}
          >
            Попробовать снова
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);

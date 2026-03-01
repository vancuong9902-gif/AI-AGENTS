import React from "react";

function ChartShell({ title, children }) {
  return (
    <div className="chart-shell">
      {title ? <div className="chart-shell-title">{title}</div> : null}
      <div className="chart-shell-body">{children}</div>
    </div>
  );
}

function passthrough(displayName, element = "div") {
  function Wrapped({ children }) {
    return React.createElement(element, { className: `chart-${displayName.toLowerCase()}` }, children);
  }
  Wrapped.displayName = displayName;
  return Wrapped;
}

export const ResponsiveContainer = ({ children }) => <ChartShell>{children}</ChartShell>;
export const CartesianGrid = passthrough("CartesianGrid");
export const Legend = passthrough("Legend");
export const XAxis = passthrough("XAxis");
export const YAxis = passthrough("YAxis");
export const Tooltip = () => null;
export const Cell = () => null;
export const PolarGrid = passthrough("PolarGrid");
export const PolarAngleAxis = passthrough("PolarAngleAxis");
export const PolarRadiusAxis = passthrough("PolarRadiusAxis");

export const BarChart = ({ data = [], children }) => (
  <ChartShell title={`Dữ liệu: ${data.length} mục`}>{children}</ChartShell>
);

export const LineChart = ({ data = [], children }) => (
  <ChartShell title={`Dữ liệu: ${data.length} điểm`}>{children}</ChartShell>
);

export const PieChart = passthrough("PieChart");
export const RadarChart = passthrough("RadarChart");

export const Bar = ({ dataKey, name }) => <div className="chart-series">{name || dataKey || "series"}</div>;
export const Line = ({ dataKey, name }) => <div className="chart-series">{name || dataKey || "series"}</div>;
export const Pie = ({ data = [], nameKey, dataKey }) => (
  <ul className="chart-list">
    {data.map((item, index) => (
      <li key={index}>{String(item?.[nameKey] ?? `Mục ${index + 1}`)}: {String(item?.[dataKey] ?? 0)}</li>
    ))}
  </ul>
);

export const Radar = ({ dataKey, name }) => <div className="chart-series">{name || dataKey || "series"}</div>;

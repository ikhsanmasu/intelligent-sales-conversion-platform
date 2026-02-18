import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";
const DAY_OPTIONS = [7, 30, 90];

function formatTokenCount(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function formatCostUsd(value) {
  const amount = Number(value || 0);
  if (amount >= 100) return `$${amount.toFixed(2)}`;
  if (amount >= 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(5)}`;
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatDateLabel(epochSeconds) {
  if (!epochSeconds) return "-";
  const date = new Date(epochSeconds * 1000);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDayLabel(dayKey) {
  if (!dayKey) return "-";
  const date = new Date(`${dayKey}T00:00:00Z`);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function MetricCard({ title, value, hint }) {
  return (
    <article className="billing-metric-card">
      <p className="billing-metric-title">{title}</p>
      <p className="billing-metric-value">{value}</p>
      {hint ? <p className="billing-metric-hint">{hint}</p> : null}
    </article>
  );
}

function CostLineChart({ points }) {
  if (!points.length) {
    return <div className="billing-chart-empty">No usage data in this range.</div>;
  }

  const width = 860;
  const height = 240;
  const padX = 24;
  const padY = 22;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;
  const maxCost = Math.max(...points.map((point) => Number(point.total_cost_usd || 0)), 0);
  const yTop = maxCost <= 0 ? 1 : maxCost * 1.15;
  const stepX = points.length > 1 ? plotW / (points.length - 1) : 0;

  const coords = points.map((point, index) => {
    const x = padX + index * stepX;
    const ratio = Number(point.total_cost_usd || 0) / yTop;
    const y = padY + (1 - ratio) * plotH;
    return { x, y, raw: Number(point.total_cost_usd || 0), day: point.date };
  });

  const linePath = coords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1].x.toFixed(2)} ${(padY + plotH).toFixed(
    2
  )} L ${coords[0].x.toFixed(2)} ${(padY + plotH).toFixed(2)} Z`;

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const y = padY + (1 - ratio) * plotH;
    const value = yTop * ratio;
    return { y, value };
  });

  const first = coords[0];
  const middle = coords[Math.floor((coords.length - 1) / 2)];
  const last = coords[coords.length - 1];

  return (
    <div className="billing-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="billing-chart-svg" role="img">
        <defs>
          <linearGradient id="costArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--billing-accent)" stopOpacity="0.24" />
            <stop offset="100%" stopColor="var(--billing-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {yTicks.map((tick, idx) => (
          <g key={idx}>
            <line
              x1={padX}
              y1={tick.y}
              x2={padX + plotW}
              y2={tick.y}
              stroke="var(--billing-grid)"
              strokeWidth="1"
            />
            <text x={padX + 2} y={tick.y - 4} className="billing-chart-axis-label">
              {formatCostUsd(tick.value)}
            </text>
          </g>
        ))}

        <path d={areaPath} fill="url(#costArea)" />
        <path d={linePath} fill="none" stroke="var(--billing-accent)" strokeWidth="2.2" />

        {coords.map((point, idx) => (
          <circle
            key={idx}
            cx={point.x}
            cy={point.y}
            r={2.4}
            fill="var(--billing-accent)"
            opacity={idx === coords.length - 1 ? 1 : 0.75}
          >
            <title>
              {formatDayLabel(point.day)}: {formatCostUsd(point.raw)}
            </title>
          </circle>
        ))}

        {[first, middle, last].map((point, idx) => (
          <text key={idx} x={point.x} y={height - 4} textAnchor="middle" className="billing-chart-axis-label">
            {formatDayLabel(point.day)}
          </text>
        ))}
      </svg>
    </div>
  );
}

function TokenStackedChart({ points }) {
  if (!points.length) {
    return <div className="billing-chart-empty">No token data in this range.</div>;
  }

  const sampled = points.slice(-21);
  const width = 860;
  const height = 240;
  const padX = 24;
  const padY = 20;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;
  const maxTokens = Math.max(...sampled.map((point) => Number(point.total_tokens || 0)), 1);
  const stride = plotW / sampled.length;
  const barWidth = Math.max(3, Math.min(16, stride * 0.66));
  const startX = padX + (stride - barWidth) / 2;

  const first = sampled[0];
  const middle = sampled[Math.floor((sampled.length - 1) / 2)];
  const last = sampled[sampled.length - 1];

  return (
    <div className="billing-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="billing-chart-svg" role="img">
        <line x1={padX} y1={padY + plotH} x2={padX + plotW} y2={padY + plotH} stroke="var(--billing-grid)" />
        <line x1={padX} y1={padY} x2={padX} y2={padY + plotH} stroke="var(--billing-grid)" />

        {sampled.map((point, idx) => {
          const input = Number(point.input_tokens || 0);
          const output = Number(point.output_tokens || 0);
          const inputH = (input / maxTokens) * plotH;
          const outputH = (output / maxTokens) * plotH;
          const x = startX + idx * stride;
          const inputY = padY + plotH - inputH;
          const outputY = inputY - outputH;

          return (
            <g key={idx}>
              <rect x={x} y={inputY} width={barWidth} height={inputH} fill="var(--billing-token-input)" rx="2">
                <title>
                  {formatDayLabel(point.date)} | Input: {formatTokenCount(input)} | Output:{" "}
                  {formatTokenCount(output)}
                </title>
              </rect>
              <rect
                x={x}
                y={outputY}
                width={barWidth}
                height={outputH}
                fill="var(--billing-token-output)"
                rx="2"
              />
            </g>
          );
        })}

        {[first, middle, last].map((point, idx) => {
          const pointIndex = sampled.indexOf(point);
          const x = startX + pointIndex * stride + barWidth / 2;
          return (
            <text key={idx} x={x} y={height - 4} textAnchor="middle" className="billing-chart-axis-label">
              {formatDayLabel(point.date)}
            </text>
          );
        })}
      </svg>
      <div className="billing-chart-legend">
        <span>
          <i className="dot input" /> Input tokens
        </span>
        <span>
          <i className="dot output" /> Output tokens
        </span>
      </div>
    </div>
  );
}

export default function BillingPanel({ userId = "0" }) {
  const [rangeDays, setRangeDays] = useState(30);
  const [billing, setBilling] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const fetchBillingSummary = async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(
          `${API_BASE}/v1/billing/summary/${encodeURIComponent(userId)}?days=${rangeDays}&recent_limit=60`
        );
        if (!res.ok) {
          throw new Error("Failed to load billing data");
        }
        const data = await res.json();
        if (!cancelled) {
          setBilling(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Failed to load billing data");
          setBilling(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchBillingSummary();
    return () => {
      cancelled = true;
    };
  }, [rangeDays, reloadTick, userId]);

  const totals = billing?.totals || {
    requests: 0,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    input_cost_usd: 0,
    output_cost_usd: 0,
    total_cost_usd: 0,
  };
  const byModel = billing?.by_model || [];
  const daily = billing?.daily || [];
  const recent = billing?.recent || [];

  const modelRows = useMemo(() => {
    const totalCost = Number(totals.total_cost_usd || 0) || 1;
    return byModel.map((row) => ({
      ...row,
      share: Number(row.total_cost_usd || 0) / totalCost,
    }));
  }, [byModel, totals.total_cost_usd]);

  const avgCostPerRequest = totals.requests > 0 ? totals.total_cost_usd / totals.requests : 0;

  return (
    <main className="billing-panel">
      <header className="billing-header">
        <div>
          <h1>Usage &amp; Billing</h1>
          <p>Track model usage, token consumption, and estimated spend across model changes.</p>
        </div>

        <div className="billing-actions">
          <div className="billing-range-picker">
            {DAY_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={`billing-range-btn ${rangeDays === option ? "active" : ""}`}
                onClick={() => setRangeDays(option)}
              >
                {option}D
              </button>
            ))}
          </div>
          <button type="button" className="billing-refresh-btn" onClick={() => setReloadTick((v) => v + 1)}>
            Refresh
          </button>
        </div>
      </header>

      {error ? <div className="billing-error">{error}</div> : null}

      <section className="billing-metrics">
        <MetricCard
          title="Total Cost"
          value={formatCostUsd(totals.total_cost_usd)}
          hint={`${formatCostUsd(avgCostPerRequest)} avg / request`}
        />
        <MetricCard
          title="Total Tokens"
          value={formatTokenCount(totals.total_tokens)}
          hint={`${formatTokenCount(totals.requests)} requests`}
        />
        <MetricCard
          title="Input Tokens"
          value={formatTokenCount(totals.input_tokens)}
          hint={formatCostUsd(totals.input_cost_usd)}
        />
        <MetricCard
          title="Output Tokens"
          value={formatTokenCount(totals.output_tokens)}
          hint={formatCostUsd(totals.output_cost_usd)}
        />
      </section>

      <section className="billing-grid">
        <article className="billing-card">
          <div className="billing-card-head">
            <h2>Cost Trend</h2>
            <p>Daily estimated cost for the last {rangeDays} days</p>
          </div>
          {loading ? <div className="billing-chart-empty">Loading...</div> : <CostLineChart points={daily} />}
        </article>

        <article className="billing-card">
          <div className="billing-card-head">
            <h2>Token Trend</h2>
            <p>Stacked input/output tokens per day</p>
          </div>
          {loading ? <div className="billing-chart-empty">Loading...</div> : <TokenStackedChart points={daily} />}
        </article>
      </section>

      <section className="billing-card">
        <div className="billing-card-head">
          <h2>Model Breakdown</h2>
          <p>Costs remain separated per provider/model even if active model changes.</p>
        </div>
        <div className="billing-table-wrap">
          <table className="billing-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Requests</th>
                <th>Input</th>
                <th>Output</th>
                <th>Total Tokens</th>
                <th>Share</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {modelRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="billing-empty-row">
                    No model usage in this range.
                  </td>
                </tr>
              ) : (
                modelRows.map((row) => (
                  <tr key={`${row.provider}:${row.model}`}>
                    <td>
                      <div className="billing-model-cell">
                        <span className="provider">{row.provider}</span>
                        <span className="model">{row.model}</span>
                      </div>
                    </td>
                    <td>{formatTokenCount(row.requests)}</td>
                    <td>{formatTokenCount(row.input_tokens)}</td>
                    <td>{formatTokenCount(row.output_tokens)}</td>
                    <td>{formatTokenCount(row.total_tokens)}</td>
                    <td>{formatPercent(row.share)}</td>
                    <td>{formatCostUsd(row.total_cost_usd)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="billing-card">
        <div className="billing-card-head">
          <h2>Recent Usage Events</h2>
          <p>Newest calls with model, token, and cost metadata.</p>
        </div>
        <div className="billing-table-wrap">
          <table className="billing-table billing-table-compact">
            <thead>
              <tr>
                <th>Time</th>
                <th>Conversation</th>
                <th>Model</th>
                <th>Input</th>
                <th>Output</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 ? (
                <tr>
                  <td colSpan={6} className="billing-empty-row">
                    No recent usage events.
                  </td>
                </tr>
              ) : (
                recent.map((row) => (
                  <tr key={`${row.id}-${row.created_at}`}>
                    <td>{formatDateLabel(row.created_at)}</td>
                    <td className="mono">{row.conversation_id}</td>
                    <td>
                      {row.provider}/{row.model}
                    </td>
                    <td>{formatTokenCount(row.input_tokens)}</td>
                    <td>{formatTokenCount(row.output_tokens)}</td>
                    <td>{formatCostUsd(row.total_cost_usd)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}


"use client";

import { useState, useEffect } from "react";
import { Building2, Users, Briefcase, MessageSquare, Lightbulb, DollarSign, RefreshCw, AlertTriangle, Clock } from "lucide-react";
import { getGoldTopCustomers, getGoldPipelineHealth, getGoldRevenueSummary, getGoldDealsClosingSoon, getGoldAtRiskAccounts, refreshGoldLayer } from "@/lib/api";

export default function OverviewPage({ stats, schema, onNavigate }) {
  const [topCustomers,    setTopCustomers]    = useState([]);
  const [pipelineHealth,  setPipelineHealth]  = useState([]);
  const [closingSoon,     setClosingSoon]      = useState([]);
  const [atRisk,          setAtRisk]           = useState([]);
  const [goldLoading,     setGoldLoading]      = useState(true);
  const [refreshing,      setRefreshing]       = useState(false);

  useEffect(() => { fetchGold(); }, []);

  async function fetchGold() {
    setGoldLoading(true);
    try {
      const [tc, ph, cs, ar] = await Promise.all([
        getGoldTopCustomers(), getGoldPipelineHealth(),
        getGoldDealsClosingSoon(), getGoldAtRiskAccounts(),
      ]);
      setTopCustomers(tc.data || []);
      setPipelineHealth(ph.data || []);
      setClosingSoon(cs.data || []);
      setAtRisk(ar.data || []);
    } catch (e) { console.warn("Gold layer:", e.message); }
    setGoldLoading(false);
  }

  async function handleRefresh() {
    setRefreshing(true);
    try { await refreshGoldLayer(); await fetchGold(); }
    catch (e) { console.warn("Refresh error:", e.message); }
    setRefreshing(false);
  }

  const totalPipeline = pipelineHealth.reduce((s, r) => s + Number(r.total_value || 0), 0);

  const RISK_COLOR = { "High Risk": "#b91c1c", "Medium Risk": "#a16207", "No Contact": "#6b7280", "Active": "#15803d" };
  const STAGE_DOT  = { "Closed Won": "#15803d", "Closed Lost": "#b91c1c" };

  return (
    <div className="flex-1 overflow-y-auto bg-background">

      {/* ── Page header ── */}
      <div style={{ background: "#fff", borderBottom: "1px solid #e2e8f0", padding: "14px 24px", boxShadow: "0 1px 3px rgba(46,78,153,0.04)" }}
        className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div style={{ width: 4, height: 22, borderRadius: 2, background: "#2E4E99" }} />
          <div>
            <h1 style={{ fontSize: 17, fontWeight: 800, color: "#1C3268", letterSpacing: "-0.02em" }}>Overview</h1>
            <p style={{ fontSize: 12, color: "#64748b" }}>Gold layer · pre-computed business KPIs</p>
          </div>
        </div>
        <button onClick={handleRefresh} disabled={refreshing}
          style={{ fontSize: 12, borderRadius: 8, padding: "8px 18px", background: refreshing ? "#1C3268" : "#2E4E99", color: "#fff", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontWeight: 600, transition: "all 0.15s" }}
          className="hover:shadow-[0_4px_12px_rgba(46,78,153,0.3)]">
          <RefreshCw style={{ width: 13, height: 13, ...(refreshing ? { animation: "spin 1s linear infinite" } : {}) }} />
          {refreshing ? "Refreshing…" : "Refresh Gold"}
        </button>
      </div>

      <div style={{ padding: "20px 24px" }} className="space-y-6">

        {/* ── ROW 1: Silver stat pills ── */}
        <div className="grid grid-cols-6 gap-3">
          {[
            { label: "Accounts",     val: stats?.accounts || 0,               icon: Building2,   page: "accounts" },
            { label: "Contacts",     val: stats?.contacts || 0,               icon: Users,       page: "accounts" },
            { label: "Deals",        val: stats?.deals || 0,                   icon: Briefcase,   page: "pipeline" },
            { label: "Pipeline",     val: formatCurrency(stats?.total_deal_value || 0), icon: DollarSign, page: "pipeline" },
            { label: "Interactions", val: stats?.interactions || 0,            icon: MessageSquare, page: "chat" },
            { label: "Insights",     val: stats?.insights || 0,               icon: Lightbulb,   page: "insights" },
          ].map((c) => {
            const Icon = c.icon;
            return (
              <button key={c.label} onClick={() => onNavigate(c.page)}
                style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "14px 16px", textAlign: "left", cursor: "pointer", position: "relative", overflow: "hidden", boxShadow: "0 1px 3px rgba(46,78,153,0.06)", transition: "all 0.2s" }}
                className="hover:shadow-[0_4px_12px_rgba(46,78,153,0.1)] hover:border-[#2E4E99]"
                >
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: "#2E4E99" }} />
                <Icon style={{ width: 15, height: 15, color: "#2E4E99", marginBottom: 8 }} />
                <p style={{ fontSize: 22, fontWeight: 700, color: "#2E4E99" }}>{c.val}</p>
                <p style={{ fontSize: 11, color: "#64748b", fontWeight: 500 }}>{c.label}</p>
              </button>
            );
          })}
        </div>

        {/* ── ROW 2: Pipeline by stage (full-width) ── */}
        <GoldSection title="Pipeline by Stage" badge={formatCurrency(totalPipeline)}>
          {goldLoading ? <Skeleton h={56} /> : pipelineHealth.length === 0 ? <Empty /> : (
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(pipelineHealth.length, 6)}, 1fr)` }}>
              {pipelineHealth.map((row) => {
                const pct = totalPipeline > 0 ? (Number(row.total_value || 0) / totalPipeline) * 100 : 0;
                const dot = STAGE_DOT[row.stage] || "#2E4E99";
                return (
                  <div key={row.stage} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", transition: "box-shadow 0.2s" }} className="hover:shadow-[0_2px_8px_rgba(46,78,153,0.08)]">
                    <div className="flex items-center gap-1.5 mb-2">
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: dot, display: "inline-block", boxShadow: `0 0 6px ${dot}40` }} />
                      <span style={{ fontSize: 11, color: "#2E4E99", fontWeight: 600 }}>{row.stage || "Unknown"}</span>
                    </div>
                    <p style={{ fontSize: 17, fontWeight: 700, color: "#2E4E99" }}>{formatCurrency(Number(row.total_value || 0))}</p>
                    <p style={{ fontSize: 11, color: "#64748b" }}>{row.deal_count} deal{row.deal_count !== 1 ? "s" : ""}</p>
                    <div style={{ marginTop: 8, height: 4, background: "#e2e8f0", borderRadius: 3 }}>
                      <div style={{ height: "100%", width: `${Math.min(pct, 100)}%`, background: `linear-gradient(90deg, ${dot}, ${dot}cc)`, borderRadius: 3, transition: "width 0.5s" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </GoldSection>

        {/* ── ROW 3: Two columns — Top Customers | Deals Closing Soon ── */}
        <div className="grid grid-cols-2 gap-4">

          {/* Top Customers */}
          <GoldSection title="Top Customers">
            {goldLoading ? <Skeleton h={140} /> : topCustomers.length === 0 ? <Empty /> : (
              <table className="w-full" style={{ fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #e5e7eb" }}>
                    {["#", "Account", "Industry", "Value", "Won"].map((h) => (
                      <th key={h} style={{ fontSize: 11, color: "#6b7280", fontWeight: 500, textAlign: h === "#" || h === "Account" ? "left" : "right", paddingBottom: 6, paddingRight: 8 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {topCustomers.slice(0, 8).map((row, i) => (
                    <tr key={row.account_name} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "6px 8px 6px 0", color: "#9ca3af", width: 20 }}>{row.rank || i + 1}</td>
                      <td style={{ padding: "6px 8px 6px 0", fontWeight: 500, color: "#111827" }}>{row.account_name}</td>
                      <td style={{ padding: "6px 8px 6px 0", color: "#6b7280" }}>{row.industry || "—"}</td>
                      <td style={{ padding: "6px 0", textAlign: "right", fontWeight: 600 }}>{formatCurrency(Number(row.total_deal_value || 0))}</td>
                      <td style={{ padding: "6px 0 6px 8px", textAlign: "right", color: "#15803d" }}>{formatCurrency(Number(row.won_value || 0))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </GoldSection>

          {/* Deals Closing Soon */}
          <GoldSection title="Deals Closing Soon" icon={<Clock style={{ width: 13, height: 13, color: "#a16207" }} />}>
            {goldLoading ? <Skeleton h={140} /> : closingSoon.length === 0
              ? <p style={{ fontSize: 12, color: "#9ca3af", padding: "16px 0" }}>No upcoming close dates found.</p>
              : (
              <table className="w-full" style={{ fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #e5e7eb" }}>
                    {["Deal", "Account", "Value", "Days Left"].map((h) => (
                      <th key={h} style={{ fontSize: 11, color: "#6b7280", fontWeight: 500, textAlign: "left", paddingBottom: 6, paddingRight: 8 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {closingSoon.slice(0, 8).map((row, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "6px 8px 6px 0", fontWeight: 500 }}>{row.deal_name || "Untitled"}</td>
                      <td style={{ padding: "6px 8px 6px 0", color: "#6b7280" }}>{row.account_name}</td>
                      <td style={{ padding: "6px 8px 6px 0" }}>{row.deal_value ? `$${Number(row.deal_value).toLocaleString()}` : "—"}</td>
                      <td style={{ padding: "6px 0" }}>
                        <span style={{
                          fontSize: 11, padding: "2px 7px", borderRadius: 3,
                          background: row.days_until_close <= 7 ? "#fee2e2" : row.days_until_close <= 30 ? "#fef9c3" : "#dcfce7",
                          color: row.days_until_close <= 7 ? "#b91c1c" : row.days_until_close <= 30 ? "#a16207" : "#15803d",
                        }}>
                          {row.days_until_close != null ? `${row.days_until_close}d` : "—"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </GoldSection>
        </div>

        {/* ── ROW 4: At-Risk Accounts (full-width) ── */}
        <GoldSection title="At-Risk Accounts" icon={<AlertTriangle style={{ width: 13, height: 13, color: "#b91c1c" }} />}>
          {goldLoading ? <Skeleton h={80} /> : atRisk.length === 0
            ? <p style={{ fontSize: 12, color: "#9ca3af", padding: "16px 0" }}>No at-risk accounts. All accounts are active.</p>
            : (
            <table className="w-full" style={{ fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #e5e7eb" }}>
                  {["Account", "Industry", "Open Deals", "Open Value", "Last Contact", "Days Silent", "Risk"].map((h) => (
                    <th key={h} style={{ fontSize: 11, color: "#6b7280", fontWeight: 500, textAlign: "left", paddingBottom: 6, paddingRight: 10 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {atRisk.slice(0, 10).map((row, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                    <td style={{ padding: "6px 10px 6px 0", fontWeight: 500 }}>{row.account_name}</td>
                    <td style={{ padding: "6px 10px 6px 0", color: "#6b7280" }}>{row.industry || "—"}</td>
                    <td style={{ padding: "6px 10px 6px 0", color: "#6b7280" }}>{row.open_deal_count}</td>
                    <td style={{ padding: "6px 10px 6px 0" }}>{formatCurrency(Number(row.open_deal_value || 0))}</td>
                    <td style={{ padding: "6px 10px 6px 0", color: "#6b7280" }}>{row.last_interaction_date || "Never"}</td>
                    <td style={{ padding: "6px 10px 6px 0", color: "#6b7280" }}>{row.days_since_last_contact != null ? `${row.days_since_last_contact}d` : "—"}</td>
                    <td style={{ padding: "6px 0" }}>
                      <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 3, background: "#f3f4f6", color: RISK_COLOR[row.risk_level] || "#374151", fontWeight: 500 }}>
                        {row.risk_level || "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </GoldSection>

      </div>
    </div>
  );
}

function GoldSection({ title, badge, icon, children }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "16px 18px", boxShadow: "0 1px 3px rgba(46,78,153,0.06)" }}>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h2 style={{ fontSize: 12, fontWeight: 700, color: "#2E4E99", textTransform: "uppercase", letterSpacing: "0.04em" }}>{title}</h2>
        {badge && <span style={{ marginLeft: "auto", fontSize: 13, fontWeight: 700, color: "#2E4E99" }}>{badge}</span>}
      </div>
      {children}
    </div>
  );
}

function Skeleton({ h }) {
  return <div style={{ height: h, background: "#f1f5f9", borderRadius: 8 }} />;
}

function Empty() {
  return <p style={{ fontSize: 12, color: "#9ca3af", padding: "16px 0" }}>No data yet — ingest files to populate.</p>;
}

function formatCurrency(val) {
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000)     return `$${(val / 1_000).toFixed(0)}K`;
  if (val > 0)          return `$${val.toLocaleString()}`;
  return "$0";
}

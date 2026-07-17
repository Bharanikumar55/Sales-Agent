"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp,
  DollarSign,
  Calendar,
  Building2,
  Users,
  Loader2,
} from "lucide-react";
import { getPipeline } from "@/lib/api";

const STAGE_COLORS = {
  Proposal: { bg: "#6366f1", text: "#818cf8", border: "#6366f1" },
  Negotiation: { bg: "#fbbf24", text: "#fbbf24", border: "#fbbf24" },
  "Closed Won": { bg: "#34d399", text: "#34d399", border: "#34d399" },
  "Closed Lost": { bg: "#f87171", text: "#f87171", border: "#f87171" },
  Qualification: { bg: "#22d3ee", text: "#22d3ee", border: "#22d3ee" },
  Discovery: { bg: "#f472b6", text: "#f472b6", border: "#f472b6" },
  Unknown: { bg: "#71717a", text: "#71717a", border: "#71717a" },
};

function getStageColor(stage) {
  return STAGE_COLORS[stage] || STAGE_COLORS.Unknown;
}

export default function PipelinePage() {
  const [pipeline, setPipeline] = useState({});
  const [totalDeals, setTotalDeals] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPipeline();
  }, []);

  async function loadPipeline() {
    setLoading(true);
    try {
      const data = await getPipeline();
      setPipeline(data.stages || {});
      setTotalDeals(data.total_deals || 0);
    } catch {
      setPipeline({});
    }
    setLoading(false);
  }

  const stages = Object.entries(pipeline);
  const totalValue = stages.reduce((sum, [, deals]) => {
    return (
      sum +
      deals.reduce((s, d) => {
        const v = parseFloat(d.deal_value) || 0;
        return s + v;
      }, 0)
    );
  }, 0);

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-background">
      {/* Header */}
      <div style={{ borderBottom: "1px solid #e2e8f0", background: "#fff", padding: "14px 24px", boxShadow: "0 1px 3px rgba(46,78,153,0.04)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div style={{ width: 4, height: 22, borderRadius: 2, background: "#2E4E99" }} />
            <div>
              <h1 style={{ fontSize: 17, fontWeight: 800, color: "#1C3268", letterSpacing: "-0.02em" }}>
                Sales Pipeline
              </h1>
              <p style={{ fontSize: 12, color: "#64748b" }}>
                {totalDeals} deal{totalDeals !== 1 ? "s" : ""} across{" "}
                {stages.length} stage{stages.length !== 1 ? "s" : ""}
              </p>
            </div>
          </div>
          <div style={{ background: "#2E4E99", borderRadius: 8, padding: "8px 16px", display: "flex", alignItems: "center", gap: 8, boxShadow: "0 2px 8px rgba(46,78,153,0.2)" }}>
            <DollarSign style={{ width: 16, height: 16, color: "#a8c0e8" }} />
            <span style={{ fontSize: 13, fontWeight: 500, color: "#e2e8f0" }}>
              Total Pipeline:{" "}
              <span style={{ color: "#ffffff", fontWeight: 700 }}>
                ${totalValue.toLocaleString()}
              </span>
            </span>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center flex-1">
          <Loader2 className="w-5 h-5 text-primary animate-spin" />
        </div>
      ) : stages.length === 0 ? (
        <div className="flex flex-col items-center justify-center flex-1 text-muted-light">
          <TrendingUp className="w-10 h-10 mb-2 opacity-30" />
          <p className="text-sm">No deals in the pipeline</p>
          <p className="text-xs mt-1">Ingest CRM data to see deals here</p>
        </div>
      ) : (
        <div className="flex-1 overflow-x-auto p-6">
          <div className="flex gap-4 min-w-max h-full">
            {stages.map(([stage, deals]) => {
              const color = getStageColor(stage);
              const stageValue = deals.reduce(
                (s, d) => s + (parseFloat(d.deal_value) || 0),
                0
              );

              return (
                <div
                  key={stage}
                  style={{ width: 288, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, display: "flex", flexDirection: "column", boxShadow: "0 1px 3px rgba(46,78,153,0.06)", overflow: "hidden" }}
                >
                  {/* Stage Header */}
                  <div style={{ padding: "12px 14px", background: "#2E4E99", borderBottom: "none" }}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <div
                          style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: color.bg, boxShadow: `0 0 6px ${color.bg}60` }}
                        />
                        <h3 style={{ fontSize: 11, fontWeight: 700, color: "#e2e8f0", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                          {stage}
                        </h3>
                      </div>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "#a8c0e8", background: "rgba(168,192,232,0.15)", padding: "2px 8px", borderRadius: 10 }}>
                        {deals.length}
                      </span>
                    </div>
                    <p style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>
                      ${stageValue.toLocaleString()}
                    </p>
                  </div>

                  {/* Deal Cards */}
                  <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8, background: "#f8fafc" }}>
                    {deals.map((deal) => (
                      <DealCard
                        key={deal.id}
                        deal={deal}
                        color={color}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function DealCard({ deal, color }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 12, cursor: "default", transition: "all 0.15s", borderLeft: "3px solid transparent" }}
      className="hover:border-l-[#2E4E99] hover:shadow-[0_2px_8px_rgba(46,78,153,0.08)]"
      onMouseEnter={(e) => { e.currentTarget.style.borderLeftColor = "#2E4E99"; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderLeftColor = "transparent"; }}>
      <h4 style={{ fontSize: 13, fontWeight: 600, color: "#2E4E99", marginBottom: 6, lineHeight: 1.3 }}>
        {deal.deal_name || "Untitled Deal"}
      </h4>

      {deal.account_name && (
        <div className="flex items-center gap-1.5 mb-1">
          <Building2 style={{ width: 12, height: 12, color: "#94a3b8" }} />
          <span style={{ fontSize: 11, color: "#64748b" }} className="truncate">
            {deal.account_name}
          </span>
        </div>
      )}

      {deal.contact_name && (
        <div className="flex items-center gap-1.5 mb-2">
          <Users style={{ width: 12, height: 12, color: "#94a3b8" }} />
          <span style={{ fontSize: 11, color: "#64748b" }} className="truncate">
            {deal.contact_name}
          </span>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8, paddingTop: 8, borderTop: "1px solid #f1f5f9" }}>
        {deal.deal_value && (
          <span style={{ fontSize: 14, fontWeight: 700, color: "#2E4E99" }}>
            ${Number(deal.deal_value).toLocaleString()}
          </span>
        )}
        {deal.close_date && (
          <div className="flex items-center gap-1">
            <Calendar style={{ width: 12, height: 12, color: "#94a3b8" }} />
            <span style={{ fontSize: 10, color: "#94a3b8" }}>
              {deal.close_date}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

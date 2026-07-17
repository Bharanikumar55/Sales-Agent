"use client";

import { useState, useEffect } from "react";
import {
  Lightbulb,
  Loader2,
  TrendingUp,
  Shield,
  AlertTriangle,
  Target,
  Building2,
  Users,
} from "lucide-react";
import { getInsights } from "@/lib/api";

const TYPE_CONFIG = {
  deal_signal: {
    icon: TrendingUp,
    color: "#059669",
    label: "Deal Signal",
  },
  competitive: {
    icon: Shield,
    color: "#4f46e5",
    label: "Competitive Intel",
  },
  risk: {
    icon: AlertTriangle,
    color: "#dc2626",
    label: "Risk",
  },
  action_item: {
    icon: Target,
    color: "#d97706",
    label: "Action Item",
  },
  key_point: {
    icon: Lightbulb,
    color: "#2563eb",
    label: "Key Point",
  },
};

function getTypeConfig(type) {
  return TYPE_CONFIG[type] || { icon: Lightbulb, color: "#fb923c", label: type || "Insight" };
}

export default function InsightsPage() {
  const [insights, setInsights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    loadInsights();
  }, []);

  async function loadInsights() {
    setLoading(true);
    try {
      const data = await getInsights();
      setInsights(data.insights || []);
    } catch {
      setInsights([]);
    }
    setLoading(false);
  }

  const types = ["all", ...new Set(insights.map((i) => i.insight_type).filter(Boolean))];
  const filtered = filter === "all" ? insights : insights.filter((i) => i.insight_type === filter);

  return (
    <div className="flex-1 overflow-y-auto bg-background">
      {/* Header */}
      <div className="border-b border-border bg-surface px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-foreground">AI Insights</h1>
            <p className="text-sm text-muted">
              {insights.length} insight{insights.length !== 1 ? "s" : ""}{" "}
              extracted from your data
            </p>
          </div>
        </div>

        {/* Filter Pills */}
        {types.length > 1 && (
          <div className="flex items-center gap-2 mt-4">
            {types.map((t) => (
              <button
                key={t}
                onClick={() => setFilter(t)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-all ${
                  filter === t
                    ? "bg-primary/10 border-primary/30 text-primary font-medium shadow-sm"
                    : "bg-surface border-border text-muted hover:border-primary hover:text-foreground"
                }`}
              >
                {t === "all" ? "All" : getTypeConfig(t).label}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 text-primary animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-light">
          <Lightbulb className="w-10 h-10 mb-2 opacity-30" />
          <p className="text-sm">No insights yet</p>
          <p className="text-xs mt-1">
            Upload transcripts or ingest data to generate AI insights
          </p>
        </div>
      ) : (
        <div className="p-6">
          <div className="max-w-[1600px] w-full mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map((ins) => {
              const config = getTypeConfig(ins.insight_type);
              const Icon = config.icon;
              return (
                <div
                  key={ins.id}
                  className="bg-surface border border-border rounded p-5 hover:border-primary transition-all shadow-sm flex flex-col h-full"
                >
                  <div className="flex items-center gap-3 mb-4">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ backgroundColor: `${config.color}15` }}
                    >
                      <Icon
                        className="w-4.5 h-4.5"
                        style={{ color: config.color }}
                      />
                    </div>
                    <div className="flex-1 min-w-0 flex flex-col items-start gap-1">
                      <span
                        className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border"
                        style={{
                          backgroundColor: `${config.color}10`,
                          borderColor: `${config.color}30`,
                          color: config.color,
                        }}
                      >
                        {config.label}
                      </span>
                      {ins.confidence && (
                        <span className="text-[10px] text-muted-light font-medium tracking-wide">
                          Confidence: {ins.confidence}
                        </span>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex-1 min-w-0 mb-4">
                    <p className="text-[13px] text-foreground leading-relaxed font-medium">
                      {ins.content || "No content"}
                    </p>
                  </div>
                  
                  <div className="flex items-center gap-x-4 gap-y-2 flex-wrap mt-auto pt-4 border-t border-border">
                        {ins.account_name && (
                          <div className="flex items-center gap-1.5">
                            <Building2 className="w-3 h-3 text-muted-light" />
                            <span className="text-[11px] text-muted font-medium">
                              {ins.account_name}
                            </span>
                          </div>
                        )}
                        {ins.contact_name && (
                          <div className="flex items-center gap-1.5">
                            <Users className="w-3 h-3 text-muted-light" />
                            <span className="text-[11px] text-muted font-medium">
                              {ins.contact_name}
                            </span>
                          </div>
                        )}
                        {ins.insight_date && (
                          <span className="text-[10px] text-muted-light ml-auto">
                            {ins.insight_date}
                          </span>
                        )}
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

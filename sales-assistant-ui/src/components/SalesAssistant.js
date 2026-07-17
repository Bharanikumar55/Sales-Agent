"use client";

import { useState, useEffect } from "react";
import {
  MessageSquare, Building2, TrendingUp,
  LayoutDashboard, Database, Plus, Trash2, X,
  History, PanelRightClose, Clock
} from "lucide-react";
import { getSchemaInfo, getDashboardStats } from "@/lib/api";
import ChatPage from "./ChatPage";
import AccountsPage from "./AccountsPage";
import PipelinePage from "./PipelinePage";
import OverviewPage from "./OverviewPage";

const NAV_ITEMS = [
  { id: "overview",  label: "Overview",  icon: LayoutDashboard },
  { id: "accounts",  label: "Accounts",  icon: Building2 },
  { id: "pipeline",  label: "Pipeline",  icon: TrendingUp },
  { id: "chat",      label: "Assistant", icon: MessageSquare },
];

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}
function loadConversations() {
  try { return JSON.parse(localStorage.getItem("sa_conversations") || "[]"); }
  catch { return []; }
}
function saveConversations(convs) {
  localStorage.setItem("sa_conversations", JSON.stringify(convs));
}

export default function SalesAssistant() {
  const [activePage, setActivePage]       = useState("overview");
  const [schema, setSchema]               = useState(null);
  const [stats, setStats]                 = useState(null);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId]   = useState(null);
  const [convOpen, setConvOpen]           = useState(false);
  const [historyOpen, setHistoryOpen]     = useState(false);

  useEffect(() => {
    loadData();
    const convs = loadConversations();
    setConversations(convs);
    if (convs.length > 0) setActiveConvId(convs[0].id);
  }, []);

  async function loadData() {
    try {
      const res = await fetch("http://127.0.0.1:9000/health");
      setBackendStatus(res.ok ? "connected" : "error");
    } catch { setBackendStatus("error"); }
    try { const s = await getSchemaInfo();      setSchema(s); }       catch {}
    try { const st = await getDashboardStats(); setStats(st.stats); } catch {}
  }

  function createConversation() {
    const conv = { id: generateId(), title: "New conversation", messages: [], createdAt: new Date().toISOString() };
    const updated = [conv, ...conversations];
    setConversations(updated);
    setActiveConvId(conv.id);
    saveConversations(updated);
    setActivePage("chat");
    setConvOpen(false);
    return conv.id;
  }

  function deleteConversation(id) {
    const updated = conversations.filter((c) => c.id !== id);
    setConversations(updated);
    saveConversations(updated);
    if (activeConvId === id) setActiveConvId(updated[0]?.id ?? null);
  }

  function updateConversation(id, messages) {
    setConversations((prev) => {
      const title = messages.find((m) => m.role === "user")?.content?.slice(0, 45) || "New conversation";
      const exists = prev.some((c) => c.id === id);
      const updated = exists
        ? prev.map((c) => c.id !== id ? c : { ...c, messages, title })
        : [{ id, title, messages, createdAt: new Date().toISOString() }, ...prev];
      saveConversations(updated);
      return updated;
    });
  }

  const activeConv = conversations.find((c) => c.id === activeConvId);
  const totalRows  = schema
    ? [...(schema.dimensions || []), ...(schema.fact_tables || [])].reduce((s, t) => s + (t.row_count || 0), 0)
    : 0;

  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">

      {/* ── HEADER ── */}
      <header style={{ background: "#ffffff", borderBottom: "1px solid #e2e8f0", boxShadow: "0 1px 4px rgba(0,0,0,0.05)" }}
        className="flex-shrink-0 flex items-center px-8 h-[72px]">

        {/* Left: Brand + Nav (together) */}
        <div className="flex items-center gap-8 h-full">
          {/* Brand */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <div style={{ width: 38, height: 38, borderRadius: 10, background: "#2E4E99", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <TrendingUp style={{ width: 20, height: 20, color: "#fff" }} />
            </div>
            <span style={{ fontSize: 22, fontWeight: 800, color: "#1C3268", letterSpacing: "-0.03em" }}>
              Sales Assistant
            </span>
          </div>

          {/* Divider */}
          <div style={{ width: 1, height: 32, background: "#e2e8f0" }} />

          {/* Nav items */}
          <nav className="flex items-center gap-1 h-full">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = activePage === item.id;
              return (
                <button key={item.id} onClick={() => setActivePage(item.id)}
                  style={{
                    fontSize: 15, fontWeight: active ? 600 : 450,
                    color: active ? "#2E4E99" : "#64748b",
                    borderBottom: active ? "3px solid #2E4E99" : "3px solid transparent",
                    padding: "0 20px", height: "100%", background: "none", cursor: "pointer",
                    display: "flex", alignItems: "center", gap: 8,
                    transition: "color 0.15s",
                  }}
                  onMouseEnter={(e) => { if (!active) e.currentTarget.style.color = "#2E4E99"; }}
                  onMouseLeave={(e) => { if (!active) e.currentTarget.style.color = "#64748b"; }}>
                  <Icon style={{ width: 17, height: 17 }} />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right: Status + Actions (pushed to far right) */}
        <div className="flex items-center gap-4 ml-auto">
          <div className="flex items-center gap-1.5">
            <span style={{
              width: 7, height: 7, borderRadius: "50%", display: "inline-block",
              background: backendStatus === "connected" ? "#2E4E99" : backendStatus === "error" ? "#ef4444" : "#f59e0b",
              boxShadow: backendStatus === "connected" ? "0 0 6px rgba(46,78,153,0.35)" : "none"
            }} />
            <span style={{ color: "#94a3b8", fontSize: 11 }}>
              {backendStatus === "connected" ? "Connected" : backendStatus === "error" ? "Offline" : "Connecting"}
            </span>
          </div>

          {schema && (
            <div className="flex items-center gap-1" style={{ color: "#94a3b8", fontSize: 11 }}>
              <Database className="w-3 h-3" />
              <span>{schema.total_tables}t · {totalRows.toLocaleString()}r</span>
            </div>
          )}

          {activePage === "chat" && (
            <button
              onClick={() => setHistoryOpen(!historyOpen)}
              style={{ background: historyOpen ? "#eef2f9" : "transparent", border: "1px solid #e2e8f0", borderRadius: 8, padding: "6px 12px", color: historyOpen ? "#2E4E99" : "#64748b", fontSize: 12, transition: "all 0.15s", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
              className="hover:bg-[#eef2f9]"
            >
              {historyOpen ? <PanelRightClose style={{ width: 14, height: 14 }} /> : <History style={{ width: 14, height: 14 }} />}
              <span className="hidden sm:inline">History</span>
            </button>
          )}

          {activePage === "chat" && (
            <button onClick={createConversation}
              style={{ background: "#2E4E99", borderRadius: 8, color: "#fff", fontSize: 13, fontWeight: 600, padding: "7px 18px", cursor: "pointer", transition: "all 0.15s", display: "flex", alignItems: "center", gap: 6 }}
              className="hover:shadow-[0_4px_12px_rgba(46,78,153,0.3)] hover:scale-[1.02] active:scale-[0.98]">
              <Plus className="w-4 h-4" /> New Chat
            </button>
          )}
        </div>
      </header>

      {/* ── MAIN CONTENT + OPTIONAL HISTORY DRAWER ── */}
      <div className="flex-1 overflow-hidden flex">
        <main className="flex-1 overflow-hidden flex flex-col">
          {activePage === "overview"  && <OverviewPage stats={stats} schema={schema} onNavigate={setActivePage} />}
          {activePage === "chat"      && (
            <ChatPage
              onDataChange={loadData}
              conversation={activeConv}
              activeConvId={activeConvId}
              onUpdateMessages={updateConversation}
              onNewConversation={createConversation}
              hasConversation={!!activeConv}
            />
          )}
          {activePage === "accounts"  && <AccountsPage onOpenChat={(accName) => { createConversation(); setActivePage("chat"); }} />}
          {activePage === "pipeline"  && <PipelinePage />}
        </main>

        {/* ── RIGHT-SIDE CONVERSATION HISTORY DRAWER ── */}
        {activePage === "chat" && historyOpen && (
          <div style={{
            width: 300, background: "#ffffff", borderLeft: "1px solid #e2e8f0",
            display: "flex", flexDirection: "column", flexShrink: 0,
            boxShadow: "-4px 0 16px rgba(46,78,153,0.06)",
            animation: "slideInRight 0.2s ease-out",
          }}>
            {/* Drawer header */}
            <div style={{ padding: "16px 18px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div className="flex items-center gap-2">
                <History style={{ width: 14, height: 14, color: "#2E4E99" }} />
                <span style={{ fontSize: 13, fontWeight: 700, color: "#1C3268" }}>Chat History</span>
              </div>
              <button onClick={() => setHistoryOpen(false)} style={{ color: "#94a3b8", cursor: "pointer", padding: 4, borderRadius: 6 }} className="hover:bg-[#f1f5f9]">
                <X style={{ width: 14, height: 14 }} />
              </button>
            </div>

            {/* New chat button */}
            <div style={{ padding: "12px 14px", borderBottom: "1px solid #f1f5f9" }}>
              <button onClick={createConversation}
                style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "9px 12px", borderRadius: 8, background: "#2E4E99", color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", transition: "all 0.15s" }}
                className="hover:shadow-[0_4px_12px_rgba(46,78,153,0.25)]"
              >
                <Plus style={{ width: 14, height: 14 }} />
                New Conversation
              </button>
            </div>

            {/* Conversation list */}
            <div style={{ flex: 1, overflowY: "auto" }}>
              {conversations.length === 0
                ? (
                  <div style={{ padding: "40px 16px", textAlign: "center" }}>
                    <MessageSquare style={{ width: 28, height: 28, color: "#e2e8f0", margin: "0 auto 10px" }} />
                    <p style={{ fontSize: 13, color: "#94a3b8", fontWeight: 500 }}>No conversations yet</p>
                    <p style={{ fontSize: 11, color: "#cbd5e1", marginTop: 4 }}>Start a new chat to begin</p>
                  </div>
                )
                : conversations.map((conv) => {
                    const isActive = activeConvId === conv.id;
                    const dateStr = conv.createdAt ? new Date(conv.createdAt).toLocaleDateString([], { month: "short", day: "numeric" }) : "";
                    return (
                      <div key={conv.id}
                        onClick={() => { setActiveConvId(conv.id); }}
                        style={{
                          padding: "12px 16px", cursor: "pointer", transition: "all 0.15s",
                          borderLeft: isActive ? "3px solid #2E4E99" : "3px solid transparent",
                          background: isActive ? "#eef2f9" : "transparent",
                        }}
                        className="group hover:bg-[#f8fafc]"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <p style={{ fontSize: 12, fontWeight: isActive ? 600 : 450, color: isActive ? "#2E4E99" : "#374151", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {conv.title}
                            </p>
                            <div className="flex items-center gap-2" style={{ marginTop: 4 }}>
                              <Clock style={{ width: 10, height: 10, color: "#cbd5e1" }} />
                              <span style={{ fontSize: 10, color: "#94a3b8" }}>{dateStr}</span>
                              <span style={{ fontSize: 10, color: "#cbd5e1" }}>·</span>
                              <span style={{ fontSize: 10, color: "#cbd5e1" }}>{conv.messages?.length || 0} msgs</span>
                            </div>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); }}
                            style={{ color: "#ef4444", padding: 2, borderRadius: 4, flexShrink: 0, marginTop: 2 }}
                            className="opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[#fee2e2]"
                          >
                            <Trash2 style={{ width: 12, height: 12 }} />
                          </button>
                        </div>
                      </div>
                    );
                  })
              }
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

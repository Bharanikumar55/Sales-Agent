"use client";

import { useState, useEffect, useRef } from "react";
import { Building2, Users, Briefcase, MessageSquare, Lightbulb, ArrowLeft, Mail, Phone, Calendar, Loader2, Search, Send, Paperclip, X, FileText, FileSpreadsheet, TrendingUp, Shield, AlertTriangle, Target } from "lucide-react";
import { getAccounts, getAccountDetail, askQuestion, uploadFileForAccount } from "@/lib/api";

export default function AccountsPage() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => { loadAccounts(); }, []);

  async function loadAccounts() {
    setLoading(true);
    try { const data = await getAccounts(); setAccounts(data.accounts || []); }
    catch { setAccounts([]); }
    setLoading(false);
  }

  async function selectAccount(acc) {
    setSelectedAccount(acc);
    setDetailLoading(true);
    try { const data = await getAccountDetail(acc.id); setDetail(data); }
    catch { setDetail(null); }
    setDetailLoading(false);
  }

  const filtered = accounts.filter(
    (a) => (a.account_name || "").toLowerCase().includes(search.toLowerCase()) ||
      (a.industry || "").toLowerCase().includes(search.toLowerCase())
  );

  if (selectedAccount && detail) {
    return <AccountDetailView detail={detail} onBack={() => { setSelectedAccount(null); setDetail(null); }} loading={detailLoading} />;
  }

  return (
    <div className="flex-1 overflow-y-auto bg-background">
      <div style={{ borderBottom: "1px solid #e2e8f0", background: "#fff", padding: "14px 24px", boxShadow: "0 1px 3px rgba(46,78,153,0.04)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div style={{ width: 4, height: 22, borderRadius: 2, background: "#2E4E99" }} />
            <div>
              <h1 style={{ fontSize: 17, fontWeight: 800, color: "#1C3268", letterSpacing: "-0.02em" }}>Accounts</h1>
              <p style={{ fontSize: 12, color: "#64748b" }}>{accounts.length} account{accounts.length !== 1 ? "s" : ""}</p>
            </div>
          </div>
          <div className="relative">
            <Search style={{ width: 16, height: 16, color: "#94a3b8", position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)" }} />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search accounts..."
              style={{ paddingLeft: 36, paddingRight: 16, paddingTop: 7, paddingBottom: 7, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 13, color: "#111827", outline: "none", width: 260, transition: "border-color 0.2s, box-shadow 0.2s" }}
              className="placeholder-[#94a3b8] focus:border-[#2E4E99] focus:shadow-[0_0_0_3px_rgba(46,78,153,0.1)]" />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-5 h-5 text-primary animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-light">
          <Building2 className="w-10 h-10 mb-2 opacity-30" />
          <p className="text-sm">No accounts found</p>
          <p className="text-xs mt-1">Ingest data to see accounts here</p>
        </div>
      ) : (
        <div style={{ padding: "16px 24px", maxWidth: 880, margin: "0 auto" }}>
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, overflow: "hidden", boxShadow: "0 1px 3px rgba(46,78,153,0.06)" }}>
            {filtered.map((acc, idx) => (
              <div key={acc.id} onClick={() => selectAccount(acc)}
                style={{
                  display: "flex", alignItems: "center", gap: 14, padding: "14px 20px",
                  cursor: "pointer", transition: "background 0.15s",
                  borderBottom: idx < filtered.length - 1 ? "1px solid #f1f5f9" : "none",
                }}
                className="hover:bg-[#f8fafc]"
              >
                {/* Avatar initial */}
                <div style={{
                  width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                  background: `hsl(${(acc.account_name || "").charCodeAt(0) * 7 % 360}, 45%, 92%)`,
                  color: `hsl(${(acc.account_name || "").charCodeAt(0) * 7 % 360}, 55%, 40%)`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 16, fontWeight: 700,
                }}>
                  {(acc.account_name || "U").charAt(0).toUpperCase()}
                </div>

                {/* Name + industry */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: 14, fontWeight: 600, color: "#1C3268", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {acc.account_name || "Unnamed"}
                  </p>
                  <div className="flex items-center gap-2" style={{ marginTop: 2 }}>
                    {acc.industry && (
                      <span style={{ fontSize: 11, color: "#2E4E99", background: "#eef2f9", padding: "1px 7px", borderRadius: 4, fontWeight: 500 }}>
                        {acc.industry}
                      </span>
                    )}
                    {acc.geography && <span style={{ fontSize: 11, color: "#94a3b8" }}>{acc.geography}</span>}
                  </div>
                </div>

                {/* Inline stats */}
                <div className="flex items-center gap-5" style={{ flexShrink: 0 }}>
                  {[
                    { icon: Users, val: acc.contact_count, tip: "Contacts" },
                    { icon: Briefcase, val: acc.deal_count, tip: "Deals" },
                    { icon: MessageSquare, val: acc.interaction_count, tip: "Meetings" },
                  ].map((s) => {
                    const SIcon = s.icon;
                    return (
                      <div key={s.tip} title={s.tip} className="flex items-center gap-1.5" style={{ minWidth: 36 }}>
                        <SIcon style={{ width: 13, height: 13, color: "#94a3b8" }} />
                        <span style={{ fontSize: 13, color: "#64748b", fontWeight: 500 }}>{s.val}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Pipeline */}
                <div style={{ flexShrink: 0, textAlign: "right", minWidth: 90 }}>
                  <p style={{ fontSize: 14, fontWeight: 700, color: "#2E4E99" }}>
                    {acc.deal_total_value > 0 ? `$${Number(acc.deal_total_value).toLocaleString()}` : "—"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AccountDetailView({ detail, onBack, loading }) {
  const { account, contacts, deals, interactions, insights } = detail;
  const [chatMessages, setChatMessages] = useState([
    { role: "assistant", text: `I'm scoped to **${account?.account_name || "this account"}**. Ask me anything about their deals, contacts, or activity. You can also upload files (PDF, CSV, XLSX, DOCX) about this account.` }
  ]);
  const [chatInput, setChatInput]   = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  const chatEndRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages]);

  function stageFile(file) {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    const supported = ["pdf", "csv", "xlsx", "xls", "txt", "docx"];
    if (!supported.includes(ext)) {
      setChatMessages((prev) => [...prev, { role: "assistant", text: `Unsupported file type: .${ext}. Supported: PDF, CSV, XLSX, TXT, DOCX`, error: true }]);
      return;
    }
    setPendingFile(file);
  }

  function buildChatHistory() {
    return chatMessages
      .filter((m) => m.role !== "system")
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.text }));
  }

  async function handleForceProcess(msgIndex, skippedFile, accountName) {
    if (!skippedFile || chatLoading) return;
    setChatLoading(true);
    try {
      const uploadResult = await uploadFileForAccount(accountName, skippedFile, "account_upload", true);
      const rp = uploadResult.ingest_result?.records_processed || 0;
      const msg = rp > 0
        ? `**${skippedFile.name}** processed — ${uploadResult.ingest_result.message}`
        : `**${skippedFile.name}** saved to **${accountName}**. No new structured records were added.`;
      setChatMessages((prev) => {
        const updated = [...prev];
        updated.splice(msgIndex, 1);
        return [...updated, { role: "assistant", text: msg }];
      });
    } catch (err) {
      setChatMessages((prev) => [...prev, { role: "assistant", text: `Error: ${err.message}`, error: true }]);
    }
    setChatLoading(false);
  }

  async function sendMessage(e) {
    e.preventDefault();
    const q = chatInput.trim();
    const hasFile = !!pendingFile;
    const hasQuery = !!q;
    if ((!hasFile && !hasQuery) || chatLoading) return;

    const file = pendingFile;
    setChatInput("");
    setPendingFile(null);

    if (hasFile && hasQuery) {
      setChatMessages((prev) => [...prev, { role: "user", text: `${q} [File: ${file.name}]` }]);
    } else if (hasFile) {
      setChatMessages((prev) => [...prev, { role: "user", text: `Uploading: ${file.name}` }]);
    } else {
      setChatMessages((prev) => [...prev, { role: "user", text: q }]);
    }

    setChatLoading(true);
    const acctName = account?.account_name || "";

    try {
      if (hasFile) {
        const uploadResult = await uploadFileForAccount(acctName, file);

        if (uploadResult.is_relevant === false) {
          setChatMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              text: `This file doesn't appear to contain sales-related data. It has been saved to the archive.\n\nClick below to process it anyway.`,
              isRelevanceWarning: true,
              skippedFile: file,
              accountName: acctName,
            },
          ]);
        } else if (uploadResult.account_mismatch && uploadResult.other_accounts?.length > 0) {
          const others = uploadResult.other_accounts.join(", ");
          const rp = uploadResult.ingest_result?.records_processed || 0;
          let mismatchMsg = `**Heads up:** This file mentions **${others}**, which is different from **${acctName}**.`;
          if (rp > 0) {
            mismatchMsg += `\n\nThe data has been tagged to **${acctName}** and **${rp} record(s)** were added.`;
          } else {
            mismatchMsg += `\n\nThe file was saved to **${acctName}** but no new records were added.`;
          }
          mismatchMsg += ` If this file belongs to a different account, please upload it from that account's page instead.`;
          setChatMessages((prev) => [...prev, { role: "assistant", text: mismatchMsg }]);
        } else {
          const rp = uploadResult.ingest_result?.records_processed || 0;
          let uploadMsg;
          if (rp > 0) {
            uploadMsg = `**${file.name}** processed and added to **${acctName}** — ${uploadResult.ingest_result.message}`;
          } else {
            uploadMsg = `**${file.name}** saved to **${acctName}**. No new structured records were extracted (data may already exist).`;
          }
          setChatMessages((prev) => [...prev, { role: "assistant", text: uploadMsg }]);
        }
      }

      if (hasQuery) {
        const history = buildChatHistory();
        const res = await askQuestion(q, 10, acctName || null, history);
        setChatMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: res.answer || "No answer returned.",
            fallback: res.fallback_used,
          },
        ]);
      }
    } catch (err) {
      setChatMessages((prev) => [...prev, { role: "assistant", text: `Error: ${err.message}`, error: true }]);
    }
    setChatLoading(false);
  }

  if (loading) return (
    <div className="flex items-center justify-center flex-1">
      <Loader2 className="w-5 h-5 text-primary animate-spin" />
    </div>
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-background">
      {/* Header */}
      <div style={{ background: "#fff", borderBottom: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(46,78,153,0.04)" }} className="px-6 py-3 flex-shrink-0">
        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "#64748b", cursor: "pointer", marginBottom: 6, transition: "color 0.15s" }} className="hover:text-[#2E4E99]">
          <ArrowLeft style={{ width: 14, height: 14 }} /> Accounts
        </button>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div style={{ width: 4, height: 24, borderRadius: 2, background: "#2E4E99" }} />
            <div>
              <h1 style={{ fontSize: 17, fontWeight: 800, color: "#1C3268", letterSpacing: "-0.02em" }}>{account.account_name || "Unnamed"}</h1>
              <p style={{ fontSize: 12, color: "#64748b" }}>
                {account.industry || "—"}{account.geography ? ` · ${account.geography}` : ""}
              </p>
            </div>
          </div>
          {/* KPI pills */}
          <div className="flex items-center gap-3">
            {[
              { label: "Contacts",     val: contacts.length },
              { label: "Deals",        val: deals.length },
              { label: "Interactions", val: interactions.length },
              { label: "Insights",     val: insights.length },
            ].map((k) => (
              <div key={k.label} style={{ background: "#f8fafc", borderRadius: 8, padding: "5px 12px", textAlign: "center", border: "1px solid #e2e8f0", position: "relative", overflow: "hidden" }}>
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: "#2E4E99" }} />
                <p style={{ fontSize: 16, fontWeight: 700, color: "#2E4E99" }}>{k.val}</p>
                <p style={{ fontSize: 10, color: "#64748b" }}>{k.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Split: data left, chat right */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT: Account Data ── */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4" style={{ borderRight: "1px solid #e5e7eb" }}>

          {/* Deals */}
          <Section title="Deals">
            {deals.length === 0 ? <Empty text="No deals" /> : (
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: "1px solid #e5e7eb" }}>
                    {["Deal", "Stage", "Value", "Close Date"].map((h) => (
                      <th key={h} style={{ fontSize: 11, color: "#6b7280", fontWeight: 500, textAlign: "left", paddingBottom: 6 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {deals.map((d) => (
                    <tr key={d.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "7px 0", fontWeight: 500 }}>{d.deal_name || "Untitled"}</td>
                      <td><span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 3, background: "#e8edf5", color: "#2E4E99" }}>{d.deal_stage || "—"}</span></td>
                      <td style={{ fontWeight: 600 }}>{d.deal_value ? `$${Number(d.deal_value).toLocaleString()}` : "—"}</td>
                      <td style={{ color: "#6b7280", fontSize: 12 }}>{d.close_date || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          {/* Contacts */}
          <Section title="Contacts">
            {contacts.length === 0 ? <Empty text="No contacts" /> : (
              <div className="grid grid-cols-2 gap-2">
                {contacts.map((c) => (
                  <div key={c.id} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 14px" }}>
                    <p style={{ fontWeight: 600, fontSize: 13 }}>{c.contact_name || "Unknown"}</p>
                    <p style={{ fontSize: 11, color: "#6b7280" }}>{c.title || c.role || "—"}</p>
                    <div className="flex gap-3 mt-1">
                      {c.email && <span style={{ fontSize: 11, color: "#6b7280" }} className="flex items-center gap-1"><Mail className="w-3 h-3" />{c.email}</span>}
                      {c.phone && <span style={{ fontSize: 11, color: "#6b7280" }} className="flex items-center gap-1"><Phone className="w-3 h-3" />{c.phone}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Interactions */}
          <Section title="Recent Interactions">
            {interactions.length === 0 ? <Empty text="No interactions" /> : (
              <div className="space-y-2">
                {interactions.slice(0, 6).map((i) => (
                  <div key={i.id} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 14px" }}>
                    <div className="flex items-center justify-between">
                      <span style={{ fontWeight: 500, fontSize: 13 }}>{i.interaction_type || "Meeting"}</span>
                      {i.sentiment && (
                        <span style={{ fontSize: 11, padding: "1px 7px", borderRadius: 3,
                          background: i.sentiment?.toLowerCase() === "positive" ? "#dcfce7" : i.sentiment?.toLowerCase() === "negative" ? "#fee2e2" : "#f3f4f6",
                          color: i.sentiment?.toLowerCase() === "positive" ? "#15803d" : i.sentiment?.toLowerCase() === "negative" ? "#b91c1c" : "#374151"
                        }}>{i.sentiment}</span>
                      )}
                    </div>
                    {i.summary && <p style={{ fontSize: 12, color: "#6b7280", marginTop: 3 }}>{i.summary}</p>}
                    {i.interaction_date && <p style={{ fontSize: 11, color: "#9ca3af", marginTop: 3 }}>{i.interaction_date}</p>}
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Insights */}
          <Section title={`Insights (${insights.length})`}>
            {insights.length === 0 ? <Empty text="No insights yet — upload transcripts to generate insights for this account" /> : (
              <div className="space-y-3">
                {insights.map((ins) => {
                  const config = getInsightConfig(ins.insight_type);
                  const Icon = config.icon;
                  return (
                    <div key={ins.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "14px 16px", borderLeft: `3px solid ${config.color}`, boxShadow: "0 1px 3px rgba(46,78,153,0.06)" }}>
                      <div className="flex items-center gap-2.5 mb-2.5">
                        <div style={{ background: `${config.color}12`, borderRadius: 6, width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <Icon style={{ width: 15, height: 15, color: config.color }} />
                        </div>
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", padding: "2px 8px", borderRadius: 3, background: `${config.color}10`, border: `1px solid ${config.color}30`, color: config.color }}>
                            {config.label}
                          </span>
                          {ins.confidence && (
                            <span style={{ fontSize: 10, color: "#9ca3af", fontWeight: 500 }}>
                              Confidence: {ins.confidence}
                            </span>
                          )}
                          {ins.insight_date && (
                            <span style={{ fontSize: 10, color: "#9ca3af", marginLeft: "auto" }}>
                              {ins.insight_date}
                            </span>
                          )}
                        </div>
                      </div>
                      <p style={{ fontSize: 12.5, color: "#1f2937", lineHeight: 1.6, fontWeight: 500 }}>
                        {ins.content || "—"}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>
        </div>

        {/* ── RIGHT: Account-Scoped Chat ── */}
        <div style={{ width: 380, display: "flex", flexDirection: "column", background: "#fff" }}>
          <div style={{ padding: "14px 16px", borderBottom: "1px solid #e2e8f0", flexShrink: 0, background: "#f8fafc" }}>
            <div className="flex items-center gap-2">
              <div style={{ width: 24, height: 24, borderRadius: 6, background: "#2E4E99", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <MessageSquare style={{ width: 12, height: 12, color: "#fff" }} />
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#2E4E99" }}>Account Assistant</span>
            </div>
            <p style={{ fontSize: 11, color: "#64748b", marginTop: 3 }}>
              Scoped to <strong style={{ color: "#2E4E99" }}>{account.account_name}</strong>
            </p>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {chatMessages.map((msg, i) => {
              const isUser = msg.role === "user";
              const barColor = isUser ? "#2E4E99" : msg.isRelevanceWarning ? "#f59e0b" : "#3A5EAD";
              return (
                <div key={i} style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
                  <div style={{ maxWidth: "90%" }}>
                    <div style={{
                      fontSize: 12, lineHeight: 1.6, padding: "10px 14px", borderRadius: 8,
                      background: msg.isRelevanceWarning ? "#fffbeb" : isUser ? "#f8fafc" : "#ffffff",
                      color: msg.isRelevanceWarning ? "#92400e" : "#111827",
                      border: `1px solid ${msg.isRelevanceWarning ? "#fde68a" : "#e2e8f0"}`,
                      borderLeft: `3px solid ${barColor}`,
                      boxShadow: "0 1px 3px rgba(46,78,153,0.06)",
                    }}>
                      {msg.fallback && (
                        <p style={{ fontSize: 10, color: "#b45309", marginBottom: 4, fontWeight: 600 }}>Silver Layer</p>
                      )}
                      <MarkdownText text={msg.text} isUser={isUser} />
                    </div>
                    {msg.isRelevanceWarning && msg.skippedFile && (
                      <button
                        onClick={() => handleForceProcess(i, msg.skippedFile, msg.accountName)}
                        style={{
                          marginTop: 6, padding: "5px 12px", fontSize: 11, fontWeight: 600, borderRadius: 6,
                          border: "1px solid #fde68a", background: "#fffbeb", color: "#92400e", cursor: "pointer",
                        }}
                      >
                        Process anyway
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
            {chatLoading && (
              <div className="flex justify-start">
                <div style={{ borderLeft: "3px solid #2E4E99", background: "#fff", border: "1px solid #e2e8f0", borderLeftWidth: 3, borderLeftColor: "#2E4E99", borderRadius: 8, padding: "8px 14px", boxShadow: "0 1px 3px rgba(46,78,153,0.06)" }}>
                  <Loader2 style={{ width: 14, height: 14, color: "#2E4E99" }} className="animate-spin" />
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={sendMessage} style={{ padding: "12px 14px", borderTop: "1px solid #e2e8f0", flexShrink: 0, background: "#f8fafc" }}>
            {pendingFile && (
              <div className="flex items-center gap-1.5 mb-2">
                <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "2px 8px", borderRadius: 4, background: "rgba(46,78,153,0.06)", border: "1px solid rgba(46,78,153,0.12)" }}>
                  {pendingFile.name.endsWith(".pdf") ? (
                    <FileText style={{ width: 12, height: 12, color: "#2E4E99" }} />
                  ) : (
                    <FileSpreadsheet style={{ width: 12, height: 12, color: "#2E4E99" }} />
                  )}
                  <span style={{ fontSize: 11, color: "#2E4E99", fontWeight: 500 }}>{pendingFile.name}</span>
                  <button type="button" onClick={() => setPendingFile(null)} style={{ marginLeft: 2, color: "#94a3b8", cursor: "pointer" }} className="hover:text-[#dc2626]">
                    <X style={{ width: 12, height: 12 }} />
                  </button>
                </div>
              </div>
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                style={{ padding: 6, borderRadius: 6, flexShrink: 0, cursor: "pointer", transition: "background 0.15s" }}
                className="hover:bg-[#e2e8f0]"
                title="Attach file"
                disabled={chatLoading}
              >
                <Paperclip style={{ width: 16, height: 16, color: pendingFile ? "#2E4E99" : "#94a3b8" }} />
              </button>
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder={pendingFile ? "Ask about the uploaded file or just send..." : `Ask about ${account.account_name}…`}
                style={{ flex: 1, fontSize: 12, padding: "8px 12px", border: "1px solid #e2e8f0", borderRadius: 8, outline: "none", background: "#fff", transition: "border-color 0.2s" }}
                className="focus:border-[#2E4E99] placeholder-[#94a3b8]"
                disabled={chatLoading}
              />
              <button type="submit" disabled={chatLoading || (!chatInput.trim() && !pendingFile)}
                style={{ background: "#2E4E99", color: "#fff", borderRadius: 8, padding: "6px 14px", cursor: "pointer", opacity: chatLoading || (!chatInput.trim() && !pendingFile) ? 0.3 : 1, boxShadow: "0 2px 6px rgba(46,78,153,0.25)", transition: "transform 0.1s" }}
                className="hover:scale-105 active:scale-95">
                <Send style={{ width: 14, height: 14 }} />
              </button>
            </div>
            <p style={{ fontSize: 10, color: "#94a3b8", marginTop: 6 }}>
              Attach files by clicking the paperclip. Supports PDF, CSV, XLSX, TXT, DOCX.
            </p>
          </form>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.csv,.xlsx,.xls,.txt,.docx"
            onChange={(e) => { if (e.target.files[0]) stageFile(e.target.files[0]); e.target.value = ""; }}
            className="hidden"
          />
        </div>
      </div>
    </div>
  );
}

function MarkdownText({ text, isUser }) {
  if (!text) return null;
  const lines = text.split("\n");
  const elements = [];
  let listBuf = [];

  function flushList() {
    if (listBuf.length === 0) return;
    elements.push(
      <ul key={elements.length} style={{ margin: "4px 0 6px 0", paddingLeft: 16 }}>
        {listBuf.map((item, i) => (
          <li key={i} style={{ marginBottom: 2 }}>
            <InlineFormatted text={item} isUser={isUser} />
          </li>
        ))}
      </ul>
    );
    listBuf = [];
  }

  lines.forEach((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) { flushList(); elements.push(<br key={i} />); return; }
    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(<p key={i} style={{ fontSize: 11, fontWeight: 700, color: isUser ? "#bfdbfe" : "#374151", textTransform: "uppercase", letterSpacing: "0.05em", margin: "8px 0 3px" }}>{trimmed.slice(4)}</p>);
    } else if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(<p key={i} style={{ fontSize: 12, fontWeight: 700, color: isUser ? "#fff" : "#111827", borderBottom: isUser ? "1px solid rgba(255,255,255,0.2)" : "1px solid #e5e7eb", paddingBottom: 3, margin: "8px 0 4px" }}>{trimmed.slice(3)}</p>);
    } else if (trimmed.startsWith("# ")) {
      flushList();
      elements.push(<p key={i} style={{ fontSize: 13, fontWeight: 700, color: isUser ? "#fff" : "#111827", margin: "6px 0 4px" }}>{trimmed.slice(2)}</p>);
    } else if (/^[-*•] /.test(trimmed)) {
      listBuf.push(trimmed.replace(/^[-*•] /, ""));
    } else if (/^\d+\. /.test(trimmed)) {
      listBuf.push(trimmed.replace(/^\d+\. /, ""));
    } else {
      flushList();
      elements.push(<p key={i} style={{ margin: "2px 0" }}><InlineFormatted text={trimmed} isUser={isUser} /></p>);
    }
  });
  flushList();
  return <div style={{ fontSize: 12, lineHeight: 1.6 }}>{elements}</div>;
}

function InlineFormatted({ text, isUser }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <span>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**")
          ? <strong key={i} style={{ fontWeight: 600, color: isUser ? "#fff" : "#111827" }}>{part.slice(2, -2)}</strong>
          : <span key={i}>{part}</span>
      )}
    </span>
  );
}

const INSIGHT_TYPE_CONFIG = {
  deal_signal:  { icon: TrendingUp,    color: "#059669", label: "Deal Signal" },
  competitive:  { icon: Shield,        color: "#4f46e5", label: "Competitive Intel" },
  risk:         { icon: AlertTriangle, color: "#dc2626", label: "Risk" },
  action_items: { icon: Target,        color: "#d97706", label: "Action Items" },
  action_item:  { icon: Target,        color: "#d97706", label: "Action Item" },
  key_point:    { icon: Lightbulb,     color: "#2E4E99", label: "Key Point" },
};

function getInsightConfig(type) {
  return INSIGHT_TYPE_CONFIG[type] || { icon: Lightbulb, color: "#fb923c", label: type || "Insight" };
}

function Section({ title, children }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "16px 18px", boxShadow: "0 1px 3px rgba(46,78,153,0.06)" }}>
      <h3 style={{ fontSize: 12, fontWeight: 700, color: "#2E4E99", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.04em" }}>{title}</h3>
      {children}
    </div>
  );
}

function Empty({ text }) {
  return <p style={{ fontSize: 12, color: "#9ca3af", textAlign: "center", padding: "12px 0" }}>{text}</p>;
}

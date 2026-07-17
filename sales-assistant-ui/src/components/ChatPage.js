"use client";

import { useState, useRef, useEffect } from "react";
import {
  Send,
  FileText,
  FileSpreadsheet,
  Loader2,
  Paperclip,
  Upload,
  X,
} from "lucide-react";
import { askQuestion, uploadFile } from "@/lib/api";

const SAMPLE_QUESTIONS = [
  "What deals are in the pipeline?",
  "Show me all contacts",
  "What do we know about Acme Corp?",
  "What was discussed in recent meetings?",
  "What is the total deal value?",
  "Who are the decision makers?",
];

const WELCOME_MSG = {
  id: "welcome",
  role: "assistant",
  content:
    "Welcome to Sales Assistant. Ask about your CRM, ERP, or meeting data. You can also attach a file and ask about it in one step.",
  timestamp: new Date().toISOString(),
};

export default function ChatPage({
  onDataChange,
  conversation,
  activeConvId,
  onUpdateMessages,
  onNewConversation,
  hasConversation,
}) {
  const [messages, setMessages] = useState([WELCOME_MSG]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const inputRef = useRef(null);
  // Tracks the resolved conversation id for the current session (race-free)
  const convIdRef = useRef(activeConvId);

  useEffect(() => {
    convIdRef.current = activeConvId;
  }, [activeConvId]);

  useEffect(() => {
    if (conversation && conversation.messages.length > 0) {
      setMessages([WELCOME_MSG, ...conversation.messages]);
    } else {
      setMessages([WELCOME_MSG]);
    }
    convIdRef.current = conversation?.id ?? null;
  }, [conversation?.id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const pendingPersist = useRef(false);
  useEffect(() => {
    if (!pendingPersist.current) return;
    pendingPersist.current = false;
    const id = convIdRef.current;
    if (!id) return;
    const toSave = messages.filter((m) => m.id !== "welcome");
    onUpdateMessages?.(id, toSave);
  }, [messages]);

  function addMessage(role, content, meta = {}) {
    const msg = {
      id: Date.now().toString() + Math.random(),
      role,
      content,
      timestamp: new Date().toISOString(),
      ...meta,
    };
    pendingPersist.current = true;
    setMessages((prev) => [...prev, msg]);
    return msg;
  }

  async function handleSend() {
    const hasFile = !!pendingFile;
    const hasQuery = !!input.trim();
    if ((!hasFile && !hasQuery) || isLoading) return;

    // If no conversation yet, create one and capture its id immediately
    if (!convIdRef.current) {
      const newId = onNewConversation?.();
      if (newId) convIdRef.current = newId;
    }

    const query = input.trim();
    const file = pendingFile;
    setInput("");
    setPendingFile(null);

    if (hasFile && hasQuery) {
      addMessage("user", query, { fileName: file.name, fileType: file.name.split(".").pop().toLowerCase() });
    } else if (hasFile) {
      addMessage("user", `Uploaded: ${file.name}`, { fileName: file.name, fileType: file.name.split(".").pop().toLowerCase() });
    } else {
      addMessage("user", query);
    }

    setIsLoading(true);

    try {
      if (hasFile) {
        const uploadResult = await uploadFile(file);

        if (uploadResult.is_relevant === false) {
          addMessage(
            "assistant",
            `**Not processed:** ${uploadResult.relevance_message}\n\nThe file has been saved to the raw archive. Click below to process it anyway.`,
            {
              uploadResult,
              isRelevanceWarning: true,
              skippedFile: file,
            }
          );
        } else {
          if (uploadResult.file_overview) {
            addMessage("assistant", uploadResult.file_overview, {
              uploadResult,
              isFileOverview: true,
            });
          }

          const accts = uploadResult.accounts_found || [];
          const rp = uploadResult.ingest_result?.records_processed || 0;
          let ingestMsg;
          if (rp > 0) {
            ingestMsg = `**${file.name}** processed successfully — ${uploadResult.ingest_result.message}`;
          } else if (accts.length > 0) {
            ingestMsg = `**${file.name}** saved. Accounts mentioned: **${accts.join(", ")}**. No new records were added (data may already exist).`;
          } else {
            ingestMsg = `**${file.name}** saved to the archive. No structured records were extracted from this file.`;
          }
          addMessage("assistant", ingestMsg, { uploadResult });
        }
      }

      if (hasQuery) {
        // Build conversation history from previous messages (excluding welcome)
        const conversationHistory = messages
          .filter(m => m.id !== "welcome" && m.role !== "system")
          .slice(-6) // Last 3 exchanges (6 messages: user + assistant pairs)
          .map(m => ({
            role: m.role,
            content: m.content
          }));

        const result = await askQuestion(query, 10, null, conversationHistory);
        addMessage("assistant", result.answer, {
          sql: result.sql_queries,
          data: result.data,
          rowCount: result.row_count,
          executionTime: result.execution_time_ms,
          explanation: result.explanation,
          fallbackUsed: result.fallback_used,
          vectorUsed: result.vector_used,
        });
      }
    } catch (err) {
      addMessage(
        "assistant",
        `Error: ${err.message}. Make sure the backend is running on port 9000.`,
        { isError: true }
      );
    }
    setIsLoading(false);
    onDataChange?.();
  }

  async function handleForceProcess(msgId, skippedFile) {
    if (!skippedFile || isLoading) return;
    setIsLoading(true);
    try {
      const uploadResult = await uploadFile(skippedFile, "user_upload", true);

      setMessages((prev) => prev.filter((m) => m.id !== msgId));

      if (uploadResult.file_overview) {
        addMessage("assistant", uploadResult.file_overview, {
          uploadResult,
          isFileOverview: true,
        });
      }
      const rp = uploadResult.ingest_result?.records_processed || 0;
      const fMsg = rp > 0
        ? `File processed successfully — ${uploadResult.ingest_result.message}`
        : `File saved. ${uploadResult.ingest_result.message}`;
      addMessage("assistant", fMsg, { uploadResult });
    } catch (err) {
      addMessage("assistant", `Error: ${err.message}`, { isError: true });
    }
    setIsLoading(false);
    onDataChange?.();
  }

  function stageFile(file) {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    const supported = ["pdf", "csv", "xlsx", "xls", "txt", "docx"];
    if (!supported.includes(ext)) {
      addMessage(
        "assistant",
        `Unsupported file type: .${ext}. Supported: PDF, CSV, XLSX, TXT, DOCX`,
        { isError: true }
      );
      return;
    }
    setPendingFile(file);
    inputRef.current?.focus();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) stageFile(file);
  }

  return (
    <div
      className="flex-1 flex flex-col overflow-hidden relative bg-background"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div style={{ borderBottom: "1px solid #e2e8f0", background: "#ffffff", padding: "20px 24px" }}>
        <div className="max-w-2xl mx-auto">
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.03em", lineHeight: 1.2, color: "#1C3268" }}>
            Sales Assistant
          </h1>
          <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 4, fontWeight: 400 }}>Ask anything about your sales data, upload files, and get instant insights</p>
        </div>
      </div>

      {dragOver && (
        <div className="absolute inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(46,78,153,0.08)", border: "2px dashed #2E4E99" }}>
          <div style={{ background: "#fff", borderRadius: 12, padding: "32px 40px", textAlign: "center", boxShadow: "0 8px 32px rgba(46,78,153,0.15)", border: "1px solid #e2e8f0" }}>
            <Upload style={{ width: 40, height: 40, color: "#2E4E99", margin: "0 auto 8px" }} />
            <p style={{ fontSize: 14, fontWeight: 600, color: "#2E4E99" }}>Drop file to upload</p>
            <p style={{ fontSize: 12, color: "#64748b" }}>PDF, CSV, XLSX, TXT, or DOCX</p>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-2xl mx-auto space-y-4">
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} onForceProcess={handleForceProcess} />
          ))}

          {isLoading && (
            <div className="flex items-start">
              <div style={{ borderLeft: "3px solid #2E4E99", borderRadius: 8, background: "#fff", boxShadow: "0 1px 3px rgba(46,78,153,0.08)", padding: "10px 16px" }}>
                <div className="flex items-center gap-2.5">
                  <Loader2 style={{ width: 14, height: 14, color: "#2E4E99" }} className="animate-spin" />
                  <span style={{ fontSize: 13, color: "#64748b" }}>Processing...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {messages.length <= 1 && (
          <div className="max-w-2xl mx-auto mt-8">
            <p style={{ fontSize: 11, color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Suggested questions</p>
            <div className="grid grid-cols-2 gap-2.5">
              {SAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q); inputRef.current?.focus(); }}
                  style={{ textAlign: "left", fontSize: 12, padding: "10px 14px", borderRadius: 8, background: "#fff", border: "1px solid #e2e8f0", color: "#64748b", cursor: "pointer", transition: "all 0.15s", boxShadow: "0 1px 3px rgba(46,78,153,0.06)", borderLeft: "3px solid transparent" }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderLeftColor = "#2E4E99"; e.currentTarget.style.color = "#2E4E99"; e.currentTarget.style.boxShadow = "0 2px 8px rgba(46,78,153,0.1)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderLeftColor = "transparent"; e.currentTarget.style.color = "#64748b"; e.currentTarget.style.boxShadow = "0 1px 3px rgba(46,78,153,0.06)"; }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{ borderTop: "1px solid #e2e8f0", background: "#fff", padding: 16, boxShadow: "0 -2px 8px rgba(46,78,153,0.04)" }}>
        <div className="max-w-2xl mx-auto">
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: "8px 12px", transition: "border-color 0.2s, box-shadow 0.2s" }}
            className="focus-within:!border-[#2E4E99] focus-within:shadow-[0_0_0_3px_rgba(46,78,153,0.08)]">
            <button
              onClick={() => fileInputRef.current?.click()}
              style={{ padding: 4, borderRadius: 6, transition: "background 0.15s", flexShrink: 0, marginBottom: 2 }}
              className="hover:bg-[#e2e8f0]"
              title="Attach file"
            >
              <Paperclip style={{ width: 16, height: 16, color: pendingFile ? "#2E4E99" : "#94a3b8" }} />
            </button>
            <div className="flex-1 flex flex-col">
              {pendingFile && (
                <div className="flex items-center gap-1.5 mb-1.5">
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "2px 8px", borderRadius: 4, background: "rgba(46,78,153,0.06)", border: "1px solid rgba(46,78,153,0.12)" }}>
                    <FileText style={{ width: 12, height: 12, color: "#2E4E99" }} />
                    <span style={{ fontSize: 11, color: "#2E4E99", fontWeight: 500 }}>{pendingFile.name}</span>
                    <button onClick={() => setPendingFile(null)} style={{ marginLeft: 2, color: "#94a3b8", cursor: "pointer" }} className="hover:text-[#dc2626]">
                      <X style={{ width: 12, height: 12 }} />
                    </button>
                  </div>
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>Add a question or hit send</span>
                </div>
              )}
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={pendingFile ? "Ask about the uploaded file..." : "Ask about your sales data..."}
                style={{ flex: 1, background: "transparent", border: "none", outline: "none", fontSize: 13, color: "#111827", resize: "none", maxHeight: 128, minHeight: 20, lineHeight: 1.5 }}
                className="placeholder-[#94a3b8]"
                rows={1}
                disabled={isLoading}
              />
            </div>
            <button
              onClick={handleSend}
              disabled={(!input.trim() && !pendingFile) || isLoading}
              style={{ padding: "6px 8px", borderRadius: 8, background: "#2E4E99", boxShadow: "0 2px 6px rgba(46,78,153,0.25)", transition: "transform 0.1s, opacity 0.15s", flexShrink: 0, marginBottom: 2, cursor: "pointer", opacity: (!input.trim() && !pendingFile) || isLoading ? 0.3 : 1 }}
              className="hover:scale-105 active:scale-95 disabled:cursor-not-allowed"
            >
              <Send style={{ width: 16, height: 16, color: "#fff" }} />
            </button>
          </div>
          <p style={{ fontSize: 10, color: "#94a3b8", marginTop: 6, textAlign: "center" }}>
            Attach files by clicking the paperclip or dragging them here. Supports PDF, CSV, XLSX, TXT, DOCX.
          </p>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.csv,.xlsx,.xls,.txt,.docx"
        onChange={(e) => { if (e.target.files[0]) stageFile(e.target.files[0]); e.target.value = ""; }}
        className="hidden"
      />
    </div>
  );
}

function MarkdownContent({ content, isUser }) {
  const lines = content.split("\n");
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <pre key={i} style={{ margin: "8px 0", background: "#1C3268", color: "#e2e8f0", borderRadius: 8, fontSize: 11, fontFamily: "monospace", padding: "10px 14px", overflowX: "auto", whiteSpace: "pre" }}>
          {codeLines.join("\n")}
        </pre>
      );
      i++;
      continue;
    }

    // H1
    if (line.startsWith("# ")) {
      elements.push(<h1 key={i} className="text-base font-bold mt-3 mb-1 text-foreground">{renderInline(line.slice(2), isUser)}</h1>);
      i++; continue;
    }
    // H2
    if (line.startsWith("## ")) {
      elements.push(<h2 key={i} className="text-sm font-bold mt-2.5 mb-1 text-foreground border-b border-border pb-0.5">{renderInline(line.slice(3), isUser)}</h2>);
      i++; continue;
    }
    // H3
    if (line.startsWith("### ")) {
      elements.push(<h3 key={i} className="text-sm font-semibold mt-2 mb-0.5 text-foreground">{renderInline(line.slice(4), isUser)}</h3>);
      i++; continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      elements.push(<hr key={i} className="my-2 border-border" />);
      i++; continue;
    }

    // Unordered list — collect consecutive list items
    if (/^[-*•]\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*•]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*•]\s/, ""));
        i++;
      }
      elements.push(
        <ul key={i} className="my-1.5 space-y-0.5 pl-4">
          {items.map((item, j) => (
            <li key={j} className="text-sm leading-relaxed flex gap-2">
              <span style={{ marginTop: 6, width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: isUser ? "#94a3b8" : "#2E4E99" }} />
              <span>{renderInline(item, isUser)}</span>
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // Ordered list — collect consecutive numbered items
    if (/^\d+[.)]\s/.test(line)) {
      const items = [];
      let num = 1;
      while (i < lines.length && /^\d+[.)]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+[.)]\s/, ""));
        i++;
      }
      elements.push(
        <ol key={i} className="my-1.5 space-y-0.5 pl-4">
          {items.map((item, j) => (
            <li key={j} className="text-sm leading-relaxed flex gap-2">
              <span style={{ flexShrink: 0, fontWeight: 500, fontSize: 12, marginTop: 2, width: 16, color: isUser ? "#94a3b8" : "#2E4E99" }}>{j + 1}.</span>
              <span>{renderInline(item, isUser)}</span>
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // Blockquote
    if (line.startsWith("> ")) {
      elements.push(
        <blockquote key={i} className="border-l-2 border-primary pl-3 my-1.5 text-sm text-muted italic">
          {renderInline(line.slice(2), isUser)}
        </blockquote>
      );
      i++; continue;
    }

    // Empty line → spacer
    if (line.trim() === "") {
      elements.push(<div key={i} className="h-1.5" />);
      i++; continue;
    }

    // Normal paragraph
    elements.push(
      <p key={i} className="text-sm leading-relaxed">{renderInline(line, isUser)}</p>
    );
    i++;
  }

  return <div className="space-y-0.5">{elements}</div>;
}

function renderInline(text, isUser) {
  // Handle **bold**, *italic*, `code`, and plain text segments
  const parts = [];
  const pattern = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    if (match[2] !== undefined) {
      parts.push(<strong key={match.index} className="font-semibold">{match[2]}</strong>);
    } else if (match[3] !== undefined) {
      parts.push(<em key={match.index} className="italic">{match[3]}</em>);
    } else if (match[4] !== undefined) {
      parts.push(
        <code key={match.index} style={{ fontSize: 11, fontFamily: "monospace", padding: "1px 5px", borderRadius: 4, background: isUser ? "rgba(46,78,153,0.1)" : "#f1f5f9", border: isUser ? "none" : "1px solid #e2e8f0", color: isUser ? "#2E4E99" : "#2E4E99" }}>
          {match[4]}
        </code>
      );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : parts;
}

function ChatMessage({ message, onForceProcess }) {
  const isUser = message.role === "user";
  const [showDetails, setShowDetails] = useState(false);

  const ts = typeof message.timestamp === "string" ? new Date(message.timestamp) : message.timestamp;

  const accentColor = isUser ? "#2E4E99" : message.isRelevanceWarning ? "#f59e0b" : message.isError ? "#dc2626" : "#3A5EAD";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div style={{ maxWidth: "82%" }}>
        {/* File badge */}
        {message.fileName && (
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px", borderRadius: 6, background: "rgba(46,78,153,0.04)", border: "1px solid rgba(46,78,153,0.1)", marginBottom: 4 }}>
            {message.fileType === "pdf" ? (
              <FileText style={{ width: 12, height: 12, color: "#dc2626" }} />
            ) : (
              <FileSpreadsheet style={{ width: 12, height: 12, color: "#2E4E99" }} />
            )}
            <span style={{ fontSize: 11, color: "#64748b" }}>{message.fileName}</span>
          </div>
        )}

        {/* Layer / relevance badges */}
        {!isUser && !message.isError && message.id !== "welcome" && !message.isRelevanceWarning && (
          <div style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
            {message.vectorUsed === true && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 600, color: "#6d28d9", background: "#ede9fe", border: "1px solid #c4b5fd", borderRadius: 4, padding: "2px 8px" }}>
                ✦ Vector Search
              </span>
            )}
            {message.vectorUsed !== true && message.fallbackUsed === false && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 600, color: "#b45309", background: "#fef3c7", border: "1px solid #fde68a", borderRadius: 4, padding: "2px 8px" }}>
                Gold Layer
              </span>
            )}
            {message.vectorUsed !== true && message.fallbackUsed === true && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 600, color: "#2E4E99", background: "#e8edf5", border: "1px solid #c5d0e6", borderRadius: 4, padding: "2px 8px" }}>
                Silver Layer
              </span>
            )}
          </div>
        )}
        {message.isRelevanceWarning && (
          <div style={{ marginBottom: 4 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 600, color: "#92400e", background: "#fef3c7", border: "1px solid #fde68a", borderRadius: 4, padding: "2px 8px" }}>
              Not Sales Data
            </span>
          </div>
        )}

        {/* Card-style bubble with left accent bar */}
        <div style={{
          borderLeft: `3px solid ${accentColor}`,
          borderRadius: 8,
          padding: "12px 16px",
          background: isUser ? "#f8fafc" : message.isRelevanceWarning ? "#fffbeb" : message.isError ? "#fef2f2" : "#ffffff",
          boxShadow: "0 1px 3px rgba(46,78,153,0.08)",
          border: `1px solid ${message.isRelevanceWarning ? "#fde68a" : message.isError ? "#fecaca" : "#e2e8f0"}`,
          borderLeftWidth: 3,
          borderLeftColor: accentColor,
          color: message.isRelevanceWarning ? "#92400e" : message.isError ? "#dc2626" : "#111827",
        }}>
          {isUser ? (
            <p style={{ fontSize: 13, whiteSpace: "pre-wrap", lineHeight: 1.6, color: "#2E4E99", fontWeight: 450 }}>{message.content}</p>
          ) : (
            <MarkdownContent content={message.content} isUser={false} />
          )}
        </div>

        {/* Force process button */}
        {message.isRelevanceWarning && message.skippedFile && (
          <button
            onClick={() => onForceProcess?.(message.id, message.skippedFile)}
            style={{ marginTop: 8, padding: "5px 12px", fontSize: 11, fontWeight: 600, borderRadius: 6, border: "1px solid #fde68a", background: "#fffbeb", color: "#92400e", cursor: "pointer", transition: "background 0.15s" }}
            className="hover:bg-[#fef3c7]"
          >
            Process anyway
          </button>
        )}

        {/* Metadata row */}
        {(message.sql || message.uploadResult) && (
          <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8 }}>
            {message.executionTime && (
              <span style={{ fontSize: 10, color: "#94a3b8" }}>{Math.round(message.executionTime)}ms</span>
            )}
            {message.rowCount !== undefined && (
              <span style={{ fontSize: 10, color: "#94a3b8" }}>{message.rowCount} rows</span>
            )}
            {(message.sql || message.data) && (
              <button
                onClick={() => setShowDetails(!showDetails)}
                style={{ fontSize: 10, color: "#2E4E99", cursor: "pointer", fontWeight: 500 }}
                className="hover:underline"
              >
                {showDetails ? "Hide details" : "Show details"}
              </button>
            )}
          </div>
        )}

        {/* Details panel */}
        {showDetails && (
          <div style={{ marginTop: 8, background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0", padding: 12, textAlign: "left", boxShadow: "0 1px 3px rgba(46,78,153,0.06)" }}>
            {message.sql && (
              <div style={{ marginBottom: 12 }}>
                <p style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4, fontWeight: 600 }}>SQL</p>
                {message.sql.map((q, i) => (
                  <pre key={i} style={{ fontSize: 11, color: "#e2e8f0", background: "#1C3268", borderRadius: 6, padding: "8px 10px", overflowX: "auto", marginBottom: 4, fontFamily: "monospace" }}>
                    {q}
                  </pre>
                ))}
              </div>
            )}
            {message.data && message.data.length > 0 && (
              <div>
                <p style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4, fontWeight: 600 }}>
                  Results ({message.data.length})
                </p>
                <div style={{ overflowX: "auto", maxHeight: 192, overflowY: "auto" }}>
                  <table style={{ width: "100%", fontSize: 11 }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                        {Object.keys(message.data[0]).filter((k) => k !== "source_data").slice(0, 6).map((key) => (
                          <th key={key} style={{ textAlign: "left", padding: "4px 8px", color: "#64748b", fontWeight: 500 }}>{key}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {message.data.slice(0, 10).map((row, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                          {Object.entries(row).filter(([k]) => k !== "source_data").slice(0, 6).map(([k, v], j) => (
                            <td key={j} style={{ padding: "4px 8px", color: "#64748b", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {v !== null ? String(v).substring(0, 50) : "-"}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        <span style={{ fontSize: 10, color: "#94a3b8", marginTop: 4, display: "block", textAlign: isUser ? "right" : "left" }}>
          {ts instanceof Date && !isNaN(ts) ? ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
        </span>
      </div>
    </div>
  );
}

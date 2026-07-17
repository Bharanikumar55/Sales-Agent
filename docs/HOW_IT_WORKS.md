# Sales Agent — How It Works

---

## What Is This?

Sales Agent is an **AI-powered data platform for sales teams**. It takes messy, scattered sales data — meeting transcripts, CRM exports, uploaded documents — and turns it into a clean, organized knowledge base that anyone can ask questions to in plain English.

**Think of it as:** "Upload your sales data, then chat with it."

---

## The Problem It Solves

A typical sales team has data everywhere:

- Meeting notes in Word docs
- CRM exports in Excel
- Call transcripts from Zoom / Teams
- Account info in PDFs
- Deal updates scattered across tools

Nobody has time to dig through all of this before a client call or a pipeline review.

Sales Agent brings all of it into **one place**, automatically extracts the important information, and lets anyone ask questions like:

> "What deals are in the pipeline?"
> "Who are the contacts at Infosys?"
> "What was discussed in the last meeting with HCC?"
> "Which accounts are at risk?"

---

## Architecture Diagrams

We use a **3-layer data design** called the Medallion Architecture: **Bronze → Silver → Gold**. Each layer refines the data further.

### Diagram 1: What Lives in Each Layer

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  🥉 BRONZE — Raw Archive                                   │
│  Every file saved exactly as uploaded. Never modified.      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  raw_ingestion (PDF text, CSV rows, Word docs as JSON) │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │                                  │
│               AI extracts + organizes                       │
│                          ▼                                  │
│  🥈 SILVER — Organized Entity Tables                       │
│  Clean, linked business data — one table per concept.       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  dim_account        Companies & profiles               │ │
│  │  dim_contact        People & roles                     │ │
│  │  fact_deals         Deals, values & stages             │ │
│  │  fact_interactions  Meetings, calls & emails           │ │
│  │  fact_insights      Signals & competitive intel        │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │                                  │
│                SQL aggregates                               │
│                          ▼                                  │
│  🥇 GOLD — Ready-Made Business Reports                     │
│  Pre-built answers to common sales questions.               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  revenue_summary    Revenue per account                │ │
│  │  top_customers      Biggest customers ranked           │ │
│  │  pipeline_health    Deal stages & values               │ │
│  │  account_360        Full profile per account           │ │
│  │  activity_summary   Engagement per account             │ │
│  │  deals_closing_soon Upcoming close dates               │ │
│  │  at_risk_accounts   Accounts needing attention         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Diagram 2: How the System Works

```
┌────────────────────────────────────────────────────────────────┐
│                          SALES AGENT                           │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  USER INTERFACE                                          │  │
│  │                                                          │  │
│  │  Dashboard       Accounts       Pipeline       Chat      │  │
│  │  (KPIs &         (company       (deal          (ask      │  │
│  │   stats)          profiles)      tracker)       anything) │  │
│  └───────────────────────┬──────────────────────────────────┘  │
│                          │                                     │
│                  upload files / ask questions                   │
│                          │                                     │
│  ┌───────────────────────▼──────────────────────────────────┐  │
│  │  AI PROCESSING LAYER                                     │  │
│  │                                                          │  │
│  │  Read & Extract ──→ Classify & Organize ──→ Answer Qs    │  │
│  │  (PDF, Word, CSV,    (map fields to the     (plain       │  │
│  │   transcripts)        right tables)          English      │  │
│  │                                              → SQL →      │  │
│  │                                              readable)    │  │
│  └───────────────────────┬──────────────────────────────────┘  │
│                          │                                     │
│              store in 3 layers (Medallion Architecture)         │
│                          │                                     │
│  ┌───────────────────────▼──────────────────────────────────┐  │
│  │  🥉 BRONZE — Raw Archive                                 │  │
│  │                                                          │  │
│  │  Every file saved exactly as uploaded. Never modified.    │  │
│  │  If anything goes wrong, the original data is always here.│  │
│  └───────────────────────┬──────────────────────────────────┘  │
│                     clean & organize                            │
│  ┌───────────────────────▼──────────────────────────────────┐  │
│  │  🥈 SILVER — Organized Entity Tables                     │  │
│  │                                                          │  │
│  │  Data split into 5 clean tables (linked by account ID):  │  │
│  │  Accounts · Contacts · Deals · Meetings · Insights       │  │
│  └───────────────────────┬──────────────────────────────────┘  │
│                  aggregate & summarize                          │
│  ┌───────────────────────▼──────────────────────────────────┐  │
│  │  🥇 GOLD — Ready-Made Business Reports                   │  │
│  │                                                          │  │
│  │  Pre-built answers to common sales questions.            │  │
│  │  Revenue Summary · Pipeline Health · Top Customers       │  │
│  │  Deals Closing Soon · At-Risk Accounts · Account 360°    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  QUERY FLOW:                                                   │
│  Question → try Gold (fast) → Silver (detailed) → if still     │
│  empty, extract from Bronze into Silver → re-query → answer    │
└────────────────────────────────────────────────────────────────┘
```

### Why Three Layers?

| Layer | Purpose | Analogy |
|---|---|---|
| **Bronze** | Raw archive — save everything exactly as received | A filing cabinet of originals |
| **Silver** | Organized data — split into accounts, contacts, deals, meetings, insights | A clean spreadsheet with labeled columns |
| **Gold** | Pre-built reports — instant answers to common questions | A dashboard that's always up to date |

---

## What Happens — Step by Step (with examples)

There are three things a user can do. Here's exactly what happens inside the system for each one.

### FLOW 1: User Uploads a File

```
  EXAMPLE: Sales rep drags "HCC_meeting_notes.docx" into the chat
  ─────────────────────────────────────────────────────────────────

  ┌─────────────┐
  │  Rep drags   │
  │  .docx file  │
  │  into chat   │
  └──────┬──────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 1: READ THE FILE                               │
  │                                                       │
  │  System detects file type → Word document              │
  │  Extracts all text from the .docx                      │
  │  Result: 3 pages of raw meeting conversation           │
  └──────────────────────┬────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 2: AI EXTRACTS BUSINESS INFO                   │
  │                                                       │
  │  AI reads the raw text and pulls out:                  │
  │                                                       │
  │  ✓ Company    → "Hancock Claims Consultants (HCC)"    │
  │  ✓ Deal       → "Content Pricing Genie, $320K"        │
  │  ✓ Stage      → "Discovery"                           │
  │  ✓ Contacts   → "David Chen (VP Tech), Sarah Lin"     │
  │  ✓ Sentiment  → "Positive"                            │
  │  ✓ Competitor → "Verisk, Cognizant"                   │
  │  ✓ Actions    → "Send SOW by Wed, call David Thu"     │
  │  ✓ Signal     → "Buying intent: HIGH"                 │
  └──────────────────────┬────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 3: STORE & ORGANIZE                            │
  │                                                       │
  │  Raw file → saved to archive (never lost)              │
  │                                                       │
  │  Extracted data → sorted into the right tables:        │
  │    Accounts table  ← "HCC" added/updated               │
  │    Contacts table  ← David Chen, Sarah Lin              │
  │    Deals table     ← Pricing Genie, $320K, Discovery    │
  │    Meetings table  ← Today's meeting, Positive          │
  │    Insights table  ← Competitor threat, Buying signal    │
  └──────────────────────┬────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 4: REBUILD REPORTS                              │
  │                                                       │
  │  All dashboards auto-update:                           │
  │    Pipeline  → now shows $320K HCC deal                │
  │    At-Risk   → recalculated                            │
  │    Top Custs → rankings refreshed                      │
  └──────────────────────┬────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 5: SHOW SUMMARY IN CHAT                        │
  │                                                       │
  │  💬 "Here's what I found in HCC_meeting_notes.docx:   │
  │     Company: Hancock Claims Consultants                │
  │     Deal: Content Pricing Genie — $320K — Discovery    │
  │     Contacts: David Chen (VP Tech), Sarah Lin          │
  │     Sentiment: Positive                                │
  │     Competitors: Verisk, Cognizant                     │
  │     Next Steps: Send SOW by Wed, call David Thu"       │
  │                                                       │
  │  File ingested: 1 record into 5 tables                 │
  └─────────────────────────────────────────────────────┘
```

### FLOW 2: User Asks a Question

```
  EXAMPLE: Manager types "What's happening with the HCC deal?"
  ─────────────────────────────────────────────────────────────

  ┌──────────────────┐
  │  Manager types:   │
  │  "What's happening│
  │   with the HCC    │
  │   deal?"          │
  └────────┬─────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 1: UNDERSTAND THE QUESTION                     │
  │                                                       │
  │  AI reads the question and figures out:                │
  │  "They want deal info for an account called HCC"      │
  │                                                       │
  │  Looks at what tables exist in the database            │
  │  and writes a database query to find the answer        │
  └──────────────────────┬────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 2: TRY FAST REPORTS FIRST                      │
  │                                                       │
  │  Check ready-made reports (Gold layer):                │
  │    account_360 → Has HCC? ✓ YES                        │
  │                                                       │
  │  Found:                                                │
  │    Deal: Content Pricing Genie                         │
  │    Value: $320,000                                     │
  │    Stage: Discovery                                    │
  │    Contacts: 2                                         │
  │    Meetings: 1                                         │
  │    Insights: 3                                         │
  └──────────────────────┬────────────────────────────────┘
           │
           ▼  (if reports didn't have the answer,
           │   system falls back to detailed tables)
           │
           ▼  (if detailed tables also have nothing,
           │   system searches raw files in Bronze,
           │   extracts data with AI, saves to Silver,
           │   and tries the query one more time)
           │
  ┌─────────────────────────────────────────────────────┐
  │  STEP 3: BUILD A READABLE ANSWER                     │
  │                                                       │
  │  AI takes the raw data and writes a human-friendly     │
  │  response — not a spreadsheet, not SQL, just a         │
  │  clear summary:                                        │
  │                                                       │
  │  💬 "Hancock Claims Consultants — Content Pricing      │
  │     Genie                                              │
  │     • Deal Value: $320,000                             │
  │     • Stage: Discovery                                 │
  │     • Decision Maker: David Chen, VP of Technology     │
  │     • Sentiment: Positive                              │
  │     • Competitors: Verisk and Cognizant                │
  │     • Next Steps: Send SOW by Wed, call David Thu"     │
  └─────────────────────────────────────────────────────┘
```

### FLOW 3: User Uploads a Spreadsheet (Structured Data)

```
  EXAMPLE: Admin uploads "Q1_pipeline_export.csv" from Salesforce
  ─────────────────────────────────────────────────────────────────

  ┌──────────────┐
  │  Admin drags   │
  │  .csv file     │
  │  into chat     │
  └──────┬───────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 1: READ THE FILE                               │
  │                                                       │
  │  System detects → CSV (structured data)                │
  │  Parses 47 rows, 12 columns                           │
  │  Columns: Account, Deal, Value, Stage, Close Date...   │
  └──────────────────────┬────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 2: MAP FIELDS (NO AI NEEDED)                   │
  │                                                       │
  │  Column "Account"    → accounts table                  │
  │  Column "Deal Name"  → deals table                     │
  │  Column "Amount"     → deal_value                      │
  │  Column "Stage"      → deal_stage                      │
  │  Column "Close Date" → close_date                      │
  │                                                       │
  │  ⚡ This is instant — no AI, just direct mapping       │
  │                                                       │
  │  Unknown column "NPS Score"?                           │
  │  → AI decides: add to accounts table as new column     │
  └──────────────────────┬────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │  STEP 3: STORE & REBUILD                              │
  │                                                       │
  │  47 rows → split across accounts, deals, contacts      │
  │  15 accounts updated, 32 deals added                   │
  │  All dashboards refresh automatically                  │
  │                                                       │
  │  💬 "File ingested: 47 records into 3 tables           │
  │     [deterministic mapping — no AI needed]"            │
  └─────────────────────────────────────────────────────┘
```

### Quick Comparison: The Three Flows

```
  ┌────────────────┬──────────────────────┬─────────────────────┐
  │  What User Does │  What System Does    │  AI Involved?       │
  ├────────────────┼──────────────────────┼─────────────────────┤
  │                │                      │                     │
  │  Upload a      │  Read → AI extracts  │  YES — reads the    │
  │  transcript    │  entities → store    │  text, pulls out    │
  │  (.docx .pdf   │  in 5 tables →       │  companies, deals,  │
  │   .txt)        │  rebuild reports     │  people, signals    │
  │                │                      │                     │
  ├────────────────┼──────────────────────┼─────────────────────┤
  │                │                      │                     │
  │  Upload a      │  Read → map columns  │  NO — direct field  │
  │  spreadsheet   │  to tables → store   │  mapping. AI only   │
  │  (.csv .xlsx)  │  → rebuild reports   │  if unknown columns │
  │                │                      │                     │
  ├────────────────┼──────────────────────┼─────────────────────┤
  │                │                      │                     │
  │  Ask a         │  Understand question │  YES — writes the   │
  │  question      │  → query database    │  database query and │
  │                │  → build readable    │  writes the human-  │
  │                │    answer            │  readable answer     │
  │                │                      │                     │
  └────────────────┴──────────────────────┴─────────────────────┘
```

---

## High-Level Flow

### 1. Data Comes In

Sales reps and managers feed data into the system through two ways:

- **Upload files** — drag a PDF, Excel, Word doc, CSV, or text file into the chat
- **API integration** — CRM systems, Zoom, Gong, or other tools push data automatically

The system accepts **any format** — messy meeting transcripts, clean spreadsheets, or anything in between.

### 2. AI Reads and Extracts

The AI reads every piece of incoming data and pulls out the business-relevant information:

| From a meeting transcript | From a CRM spreadsheet |
|---|---|
| Company name, industry, location | Already structured — just maps fields |
| Deal name, value, stage | to the right place in the knowledge base |
| People mentioned and their roles | |
| Sentiment (positive / negative / neutral) | |
| Competitors mentioned | |
| Action items and deadlines | |
| Buying signals | |

For structured files (CSV, Excel), no AI is needed — fields map directly. AI only activates for messy, unstructured data like transcripts and notes.

### 3. Data Gets Organized

Everything extracted is organized into five categories:

| Category | What It Holds | Example |
|---|---|---|
| **Accounts** | Companies you sell to | Infosys, HCC, Wipro |
| **Contacts** | People at those companies | Rajesh Menon — VP Engineering at Infosys |
| **Deals** | Sales opportunities | Cloud Migration — $450K — Negotiation stage |
| **Meetings** | Calls, meetings, emails | March 14 call with HCC — Positive sentiment |
| **Insights** | AI-detected intelligence | Verisk is competing for the HCC deal; buying intent is High |

If data about the same company comes from multiple sources (a transcript + a CSV + another transcript), the system **merges** it — no duplicates, just a richer profile. This works because every account gets a stable internal ID. When a new file mentions "HCC" and the system already knows "HCC Corp", it recognizes they're the same account and links the data together automatically.

### 4. Reports Build Themselves

After every upload, the system automatically builds business reports that answer the most common sales questions:

| Report | What It Answers |
|---|---|
| **Revenue Summary** | What is our total revenue exposure per account? |
| **Top Customers** | Who are our biggest accounts by total deal value? |
| **Pipeline Health** | What does our active deal pipeline look like by stage? |
| **Account 360°** | Give me the full picture on one account |
| **Activity Summary** | How active are we with each account? |
| **Deals Closing Soon** | Which open deals have a close date coming up? |
| **At-Risk Accounts** | Which accounts with open deals have gone cold? |

These reports update automatically — nobody has to manually build a dashboard.

### 5. Ask Anything

Users can ask questions in plain English through the chat:

> **User:** "What's happening with the HCC deal?"
>
> **Sales Agent:**
> **Hancock Claims Consultants — Content Pricing Genie**
> - **Deal Value:** $320,000
> - **Stage:** Discovery
> - **Decision Maker:** David Chen, VP of Technology
> - **Sentiment:** Positive
> - **Competitors:** Verisk and Cognizant are in the picture
> - **Next Steps:** Send revised SOW by Wednesday, schedule call with David Chen for Thursday
> - **Timeline:** MVP needed by end of Q2 2026

The system finds the answer from the organized data and returns it in a clean, readable format — not raw tables or database rows.

---

## What the User Sees

The interface has four sections:

### Dashboard
A quick overview of everything — total accounts, total deals, pipeline value, recent activity. Like a sales cockpit.

### Accounts
A list of every company in the system. Click any account to see:
- Company profile (industry, geography, size)
- All deals with that company
- Key contacts and their roles
- Recent meetings and their sentiment
- AI-detected insights scoped to that account:
  - **Deal signals** — "Buying intent is High. Budget confirmed. Decision maker is engaged."
  - **Competitive intel** — "Verisk and Cognizant were mentioned in the meeting."
  - **Action items** — "Send revised SOW by Wednesday. Schedule David Chen call for Thursday."
- An account-scoped chat — ask questions only about this company

### Pipeline
All active deals in one view — who, how much, what stage, when it closes. Useful for weekly pipeline reviews.

### Chat (Sales Assistant)
The main conversational interface. Users can:
- Ask any question about their data
- Upload files and ask about them in the same message
- Get answers with deal values, contact names, and next steps highlighted

---

## Real-World Examples

### A sales rep uploads a meeting transcript

They just got off a Zoom call with a potential client. They drag the transcript file into the chat. Within seconds:

1. The system reads the entire conversation
2. Extracts the company name, deal value, competitors, next steps
3. Creates or updates the account, deal, and contact records
4. Flags competitive threats and buying signals
5. Shows a summary right in the chat

The rep didn't fill out a single CRM field. The data is already there.

### A manager prepares for a pipeline review

They ask: "Show me all deals closing this quarter and their risk level"

The system pulls from the ready-made reports, cross-references with meeting sentiment and activity levels, and returns a structured summary — which deals are on track, which are stalling, and which have competitive threats.

### A new team member gets up to speed

They ask: "What do we know about Infosys?"

The system returns everything — company profile, all deals (past and current), every contact and their role, recent meeting summaries, competitor landscape, and pending action items. Months of institutional knowledge, available instantly.

---

## How Data Stays Safe

- **Nothing is lost** — Every raw upload is archived before any processing happens. If AI makes a mistake, the original data is always available.
- **No duplicates** — When the same company or person appears in multiple uploads, the system merges the information instead of creating copies. Each account gets a stable internal ID, so "HCC", "HCC Corp", and "hcc" all resolve to the same account.
- **Bad data is caught, not hidden** — Before storing anything, the system checks every record: Are required fields present? Is the deal value actually a number? Records that fail these checks are skipped and logged separately for review — the rest of the upload continues normally.
- **Non-sales files are flagged** — If someone uploads a file that doesn't look like sales data (no accounts, deals, contacts, or revenue info), the system saves it to the raw archive but skips processing. The user is told why and can choose to force-process it anyway.
- **Data builds on itself** — Each new upload enriches existing records. The more data goes in, the smarter the system gets.

---

## What Makes This Different

| Traditional CRM | Sales Agent |
|---|---|
| Reps manually enter data | AI extracts data from files and transcripts |
| Dashboards need manual setup | Reports build and update themselves |
| Searching means clicking through menus | Just ask a question in English |
| Meeting notes sit in docs nobody reads | Insights, competitors, and action items are extracted automatically |
| Data entry is a chore people skip | Upload a file and you're done |

**Sales Agent turns data entry into data conversation.**

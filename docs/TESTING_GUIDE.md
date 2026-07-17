# Testing Guide — Sales Agent Query Routing

This guide documents how to verify the three-tier query routing:
**Gold → Silver → Vector Search**

---

## Prerequisites

1. Backend running with venv activated:
   ```powershell
   .\venv\Scripts\activate
   uvicorn app.main:app --reload --port 9000
   ```
2. `.env` contains:
   ```
   PINECONE_API_KEY=<your-key>
   PINECONE_INDEX=sales-agent
   ```
3. Upload `simulation/buymore_meeting_notes.txt` via the UI or:
   ```
   POST /api/v1/data/upload
   file: buymore_meeting_notes.txt
   ```
   Confirm logs show:
   ```
   VectorStore: Ready ✅
   📌 Vector store: 2 chunk(s) indexed
   ```

---

## Test 1 — Gold Layer

**Query:** `what is the total deal value for Buy More?`

**Why Gold answers it:**
- `gold.account_360` and `gold.revenue_summary` have pre-aggregated deal values
- No narrative keywords → intent = `metric`
- Gold mart returns rows on first attempt

**Expected logs:**
```
🧭 Question intent: metric
```
No Silver fallback, no vector search.

**Expected UI:**
- 🟡 **Gold Layer** badge
- `vector_used: false`, `fallback_used: false`

---

## Test 2 — Silver Layer

**Query:** `Who are the contacts at Buy More?`

**Why Silver answers it:**
- Gold has no contacts mart
- Intent = `metric` (no narrative keywords) → goes to Silver SQL
- `silver.dim_contact` has the 3 contacts extracted from the meeting note

**Expected logs:**
```
🧭 Question intent: metric
ℹ️ GPT queried Silver directly on first attempt (no Gold tables used)
```
No vector search triggered.

**Expected UI:**
- 🔵 **Silver Layer** badge
- `vector_used: false`, `fallback_used: true`

---

## Test 3 — Vector Search

**Query:** `what was discussed in the Buy More meeting?`

**Why Vector answers it:**
- Narrative keywords detected: `"what was discussed"` + `"meeting"`
- Intent = `narrative` → vector search runs immediately after Gold
- Pinecone returns 2 chunks from `buymore_meeting_notes.txt` with scores ~0.61, ~0.38
- Answer synthesized from raw document prose, not SQL rows

**Expected logs:**
```
🧭 Question intent: narrative
📊 Vector scores: [0.614, 0.379]
🔍 Vector search: 2 chunk(s) above threshold
```

**Expected UI:**
- 🟣 **✦ Vector Search** badge
- `vector_used: true`
- Answer cites `buymore_meeting_notes.txt` as source
- No SQL shown, no "Hide details" section

---

## Test 4 — Vector with account filter

**Query:** `summarize the Buy More meeting notes`
**account_context:** `Buy More`

Same as Test 3 but Pinecone filters by `account_name = "Buy More"` metadata before scoring.

---

## Test 5 — Direct Vector Search endpoint

```
POST /api/v1/vector/search
query = "inventory cloud expansion"
account_name = "Buy More"
top_k = 5
```

Returns raw chunks with scores — useful for debugging what's indexed.

---

## Test 6 — Pinecone index stats

```
GET /api/v1/vector/stats
```

Returns total vectors indexed, dimension (1536), metric (cosine).

---

## Routing Summary

| Question type | Example | Badge | `vector_used` | `fallback_used` |
|---|---|---|---|---|
| Aggregated metrics | total deal value | 🟡 Gold Layer | false | false |
| Entity lookups | contacts, deals list | 🔵 Silver Layer | false | true |
| Meeting / narrative | what was discussed | 🟣 Vector Search | true | — |

---

## How intent is classified

The classifier in `NLQueryEngine._classify_question_intent()` is purely rule-based (no LLM call):

- **Narrative signals** (→ Vector first): `what was discussed`, `meeting`, `summarize`, `mentioned`, `transcript`, `action items`, `next steps`, `how did`, `talked about`, etc.
- **Metric signals** (→ Silver SQL first): `how many`, `total`, `revenue`, `count`, `which deals`, `top`, `at risk`, etc.

If a question scores higher on narrative keywords it routes to Vector. Ties go to metric (Silver).

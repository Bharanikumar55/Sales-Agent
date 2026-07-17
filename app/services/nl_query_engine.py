"""Natural Language Query Engine - Converts NLP queries to SQL and synthesizes answers"""
import json
import logging
import time
import concurrent.futures
from typing import Dict, Any, List, Tuple
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config import settings
from app.services.schema_introspector import build_dynamic_prompt
from app.services.gold_schema_agent import GoldSchemaAgent
from app.services.bronze_enrichment import BronzeEnrichmentService
from app.services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

_llm_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm")


class NLQueryEngine:
    """
    Converts natural language questions to SQL queries.
    Executes queries and synthesizes human-readable answers.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=45.0,
            max_retries=1,
        )
        self.vector_store = VectorStoreService()
    
    # Common greetings and their responses
    GREETINGS = [
        'hi', 'hello', 'hey', 'hola', 'namaste', 'good morning',
        'good afternoon', 'good evening', 'greetings', 'yo', 'sup',
        'howdy', 'hi there', 'hey there', 'what\'s up', 'how are you'
    ]

    def _is_greeting(self, question: str) -> bool:
        """Check if the input is a simple greeting."""
        question_lower = question.strip().lower()
        # Check for exact match or if question starts with a greeting word
        for greeting in self.GREETINGS:
            if question_lower == greeting or question_lower.startswith(greeting + ' ') or question_lower.startswith(greeting + '!'):
                return True
        return False

    def _get_greeting_response(self, question: str, account_context: str = None) -> Dict[str, Any]:
        """Generate a friendly greeting response."""
        import random
        
        # Personalized greeting if account context exists
        if account_context:
            greetings = [
                f"👋 Hello! I'm here to help you with **{account_context}**. Ask me anything about their deals, contacts, meetings, or insights!",
                f"Hey there! Ready to dive into **{account_context}** data. What would you like to know?",
                f"Hi! I'm your AI assistant for **{account_context}**. Fire away with your questions!",
            ]
        else:
            greetings = [
                "👋 Hello! I'm your AI assistant for the semantic layer. Ask me about accounts, deals, contacts, meetings, or any business data!",
                "Hey there! Ready to help you explore your data. What can I do for you today?",
                "Hi! I'm here to answer questions about your sales pipeline, accounts, and business insights. What would you like to know?",
                "Hello! Ask me anything about your accounts, deals, pipeline, or recent meetings!",
                "Hey! I'm your data assistant. I can help you with questions about accounts, deals, contacts, and more!",
            ]
        
        answer = random.choice(greetings)
        
        return {
            "status": "success",
            "answer": answer,
            "sql_queries": [],
            "data": [],
            "explanation": "Greeting detected - no database query needed",
            "row_count": 0,
            "execution_time_ms": 0,
            "fallback_used": False,
            "account_context": account_context,
        }

    def query(
        self,
        question: str,
        limit: int = 10,
        account_context: str = None,
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Process a natural language query.

        Args:
            question:             Natural language question
            limit:                Max results to return
            account_context:      Optional account name to scope the query to one account
            conversation_history: Optional list of previous messages for context

        Returns:
            Dict with answer, SQL, data, explanation, and fallback_used flag
        """
        start_time = time.time()

        # Check if this is a greeting
        if self._is_greeting(question):
            return self._get_greeting_response(question, account_context)

        # Build conversation context for SQL generation
        conversation_context = ""
        if conversation_history:
            recent = conversation_history[-6:]  # Last 3 exchanges
            context_parts = []
            for msg in recent:
                # Handle both dict and Pydantic model objects
                if hasattr(msg, 'role'):
                    # Pydantic model
                    role = msg.role
                    content = msg.content
                else:
                    # Dictionary
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                # Truncate long messages
                if len(content) > 500:
                    content = content[:500] + "..."
                context_parts.append(f"{role.upper()}: {content}")
            conversation_context = "\n".join(context_parts)

        # Scope question to account if context provided
        scoped_question = question
        if account_context:
            scoped_question = f"{question} (Only for account: {account_context})"

        # Step 1: Classify intent early — drives routing for all fallback tiers
        intent = self._classify_question_intent(scoped_question)
        print(f"  🧭 Question intent: {intent}")

        # Step 2: Try Gold layer first — always (pre-aggregated, fastest)
        all_data, sql_queries, fallback_used = self._query_with_fallback(
            scoped_question, limit, account_context, conversation_context
        )

        enrichment_triggered = False
        vector_used = False
        vector_chunks = []

        if intent == "narrative":
            # NARRATIVE path:
            # Always run vector search — even if Gold/Silver returned structured rows.
            # Narrative questions need document prose, not just extracted fields.
            if self.vector_store.is_available():
                vector_chunks = self._try_vector_search(scoped_question, account_context)
                if vector_chunks:
                    vector_used = True
                    print(f"  🔍 Vector search: {len(vector_chunks)} chunk(s) above threshold")
                else:
                    print("  ⚠️ Vector search: no chunks above score threshold")

            # If vector returned nothing and SQL also empty, try Bronze enrichment as safety net
            if not vector_chunks and not all_data:
                print("  ↩️ Vector empty, trying Silver/Bronze as safety net...")
                enrichment_result = self._try_bronze_enrichment(
                    scoped_question, limit, account_context, conversation_context
                )
                if enrichment_result is not None:
                    all_data, sql_queries, fallback_used = enrichment_result
                    enrichment_triggered = True

        else:
            # METRIC/STRUCTURED path:
            # SQL is the right source. Vector only as absolute last resort.
            if not all_data:
                enrichment_result = self._try_bronze_enrichment(
                    scoped_question, limit, account_context, conversation_context
                )
                if enrichment_result is not None:
                    all_data, sql_queries, fallback_used = enrichment_result
                    enrichment_triggered = True

            # If SQL returned nothing at all, try vector as last resort
            if not all_data and self.vector_store.is_available():
                print("  ↩️ SQL empty, trying Vector as last resort...")
                vector_chunks = self._try_vector_search(scoped_question, account_context)
                if vector_chunks:
                    vector_used = True
                    print(f"  🔍 Vector (last resort): {len(vector_chunks)} chunk(s) found")

        # Step 3: Synthesize answer
        # Narrative with vector chunks → synthesize from document text (primary)
        # Metric / no vector → synthesize from SQL rows as usual
        if vector_chunks:
            answer, explanation = self._synthesize_from_vector(
                scoped_question, vector_chunks, conversation_history
            )
            # Clear SQL fields — vector is the answer source, SQL rows would confuse the UI
            all_data = []
            sql_queries = []
        else:
            answer, explanation = self._synthesize_answer(
                scoped_question, all_data, sql_queries, conversation_history
            )

        execution_time = (time.time() - start_time) * 1000

        # Step 3: If Silver fallback occurred, fire GoldSchemaAgent in background
        # This analyzes the fallback and proposes new Gold tables/columns
        if fallback_used and all_data:
            agent = GoldSchemaAgent(self.db)
            agent.analyze_fallback(
                question=scoped_question,
                silver_data=all_data,
                silver_sql=sql_queries,
                execution_time_ms=execution_time
            )

        return {
            "status": "success",
            "answer": answer,
            "sql_queries": sql_queries,
            "data": all_data,
            "explanation": explanation,
            "row_count": len(all_data),
            "execution_time_ms": execution_time,
            "fallback_used": fallback_used,
            "enrichment_triggered": enrichment_triggered,
            "vector_used": vector_used,
            "account_context": account_context,
        }

    def _classify_question_intent(self, question: str) -> str:
        """
        Classify whether a question needs structured SQL data or narrative document content.

        Returns:
            "narrative"  → route to Vector search first  (what was said, discussed, mentioned)
            "metric"     → route to Silver SQL first      (counts, values, stages, dates)

        This is purely rule-based — zero LLM calls. Fast and deterministic.
        The rules are intentionally generous toward "narrative" because false positives
        (sending a metric question to vector) are safer than the reverse.
        """
        q = question.lower().strip()

        # Strong narrative signals — these are almost always document/transcript questions
        narrative_keywords = [
            # What was said / discussed
            "what did", "what was said", "what was discussed", "what was mentioned",
            "what were they", "what happened", "what came up",
            # Summarize / describe
            "summarize", "summary of", "describe", "tell me about", "explain",
            "key points", "action items", "next steps", "follow up",
            # Meeting / transcript specific
            "meeting", "transcript", "call", "conversation", "discussion",
            "attendees", "who attended", "who was in",
            # Sentiment / tone
            "how did", "how was the", "how did they", "tone", "reaction",
            "excited", "hesitant", "concerned", "positive about", "negative about",
            # Specific content retrieval
            "mentioned", "talked about", "said about", "raised", "brought up",
            "according to", "notes", "quote",
            # Competitor / intel
            "competitor", "competitive", "intel", "mentioned aws", "mentioned azure",
            "mentioned salesforce", "mentioned oracle",
        ]

        # Strong metric signals — these need SQL aggregation
        metric_keywords = [
            "how many", "how much", "total", "count", "sum", "average", "avg",
            "revenue", "pipeline value", "deal value", "number of",
            "list all", "show all", "show me all",
            "which accounts", "which deals", "which stage",
            "top ", "rank", "highest", "lowest",
            "closing soon", "close date", "probability",
            "open deals", "won deals", "lost deals",
            "at risk", "no contact",
            # TF-specific dimensions
            "vertical", "horizontal", "salesperson", "engagement model",
            "ai influenced", "ai-influenced", "ai influence",
            "onshore", "offshore", "opportunity stage",
            "new business", "existing customer", "renewal",
            "p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10",
            "mortgage", "banking", "capital market", "higher education", "payments",
            "win rate", "conversion", "performance",
            # New gold table keywords
            "win loss", "win/loss", "loss rate", "lost deals",
            "velocity", "cycle time", "days in stage", "speed",
            "geography mix", "onshore vs", "offshore vs",
            "lead source", "referral", "inbound", "cold outreach",
            "stale", "stuck", "no update", "inactive deal",
        ]

        narrative_score = sum(1 for kw in narrative_keywords if kw in q)
        metric_score = sum(1 for kw in metric_keywords if kw in q)

        # Narrative wins if it has any signal and metric doesn't dominate
        if narrative_score > 0 and narrative_score >= metric_score:
            return "narrative"

        return "metric"

    def _try_vector_search(
        self,
        question: str,
        account_context: str = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Semantic search over Pinecone-indexed unstructured documents.

        Args:
            question:        The user's question (already scoped if needed)
            account_context: Optional account name filter
            top_k:           Number of chunks to retrieve

        Returns:
            List of chunk dicts (text, filename, account_name, score) or []
        """
        try:
            results = self.vector_store.search(
                query=question,
                account_name=account_context,
                top_k=top_k,
            )
            if results:
                scores = [round(r.get('score', 0), 3) for r in results]
                print(f"  📊 Vector scores: {scores}")
            # Only return chunks with meaningful similarity (cosine score > 0.20)
            filtered = [r for r in results if r.get("score", 0) > 0.20]
            return filtered
        except Exception as e:
            logger.warning("Vector search error: %s", e)
            return []

    def _synthesize_from_vector(
        self,
        question: str,
        chunks: List[Dict],
        conversation_history: List[Dict[str, str]] = None,
    ) -> Tuple[str, str]:
        """
        Synthesize a markdown answer from Pinecone-retrieved document chunks.
        Called when Gold/Silver/Bronze all returned no SQL data.
        """
        conversation_context = self._build_conversation_context(conversation_history)

        # Build context block from chunks, sorted best-score-first
        sorted_chunks = sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)
        context_parts = []
        for i, chunk in enumerate(sorted_chunks, 1):
            source_label = chunk.get("filename") or chunk.get("source") or "document"
            acct = chunk.get("account_name")
            header = f"[Excerpt {i} from '{source_label}'"
            if acct:
                header += f" — {acct}"
            header += f" | relevance: {chunk.get('score', 0):.2f}]"
            context_parts.append(f"{header}\n{chunk['text']}")

        document_context = "\n\n".join(context_parts)

        prompt = f"""Answer the following sales question using ONLY the document excerpts below.
Format your answer in Markdown for a sales professional.

DOCUMENT EXCERPTS (from meeting notes, transcripts, uploaded files):
{document_context}
"""
        if conversation_context:
            prompt += f"""
CONVERSATION CONTEXT (previous messages):
{conversation_context}
"""
        prompt += f"""
QUESTION: {question}

RULES:
1. Use Markdown — headers (##), bullet lists (- item), **bold** for key values
2. Base your answer ONLY on the document excerpts above
3. Cite the source document name where relevant (e.g. "According to stark_meeting_notes.txt...")
4. Bold company names, monetary values, dates, and deal names
5. If the excerpts don't contain enough information to answer fully, say so clearly
6. NEVER fabricate data not present in the excerpts
7. Keep it concise and scannable

Return JSON with ONLY these two fields:
{{
    "answer": "your markdown answer here",
    "explanation": "Answered from document excerpts via semantic search (Pinecone)"
}}
"""
        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL_FAST,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a business analyst assistant. Answer questions strictly from the provided document excerpts. Format answers in clean Markdown. Return valid JSON with answer and explanation fields only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            result = json.loads(content.strip())
            return result.get("answer", content.strip()), result.get("explanation", "")
        except Exception as e:
            logger.warning("Vector synthesis failed: %s", e)
            fallback = "\n\n".join(f"**{c.get('filename', 'doc')}**: {c['text'][:300]}..." for c in sorted_chunks[:3])
            return fallback, "Answered from document excerpts (synthesis failed, showing raw excerpts)"

    def _query_with_fallback(
        self,
        question: str,
        limit: int,
        account_context: str = None,
        conversation_context: str = ""
    ):
        """
        Try Gold marts first. If Gold returns 0 rows, fall back to Silver entity tables.
        Returns: (data, sql_queries, fallback_used)
        fallback_used = True  → Silver tables were queried
        fallback_used = False → Gold tables were queried
        """
        # Attempt 1: Gold-aware SQL (with conversation context)
        sql_queries = self._generate_sql(question, limit, conversation_context)
        all_data = self._execute_queries(sql_queries)

        # Check if GPT actually used Gold tables
        used_gold = any("gold." in q.lower() for q in sql_queries)

        if all_data and used_gold:
            # Gold tables answered the question
            return all_data, sql_queries, False

        if all_data and not used_gold:
            # GPT went straight to Silver on first attempt — still a "fallback" from Gold's perspective
            print("  ℹ️ GPT queried Silver directly on first attempt (no Gold tables used)")
            return all_data, sql_queries, True

        # Attempt 2: Gold returned 0 rows — force Silver explicitly
        print("  ⚠️ Gold returned 0 rows, falling back to Silver...")
        fallback_question = f"{question} [Use silver.fact_* and silver.dim_* tables only, not gold.*]"
        fallback_queries = self._generate_sql(fallback_question, limit, conversation_context)
        fallback_data = self._execute_queries(fallback_queries)

        return fallback_data, fallback_queries, True

    def _try_bronze_enrichment(
        self,
        question: str,
        limit: int,
        account_context: str = None,
        conversation_context: str = ""
    ):
        """
        Attempt to fill Silver from Bronze raw data, then re-run the query.

        Returns:
            (data, sql_queries, fallback_used) tuple if enrichment produced results,
            None if enrichment was not possible or yielded no new data.
        """
        try:
            print("  🔎 No data from Gold/Silver — attempting Bronze enrichment...")
            enrichment = BronzeEnrichmentService(self.db)
            enriched_count = enrichment.enrich(question, account_context)

            if enriched_count == 0:
                logger.info("Bronze enrichment produced no new Silver records")
                return None

            print(f"  🔄 Bronze enrichment added {enriched_count} record(s) to Silver — re-running query...")
            data, queries, fb = self._query_with_fallback(
                question, limit, account_context, conversation_context
            )
            if data:
                return data, queries, fb

            return None
        except Exception as e:
            logger.warning("Bronze enrichment error: %s", e)
            return None

    def _execute_queries(self, sql_queries: List[str]) -> List[Dict]:
        """Execute a list of SQL queries and return combined results."""
        all_data = []
        for sql in sql_queries:
            try:
                result = self.db.execute(text(sql))
                rows = result.fetchall()
                columns = result.keys()
                data = [dict(zip(columns, row)) for row in rows]
                all_data.extend(data)
            except Exception as e:
                print(f"⚠️ SQL execution error: {e}")
                print(f"   Query: {sql}")
                self.db.rollback()  # rollback failed query so session stays usable
        return all_data
    
    def _generate_sql(self, question: str, limit: int, conversation_context: str = "") -> List[str]:
        """Generate SQL queries from natural language question using dynamic schema introspection."""

        # Build prompt with live schema from database
        prompt = build_dynamic_prompt(self.db, question, limit, conversation_context)
        
        # Cache schema for reuse in same session (optional optimization)
        # self._schema_cache = getattr(self, '_schema_cache', None)

        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a SQL expert. Generate PostgreSQL queries from natural language. Always return valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )
        
        raw = response.choices[0].message.content
        if not raw or not raw.strip():
            print("⚠️ GPT returned empty response for SQL generation")
            return []

        content = raw.strip()

        # Remove markdown if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()
        if not content:
            print("⚠️ GPT response was only markdown fences with no body")
            return []

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"⚠️ GPT returned invalid JSON: {e}")
            print(f"   Raw content: {content[:200]}")
            return []

        return result.get("sql_queries", [])
    
    def _build_conversation_context(self, conversation_history: List[Dict[str, str]] = None, max_messages: int = 6) -> str:
        """Build a text representation of recent conversation history."""
        if not conversation_history:
            return ""
        recent_history = conversation_history[-max_messages:]
        context_lines = []
        for msg in recent_history:
            if hasattr(msg, 'role'):
                role = msg.role
                content = msg.content
            else:
                role = msg.get("role", "user")
                content = msg.get("content", "")
            context_lines.append(f"{role.upper()}: {content}")
        return "\n".join(context_lines)

    def _synthesize_from_context(
        self,
        question: str,
        conversation_context: str
    ) -> Tuple[str, str]:
        """Answer a question purely from conversation history (no DB data)."""
        prompt = f"""Answer the user's question using ONLY the conversation context below. Format your answer in Markdown for a sales professional.

CONVERSATION CONTEXT (previous messages):
{conversation_context}

CURRENT QUESTION: {question}

RULES:
1. Use Markdown formatting — headers (##), bullet lists (- item), **bold** for key values
2. Answer based on what was discussed in the conversation (e.g. file overviews, previous answers)
3. If the question is about an uploaded file, use the file overview from the conversation to answer
4. Bold key names, dates, and important details
5. Keep it concise and scannable
6. NEVER say "no data found" — the answer IS in the conversation context
7. If you truly cannot find relevant info in the context, say you don't have enough information and suggest what to ask

Return JSON with ONLY these two fields:
{{
    "answer": "your markdown answer here",
    "explanation": "Answered from conversation context (file overview / prior messages)"
}}
"""
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL_FAST,
            messages=[
                {
                    "role": "system",
                    "content": "You are a business analyst assistant. Answer questions using the conversation context provided. Format answers in clean Markdown with headers, bold text, and bullet lists. Return valid JSON with answer and explanation fields only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        try:
            result = json.loads(content.strip())
            return result.get("answer", content.strip()), result.get("explanation", "")
        except json.JSONDecodeError:
            return content.strip(), "Answered from conversation context"

    def _synthesize_answer(
        self,
        question: str,
        data: List[Dict],
        sql_queries: List[str],
        conversation_history: List[Dict[str, str]] = None
    ) -> Tuple[str, str]:
        """Synthesize a human-readable answer from query results with conversation context"""

        conversation_context = self._build_conversation_context(conversation_history)

        if not data:
            if conversation_context:
                print("  💬 No DB data, answering from conversation context...")
                return self._synthesize_from_context(question, conversation_context)
            return "No data found matching your query.", "The database returned no results for the generated SQL queries."

        # Prepare data summary for AI
        data_summary = json.dumps(data[:20], indent=2, default=str)  # Limit to first 20 rows

        prompt = f"""Answer this business question using the data below. Format your answer in Markdown for a sales professional."""

        # Add conversation context if available
        if conversation_context:
            prompt += f"""

CONVERSATION CONTEXT (previous messages):
{conversation_context}
"""

        prompt += f"""
CURRENT QUESTION: {question}

DATA:
{data_summary}

Total rows: {len(data)}

RULES:
1. Use Markdown formatting — headers (##), bullet lists (- item), **bold** for key values
2. Start with a one-line summary, then break down the details
3. Use bullet points for lists of items (deals, contacts, accounts)
4. Bold company names, deal values, and stage names like **Lenovo**, **$120,000**, **Negotiation**
5. If there are multiple items, group them logically with a ## heading per group
6. Keep it concise and scannable — a sales manager should be able to read it in 10 seconds
7. NEVER return raw JSON or code blocks in the answer
8. If the question references previous context (like "what about them", "tell me more", "who else"), use the conversation context to understand what the user is asking about

Return JSON with ONLY these two fields:
{{
    "answer": "## Summary\\n\\nThere are **2 active deals** in the pipeline.\\n\\n## Deals\\n\\n- **Acme Corp** — $500K — *Negotiation* — Contact: Jane Smith\\n- **TechStart Inc** — $750K — *Proposal* — Contact: Bob Wilson",
    "explanation": "One sentence about which tables/data you used"
}}
"""
        
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL_FAST,
            messages=[
                {
                    "role": "system",
                    "content": "You are a business analyst assistant. Format answers in clean Markdown with headers, bold text, and bullet lists. Never return raw JSON or code in the answer field. Return valid JSON with answer and explanation fields only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove markdown if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        try:
            result = json.loads(content.strip())
            return result.get("answer", content.strip()), result.get("explanation", "")
        except json.JSONDecodeError:
            # AI didn't return JSON - use raw text as answer
            print(f"⚠️ Synthesis returned non-JSON, using raw text")
            return content.strip(), ""

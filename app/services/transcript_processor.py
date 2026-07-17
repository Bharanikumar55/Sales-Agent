"""Transcript Processor - Converts raw meeting transcripts to structured data.

Two extraction modes:
  1. AI-powered (GPT-4) — rich extraction with full NLP
  2. Fallback (regex/heuristics) — works offline when API is unreachable
"""
import json
import re
import time
from typing import Dict, Any, List
from openai import OpenAI
from app.config import settings


class TranscriptProcessor:
    """
    Processes raw meeting transcripts into structured data.
    Falls back to regex-based extraction if the AI API is unreachable.
    """
    
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=60.0,          # 60 second timeout (default is 10)
            max_retries=2,         # retry twice on transient errors
        )
    
    def process_raw_transcript(self, raw_transcript: str, metadata: Dict = None) -> Dict[str, Any]:
        """
        Convert raw transcript text into structured data.
        Tries AI extraction first; falls back to regex if API fails.
        """
        # Try AI extraction first
        try:
            result = self._extract_with_ai(raw_transcript)
            print("🤖 AI extraction succeeded")
        except Exception as e:
            print(f"⚠️ AI extraction failed ({type(e).__name__}: {e}). Using fallback extractor.")
            result = self._extract_with_fallback(raw_transcript)
            print("🔧 Fallback extraction succeeded")
        
        # Merge metadata
        if metadata:
            for key, value in metadata.items():
                if key not in result:
                    result[key] = value
        
        return result
    
    def _extract_with_ai(self, raw_transcript: str) -> Dict[str, Any]:
        """AI-powered extraction using GPT-4"""
        prompt = f"""
Analyze the following text. It could be a formal meeting transcript, casual notes,
user-uploaded info, or any free-form business text. Extract whatever structured
information you can find.

Text:
{raw_transcript}

Extract and return JSON with these fields (use null if not found, never use "Unknown"):
1. account_name - Company or organization name (e.g. "Acer", "Lenovo", "Infosys")
2. industry - Industry sector (e.g. "Information Technology", "Healthcare", "Manufacturing")
3. geography - HQ location or primary region (e.g. "Taiwan", "North America", "India")
4. employee_count - Total number of employees for the whole company, only if explicitly mentioned as the total headcount (e.g. 75000)
5. annual_revenue - Annual revenue as a number in USD if mentioned (e.g. 9000000000 for $9B)
6. website - Company website if mentioned
7. attendees - List of meeting participants with roles (for transcripts/meeting notes)
8. contacts - Named contacts explicitly listed in the document (e.g. "Primary Contact: Michael Johnson, Role: VP of Cloud Strategy"). Include anyone listed under Primary Contact, Key Contact, Account Manager, Sales Rep, etc.
9. topics - Main topics discussed (3-5)
10. sentiment - Overall sentiment (Positive/Neutral/Negative)
11. key_points - Important facts, decisions, numbers, budget mentions
12. action_items - Tasks with owners and deadlines if mentioned
13. competitive_intel - Competitors mentioned and context
14. deal_signals - Buying intent, timeline, budget confirmation
15. duration_minutes - Estimated meeting length from timestamps (0 if not a meeting)
16. deal_name - Name/title of the deal or project (e.g. "Hybrid Cloud Optimization")
17. deal_value - Numeric deal value in dollars if mentioned (e.g. 120000 for $120,000 — numbers only, no $ sign)
18. deal_stage - Current stage: one of Discovery, Proposal, Negotiation, Closed Won, Closed Lost (infer from context)
19. close_date - Expected close date if mentioned (ISO format YYYY-MM-DD or text like "Q2 2025")
20. primary_contact - Name of the main contact person for the deal
21. interaction_date - The date of the last meeting, call, email or any recent activity mentioned (ISO format YYYY-MM-DD). Look for fields like "Date:", "Last Meeting:", "Last Interaction:", "Date of meeting:". Return YYYY-MM-DD format.
22. interaction_type - Type of the last interaction: one of Meeting, Call, Email, Demo, Follow-up

Return ONLY valid JSON, no markdown, no explanation:
{{
    "account_name": null,
    "industry": null,
    "geography": null,
    "employee_count": null,
    "annual_revenue": null,
    "website": null,
    "attendees": [{{"name": "Person", "role": "Title", "company": "Comp"}}],
    "contacts": [{{"name": "Person", "role": "Title", "department": "Dept", "email": "", "phone": ""}}],
    "topics": ["Topic1", "Topic2"],
    "sentiment": "Positive",
    "key_points": ["Point 1", "Point 2"],
    "action_items": [{{"item": "Task", "owner": "Person", "due_date": "Date"}}],
    "competitive_intel": {{"competitors_mentioned": [], "our_strengths": [], "concerns": []}},
    "deal_signals": {{"buying_intent": "High", "decision_timeframe": "", "budget_confirmed": false, "decision_maker_engaged": false}},
    "duration_minutes": 0,
    "deal_name": null,
    "deal_value": null,
    "deal_stage": null,
    "close_date": null,
    "primary_contact": null,
    "interaction_date": null,
    "interaction_type": null
}}
"""
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You extract structured business information from any text. Always return ONLY valid JSON. No markdown code fences. No explanation. Just the JSON object."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Try to find JSON object if there's extra text around it
        if not content.startswith("{"):
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                content = content[start:end]
        
        return json.loads(content)
    
    def _extract_with_fallback(self, raw_transcript: str) -> Dict[str, Any]:
        """
        Regex/heuristic-based extraction. Works completely offline.
        Not as accurate as AI, but reliable and instant.
        """
        text = raw_transcript
        
        # --- Extract participants ---
        # Pattern: "[HH:MM:SS] Name:" or "Participants: Name1, Name2"
        speaker_pattern = re.compile(r'\[\d{1,2}:\d{2}(?::\d{2})?\]\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*:')
        speakers = list(set(speaker_pattern.findall(text)))
        
        participant_line = re.search(r'[Pp]articipants?\s*:\s*(.+)', text)
        if participant_line:
            names = [n.strip() for n in participant_line.group(1).split(',')]
            for name in names:
                clean = name.strip()
                if clean and clean not in speakers:
                    speakers.append(clean)
        
        attendees = [{"name": s, "role": "Participant", "company": ""} for s in speakers]

        # Define text_lower early — used by industry + all subsequent extractions
        text_lower = text.lower()
        
        # --- Extract company name ---
        # Patterns: formal ("from Google") and casual ("about Google", "Google info")
        company_patterns = [
            r'(?:from|at|with)\s+([A-Z][A-Za-z\s]+(?:Industries|Corp|Inc|Ltd|Tech|Solutions|Systems|Group|Company))',
            r'(?:about|regarding|for|on|re:|info\s+(?:about|on|for))\s+([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+){0,3})\b',
            r'(?:from|at|with)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b',
            r'([A-Z][A-Za-z]+\s+(?:Industries|Corp|Inc|Ltd|Tech|Solutions|Systems|Group))',
            r'(?:client|customer|company|account|organization)\s*(?:is|:|-|–)?\s*([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+){0,3})\b',
            r'\b([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+){0,2})\s+(?:is a|is an|are a|are an)\s+(?:technology|tech|software|finance|healthcare|consulting|manufacturing)',
        ]
        account_name = "Unknown"
        for pattern in company_patterns:
            match = re.search(pattern, text)
            if match:
                account_name = match.group(1).strip()
                break
        
        # --- Extract industry ---
        # First try explicit label in company info docs: "Industry: Computer Hardware & Electronics"
        industry_label_match = re.search(r'[Ii]ndustry\s*[:\-]\s*([^\n]+)', text)
        industry = industry_label_match.group(1).strip() if industry_label_match else None

        if not industry:
            industry_keywords = {
                'Information Technology & Hardware': ['computer hardware', 'hardware and electronics', 'pc manufacturer', 'laptop', 'semiconductor'],
                'Information Technology': ['information technology', 'technology', 'tech', 'software', 'saas', 'cloud computing', 'ai ', 'artificial intelligence', 'it services'],
                'Healthcare': ['healthcare', 'health care', 'medical', 'pharma', 'pharmaceutical', 'biotech'],
                'Finance': ['finance', 'financial', 'banking', 'insurance', 'fintech'],
                'Manufacturing': ['manufacturing', 'industrial', 'factory', 'production'],
                'Retail': ['retail', 'e-commerce', 'ecommerce', 'shopping'],
                'Energy': ['energy', 'oil', 'gas', 'petroleum', 'renewable'],
                'Automotive': ['automotive', 'automobile', 'vehicle', 'car'],
                'Consulting': ['consulting', 'advisory', 'professional services'],
                'Telecommunications': ['telecom', 'telecommunications', 'wireless', 'mobile network'],
                'Education': ['education', 'edtech', 'university', 'academic'],
            }
            for ind_name, keywords in industry_keywords.items():
                for kw in keywords:
                    if kw in text_lower:
                        industry = ind_name
                        break
                if industry:
                    break
        
        # --- Extract geography ---
        geo_match = re.search(r'(?:headquartered|hq|based|located)\s+in\s+([A-Z][A-Za-z\s,]+?)(?:\.|,|\n|with)', text, re.IGNORECASE)
        geography = geo_match.group(1).strip().rstrip(',') if geo_match else None

        # --- Extract employee count ---
        emp_match = re.search(r'(\d[\d,]+)\s*\+?\s*(?:employees|staff|workforce|people)', text, re.IGNORECASE)
        employee_count = emp_match.group(1).replace(',', '') if emp_match else None

        # --- Extract annual revenue ---
        rev_match = re.search(r'(?:annual revenue|revenue)[^\$\d]*\$?\s*([\d,.]+)\s*(billion|million|B|M)\b', text, re.IGNORECASE)
        annual_revenue = None
        if rev_match:
            val = float(rev_match.group(1).replace(',', ''))
            unit = rev_match.group(2).lower()
            if unit in ('billion', 'b'):
                annual_revenue = str(int(val * 1_000_000_000))
            elif unit in ('million', 'm'):
                annual_revenue = str(int(val * 1_000_000))

        # --- Extract budget/monetary values ---
        money_pattern = re.compile(r'\$[\d,.]+\s*(?:million|billion|M|B|K)?|\d+(?:\.\d+)?\s*(?:million|billion)\s*(?:dollars?)?', re.IGNORECASE)
        money_mentions = money_pattern.findall(text)
        
        # --- Extract topics (simple: sentences with key business words) ---
        topic_words = ['budget', 'timeline', 'deadline', 'pricing', 'security', 'compliance',
                       'integration', 'migration', 'support', 'license', 'contract', 'demo',
                       'proposal', 'requirements', 'features', 'performance', 'scalability',
                       'deployment', 'training', 'onboarding', 'implementation']
        topics = []
        for word in topic_words:
            if word.lower() in text.lower():
                topics.append(word.capitalize())
        if not topics:
            topics = ["General Discussion"]
        topics = topics[:5]
        
        # --- Key points (lines with important content) ---
        key_points = []
        for money in money_mentions:
            key_points.append(f"Budget/amount mentioned: {money}")
        
        # Extract sentences with action verbs
        action_sentences = re.findall(r'[^.!?\n]*(?:need|want|require|plan|decide|agree|confirm|approve|move forward|ready)[^.!?\n]*[.!?]', text, re.IGNORECASE)
        for s in action_sentences[:5]:
            key_points.append(s.strip())
        
        if not key_points:
            key_points = ["Meeting recorded - details require manual review"]
        
        # --- Sentiment (basic keyword scoring) ---
        positive_words = ['great', 'excellent', 'happy', 'pleased', 'good', 'excited', 'love', 'wonderful',
                          'forward', 'agree', 'ready', 'perfect', 'thanks', 'appreciate', 'fantastic']
        negative_words = ['concern', 'issue', 'problem', 'worry', 'delay', 'expensive', 'difficult',
                          'frustrated', 'disappointed', 'unfortunately', 'risk', 'fail']
        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)
        
        if pos_count > neg_count + 2:
            sentiment = "Positive"
        elif neg_count > pos_count + 2:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
        
        # --- Duration from timestamps ---
        timestamps = re.findall(r'\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]', text)
        duration_minutes = 10  # default
        if timestamps:
            try:
                last = timestamps[-1]
                first = timestamps[0]
                last_min = int(last[0]) * 60 + int(last[1])
                first_min = int(first[0]) * 60 + int(first[1])
                duration_minutes = max(last_min - first_min, 1)
            except (ValueError, IndexError):
                pass
        
        # --- Competitors ---
        competitor_keywords = ['AWS', 'Azure', 'Google Cloud', 'GCP', 'Salesforce', 'Oracle',
                               'SAP', 'Microsoft', 'IBM', 'Workday', 'ServiceNow', 'Snowflake',
                               'Databricks', 'HubSpot', 'Zendesk', 'Slack', 'Zoom']
        competitors_found = [c for c in competitor_keywords if c.lower() in text_lower]
        
        # --- Deal signals ---
        budget_confirmed = bool(money_mentions)
        buying_intent = "High" if any(w in text_lower for w in ['ready', 'move forward', 'approve', 'sign']) else \
                        "Medium" if any(w in text_lower for w in ['interested', 'evaluate', 'consider']) else "Low"
        
        # --- Extract deal fields from fallback ---
        deal_name = ""
        deal_value = ""
        deal_stage = ""
        close_date = ""
        primary_contact = ""

        # Deal name: look for patterns like "Current Deal: X" or "Deal: X"
        deal_name_match = re.search(r'(?:current deal|deal name|deal|project)\s*[:\-]\s*([^\n]+)', text, re.IGNORECASE)
        if deal_name_match:
            deal_name = deal_name_match.group(1).strip()

        # Deal value: first money mention
        if money_mentions:
            raw_val = money_mentions[0]
            num_match = re.search(r'[\d,.]+', raw_val.replace(',', ''))
            if num_match:
                deal_value = num_match.group(0).replace(',', '')

        # Deal stage: look for stage keywords
        stage_map = [
            (r'\bnegotiat', 'Negotiation'),
            (r'\bproposal|\bproposed', 'Proposal'),
            (r'\bdiscovery|\bqualif', 'Discovery'),
            (r'\bclosed?\s+won', 'Closed Won'),
            (r'\bclosed?\s+lost', 'Closed Lost'),
        ]
        for pattern, stage in stage_map:
            if re.search(pattern, text, re.IGNORECASE):
                deal_stage = stage
                break

        # Close date: look for "Expected Close" or "Q2 2025" style
        close_match = re.search(r'(?:close|closing|expected)\s*(?:date)?\s*[:\-]?\s*([Q][1-4]\s*\d{4}|\d{4}-\d{2}-\d{2}|[A-Z][a-z]+\s+\d{4})', text, re.IGNORECASE)
        if close_match:
            close_date = close_match.group(1).strip()

        # Named contacts from company info docs ("Primary Contact: Name, Role: Title")
        contacts = []
        contact_block_pattern = re.compile(
            r'(?:primary contact|key contact|account manager|sales rep|contact)\s*[:\-]\s*([A-Z][A-Za-z\s]+?)'
            r'(?:[,\n]\s*(?:role|title|position)\s*[:\-]\s*([^\n,]+))?'
            r'(?:[,\n]\s*(?:department|dept|region|division)\s*[:\-]\s*([^\n,]+))?',
            re.IGNORECASE
        )
        for m in contact_block_pattern.finditer(text):
            name = m.group(1).strip().rstrip(',')
            role = m.group(2).strip() if m.group(2) else ""
            dept = m.group(3).strip() if m.group(3) else ""
            if name and len(name.split()) <= 4:  # sanity check — not a full sentence
                contacts.append({"name": name, "role": role, "department": dept, "email": "", "phone": ""})

        # Deduplicate contacts by name
        seen_names = set()
        unique_contacts = []
        for c in contacts:
            if c["name"] not in seen_names:
                seen_names.add(c["name"])
                unique_contacts.append(c)
        contacts = unique_contacts

        # Primary contact: from contacts list first, then attendees
        if contacts:
            primary_contact = contacts[0].get('name', '')
        elif attendees:
            primary_contact = attendees[0].get('name', '')

        return {
            "account_name": account_name,
            "industry": industry,
            "geography": geography,
            "employee_count": employee_count,
            "annual_revenue": annual_revenue,
            "attendees": attendees,
            "contacts": contacts,
            "topics": topics,
            "sentiment": sentiment,
            "key_points": key_points,
            "action_items": [],
            "competitive_intel": {
                "competitors_mentioned": competitors_found,
                "our_strengths": [],
                "concerns": []
            },
            "deal_signals": {
                "buying_intent": buying_intent,
                "decision_timeframe": "Unknown",
                "budget_confirmed": budget_confirmed,
                "decision_maker_engaged": False
            },
            "duration_minutes": duration_minutes,
            "deal_name": deal_name,
            "deal_value": deal_value,
            "deal_stage": deal_stage,
            "close_date": close_date,
            "primary_contact": primary_contact,
            "_extraction_method": "fallback_regex"
        }
    
    def process_batch(self, transcripts: list) -> list:
        """Process multiple transcripts"""
        results = []
        for transcript_data in transcripts:
            raw_text = transcript_data.get("raw_transcript") or transcript_data.get("transcript")
            metadata = {k: v for k, v in transcript_data.items() if k not in ["raw_transcript", "transcript"]}
            structured = self.process_raw_transcript(raw_text, metadata)
            results.append(structured)
        return results

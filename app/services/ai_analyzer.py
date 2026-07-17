"""AI Data Classifier - Uses GPT-4 to classify data into canonical tables"""
import json
from typing import List, Dict, Any
from openai import OpenAI
from app.config import settings
from app.services.canonical_schema import get_schema_summary, CANONICAL_SCHEMA


class AIDataClassifier:
    """
    Classifies incoming data into pre-defined canonical tables using AI.
    Instead of inventing new tables, AI maps data fields to existing columns.
    """
    
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=60.0,
            max_retries=2,
        )
    
    def classify_data(self, data: List[Dict[str, Any]], source_name: str = "unknown") -> Dict[str, Any]:
        """
        Classify data records into canonical tables.
        
        Args:
            data: List of data records
            source_name: Name of data source
        
        Returns:
            Dict with table classifications and mapped records
        """
        sample = data[:3] if len(data) > 3 else data
        schema_summary = get_schema_summary()
        
        prompt = f"""You are a data classifier for a business semantic layer.

Given input data, classify each piece of information into the correct pre-defined table.
Map source field names to the table's column names.

AVAILABLE TABLES:
{schema_summary}

SOURCE: {source_name}

INPUT DATA:
{json.dumps(sample, indent=2)}

RULES:
1. Map EVERY piece of information to the most appropriate table and column
2. One input record can produce rows in MULTIPLE tables
3. Use exact column names from the table definitions above
4. For array fields (like attendees), create one row per item in dim_contact
5. Store the full original record as JSON in "source_data" column for fact tables
6. Set "source" column to "{source_name}"
7. Any fields that don't map to named columns go into "extra_data" as JSON

Return JSON:
{{
    "classifications": [
        {{
            "table": "dim_account",
            "records": [
                {{"name": "Company Name", "industry": "Technology", "source": "{source_name}"}}
            ]
        }},
        {{
            "table": "fact_deals",
            "records": [
                {{"deal_name": "Deal with Company", "deal_value": "1200000", "deal_stage": "Closed Won", "account_name": "Company Name", "source": "{source_name}", "source_data": "<full original record as JSON string>"}}
            ]
        }}
    ],
    "summary": "Brief description of what was classified"
}}

IMPORTANT: Return ONLY valid JSON. Use null for missing fields. All values must be strings."""
        
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise data classifier. Map business data to pre-defined tables. Always respond with valid JSON only. All field values must be strings."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )
        
        result = json.loads(response.choices[0].message.content)
        result["source"] = source_name
        result["records_analyzed"] = len(data)
        
        return result
    
    def classify_transcript_data(self, processed_data: List[Dict[str, Any]], source_name: str = "unknown") -> Dict[str, Any]:
        """
        Classify NLP-processed transcript data into canonical tables.
        This is deterministic (no AI call needed) since we know the NLP output structure.
        
        Args:
            processed_data: NLP-processed transcript records
            source_name: Data source name
        
        Returns:
            Dict with table classifications
        """
        classifications = {}
        
        for record in processed_data:
            # dim_account
            if record.get("account_name"):
                acc_record = {
                    "account_name": record.get("account_name", "Unknown"),
                    "source": source_name,
                }
                if record.get("industry"):
                    acc_record["industry"] = record["industry"]
                if record.get("geography") or record.get("region") or record.get("headquarters"):
                    acc_record["geography"] = record.get("geography") or record.get("region") or record.get("headquarters")
                if record.get("employee_count") or record.get("employees"):
                    acc_record["employee_count"] = str(record.get("employee_count") or record.get("employees"))
                if record.get("annual_revenue") or record.get("revenue"):
                    acc_record["annual_revenue"] = str(record.get("annual_revenue") or record.get("revenue"))
                if record.get("website"):
                    acc_record["website"] = record["website"]
                classifications.setdefault("dim_account", []).append(acc_record)
            
            # dim_contact - one row per attendee (meeting participants)
            for attendee in record.get("attendees", []):
                if isinstance(attendee, dict):
                    classifications.setdefault("dim_contact", []).append({
                        "name": attendee.get("name", "Unknown"),
                        "title": attendee.get("title", ""),
                        "role": attendee.get("role", ""),
                        "account_name": record.get("account_name", ""),
                        "source": source_name,
                    })
                elif isinstance(attendee, str):
                    classifications.setdefault("dim_contact", []).append({
                        "name": attendee,
                        "account_name": record.get("account_name", ""),
                        "source": source_name,
                    })

            # dim_contact - named contacts from company info docs (Primary Contact, Key Contact, etc.)
            for contact in record.get("contacts", []):
                if isinstance(contact, dict) and contact.get("name"):
                    classifications.setdefault("dim_contact", []).append({
                        "name": contact.get("name", ""),
                        "title": contact.get("title", "") or contact.get("role", ""),
                        "role": contact.get("role", ""),
                        "department": contact.get("department", ""),
                        "email": contact.get("email", ""),
                        "phone": contact.get("phone", ""),
                        "account_name": record.get("account_name", ""),
                        "source": source_name,
                    })
            
            # fact_interactions - the main meeting record
            interaction = {
                "interaction_type": record.get("interaction_type", "meeting"),
                "interaction_date": (
                    record.get("interaction_date") or
                    record.get("meeting_date") or
                    record.get("date") or
                    record.get("close_date") or
                    ""
                ),
                "account_name": record.get("account_name", ""),
                "summary": ", ".join(record.get("key_points", [])) if isinstance(record.get("key_points"), list) else str(record.get("key_points", "")),
                "sentiment": record.get("sentiment", ""),
                "duration_minutes": str(record.get("duration_minutes", "")),
                "attendees": json.dumps(record.get("attendees", [])),
                "topics": json.dumps(record.get("topics", [])),
                "key_points": json.dumps(record.get("key_points", [])),
                "action_items": json.dumps(record.get("action_items", [])),
                "competitive_intel": json.dumps(record.get("competitive_intel", {})),
                "deal_signals": json.dumps(record.get("deal_signals", {})),
                "meeting_id": record.get("meeting_id", ""),
                "source": source_name,
                "source_data": json.dumps(record, default=str),
            }
            classifications.setdefault("fact_interactions", []).append(interaction)
            
            # fact_deals - create a deal record if any deal field is present
            deal_name = record.get("deal_name", "")
            deal_value = record.get("deal_value", "")
            deal_stage = record.get("deal_stage", "")
            close_date = record.get("close_date", "")
            primary_contact = record.get("primary_contact", "")

            # Fallback: infer deal_stage from deal_signals if not explicitly extracted
            if not deal_stage:
                ds = record.get("deal_signals", {})
                if isinstance(ds, dict):
                    intent = ds.get("buying_intent", "")
                    if intent == "High":
                        deal_stage = "Negotiation"
                    elif intent == "Medium":
                        deal_stage = "Proposal"
                    elif intent == "Low":
                        deal_stage = "Discovery"

            if deal_name or deal_value or deal_stage:
                # Use account_name as deal_name fallback so pipeline always shows something
                effective_deal_name = deal_name or f"{record.get('account_name', 'Unknown')} Deal"
                classifications.setdefault("fact_deals", []).append({
                    "deal_name": effective_deal_name,
                    "deal_value": str(deal_value) if deal_value else "",
                    "deal_stage": deal_stage,
                    "close_date": str(close_date) if close_date else "",
                    "account_name": record.get("account_name", ""),
                    "contact_name": primary_contact,
                    "source": source_name,
                    "source_data": json.dumps(record.get("deal_signals", {}), default=str),
                })

            # fact_insights - extract deal signals as insights
            deal_signals = record.get("deal_signals", {})
            if isinstance(deal_signals, dict):
                buying_intent = deal_signals.get("buying_intent", "Unknown")
                if buying_intent and buying_intent != "Unknown":
                    budget = deal_signals.get("budget_confirmed", False)
                    timeframe = deal_signals.get("decision_timeframe", "")
                    dm_engaged = deal_signals.get("decision_maker_engaged", False)

                    content_parts = [f"Buying intent is {buying_intent}."]
                    if budget:
                        content_parts.append("Budget has been confirmed by the prospect.")
                    else:
                        content_parts.append("Budget not yet confirmed.")
                    if timeframe and timeframe != "Unknown":
                        content_parts.append(f"Decision timeframe: {timeframe}.")
                    if dm_engaged:
                        content_parts.append("Decision maker is actively engaged in discussions.")

                    key_points = record.get("key_points", [])
                    if isinstance(key_points, list) and key_points:
                        relevant = [kp for kp in key_points[:3] if isinstance(kp, str)]
                        if relevant:
                            content_parts.append("Key signals: " + "; ".join(relevant) + ".")

                    classifications.setdefault("fact_insights", []).append({
                        "insight_type": "deal_signal",
                        "content": " ".join(content_parts),
                        "confidence": "0.9" if buying_intent == "High" else "0.7" if buying_intent == "Medium" else "0.5",
                        "account_name": record.get("account_name", ""),
                        "insight_date": record.get("meeting_date") or record.get("interaction_date", ""),
                        "source": source_name,
                        "source_data": json.dumps(deal_signals),
                    })
            
            # fact_insights - competitive intel
            comp_intel = record.get("competitive_intel", {})
            if isinstance(comp_intel, dict):
                competitors = comp_intel.get("competitors_mentioned", [])
                if competitors:
                    comp_list = ', '.join(competitors) if isinstance(competitors, list) else str(competitors)
                    content_parts = [f"Competitors mentioned in conversation: {comp_list}."]

                    strengths = comp_intel.get("our_strengths", [])
                    if isinstance(strengths, list) and strengths:
                        content_parts.append("Our advantages: " + "; ".join(str(s) for s in strengths[:3]) + ".")

                    concerns = comp_intel.get("concerns", [])
                    if isinstance(concerns, list) and concerns:
                        content_parts.append("Concerns raised: " + "; ".join(str(c) for c in concerns[:3]) + ".")

                    classifications.setdefault("fact_insights", []).append({
                        "insight_type": "competitive",
                        "content": " ".join(content_parts),
                        "confidence": "0.8",
                        "account_name": record.get("account_name", ""),
                        "insight_date": record.get("meeting_date") or record.get("interaction_date", ""),
                        "source": source_name,
                        "source_data": json.dumps(comp_intel),
                    })

            # fact_insights - action items (if present, log as a follow-up insight)
            action_items = record.get("action_items", [])
            if isinstance(action_items, list) and action_items:
                items_text = []
                for ai_item in action_items[:5]:
                    if isinstance(ai_item, dict):
                        task = ai_item.get("item", ai_item.get("task", ""))
                        owner = ai_item.get("owner", "")
                        due = ai_item.get("due_date", "")
                        part = task
                        if owner:
                            part += f" (Owner: {owner})"
                        if due:
                            part += f" [Due: {due}]"
                        items_text.append(part)
                    elif isinstance(ai_item, str):
                        items_text.append(ai_item)

                if items_text:
                    classifications.setdefault("fact_insights", []).append({
                        "insight_type": "action_items",
                        "content": "Follow-up actions from meeting: " + "; ".join(items_text) + ".",
                        "confidence": "0.9",
                        "account_name": record.get("account_name", ""),
                        "insight_date": record.get("meeting_date") or record.get("interaction_date", ""),
                        "source": source_name,
                        "source_data": json.dumps(action_items, default=str),
                    })
        
        # Format as standard classification result
        result_classifications = []
        for table_name, records in classifications.items():
            result_classifications.append({
                "table": table_name,
                "records": records
            })
        
        return {
            "classifications": result_classifications,
            "summary": f"Classified {len(processed_data)} transcript(s) into {len(classifications)} tables",
            "source": source_name,
            "records_analyzed": len(processed_data),
        }
    
    def detect_data_type(self, sample_data: List[Dict]) -> str:
        """
        Detect what type of data this is.
        
        Returns:
            "raw_transcript" - Raw meeting text that needs NLP processing
            "structured_data" - Regular structured data (CRM, ERP, etc.)
        """
        if not sample_data:
            return "structured_data"
        
        first_record = sample_data[0]
        
        # Check for raw transcript field
        if "transcript" in first_record or "raw_transcript" in first_record:
            text_field = first_record.get("transcript") or first_record.get("raw_transcript")
            if isinstance(text_field, str) and len(text_field) > 50:
                return "raw_transcript"
        
        return "structured_data"

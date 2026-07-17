"""
File Overview Service - Generates AI-powered overviews of uploaded files
"""
import json
from typing import Dict, Any, List
from openai import OpenAI
from app.config import settings


class FileOverviewService:
    """
    Generates brief overviews of uploaded files using AI.
    For text files: provides content summary
    For structured files: provides sample data preview (first few rows)
    """

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=30.0,
            max_retries=1,
        )

    def generate_overview(
        self,
        filename: str,
        data: List[Dict[str, Any]],
        file_type: str,
        max_rows_for_structured: int = 5
    ) -> str:
        """
        Generate an AI overview of the uploaded file.

        Args:
            filename: Name of the uploaded file
            data: Parsed file content
            file_type: Type of file (pdf, csv, xlsx, txt)
            max_rows_for_structured: Max rows to show for CSV/Excel

        Returns:
            A brief overview string
        """
        if not data:
            return "No content could be extracted from this file."

        try:
            if file_type in ["pdf", "txt", "docx"]:
                return self._generate_text_overview(filename, data)
            elif file_type in ["csv", "xlsx"]:
                return self._generate_structured_overview(filename, data, max_rows_for_structured)
            else:
                return f"📄 **{filename}** - File uploaded successfully ({len(data)} records)."
        except Exception as e:
            # Fallback: simple message if AI fails
            return f"📄 **{filename}** - File uploaded successfully with {len(data)} records."

    def _generate_text_overview(self, filename: str, data: List[Dict[str, Any]]) -> str:
        """Generate overview for text-based files (PDF, TXT)."""
        # Extract text content from the first record
        text_content = ""
        for record in data:
            if "raw_transcript" in record:
                text_content = record["raw_transcript"]
                break

        if not text_content:
            return f"📄 **{filename}** - File uploaded successfully ({len(data)} records)."

        # Truncate if too long
        max_chars = 2000
        truncated = len(text_content) > max_chars
        sample_text = text_content[:max_chars] if truncated else text_content

        prompt = f"""You are an AI assistant helping users understand uploaded files. Format your response in clean, scannable Markdown.

Given the following text content from file **{filename}**, provide a well-formatted overview.

CONTENT SAMPLE:
{sample_text}

{'(Content truncated...)' if truncated else ''}

FORMAT YOUR RESPONSE LIKE THIS:
## 📄 **{filename}**

**Quick Summary:**
One sentence describing what this file is about.

**Key Details:**
- **Sender:** Name (if email/document has sender)
- **Recipient:** Name (if email/document has recipient)
- **Subject/Topic:** Main topic
- **Key Numbers:** Any amounts, dates, quantities (bold the numbers)
- **Action Items:** Any deadlines, follow-ups, or requests
- **People Mentioned:** Important names with their roles

**Context:**
1-2 sentences of additional context.

RULES:
- Use **bold** for all names, companies, amounts ($X), and important dates
- Use bullet points (-) for key details
- Keep it scannable — a sales manager should read it in 10 seconds
- Extract the most important business information"""

        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that provides well-formatted, scannable file summaries using Markdown. Bold all important names, numbers, and entities."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=300
            )

            overview = response.choices[0].message.content.strip()
            return overview
        except Exception as e:
            # Fallback
            return f"📄 **{filename}** - Text file uploaded ({len(text_content)} characters)."

    def _generate_structured_overview(
        self,
        filename: str,
        data: List[Dict[str, Any]],
        max_rows: int
    ) -> str:
        """Generate overview for structured files (CSV, Excel) - show first few rows only."""
        if not data:
            return f"📊 **{filename}** - Structured file uploaded but no data found."

        # Get column headers
        headers = list(data[0].keys())

        # Filter out internal/account columns for display
        display_headers = [h for h in headers if h not in ["account_name", "raw_transcript"]]
        if not display_headers:
            display_headers = headers[:10]  # Limit to first 10 columns

        # Sample first few rows
        sample_rows = data[:max_rows]

        # Build preview table
        lines = [f"📊 **{filename}**"]
        lines.append(f"**Total Records:** {len(data)}  |  **Columns:** {len(display_headers)}")
        lines.append("")
        lines.append("**Sample Preview:**")
        lines.append("")

        # Create a simple markdown table preview
        header_line = " | ".join(display_headers[:8])  # Max 8 columns for readability
        lines.append(header_line)
        lines.append("-" * len(header_line))

        for row in sample_rows:
            values = []
            for h in display_headers[:8]:
                val = str(row.get(h, ""))[:30]  # Truncate long values
                values.append(val)
            lines.append(" | ".join(values))

        if len(data) > max_rows:
            lines.append(f"\n_... and {len(data) - max_rows} more rows_")

        return "\n".join(lines)

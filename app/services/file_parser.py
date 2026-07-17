import io
import csv
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

class FileParser:
    """
    Handles parsing for different file formats (PDF, CSV, XLSX, TXT, DOCX).
    Converts them into a standardized List[Dict] for the ingestion engine.
    """

    @staticmethod
    def parse(filename: str, content: bytes) -> List[Dict[str, Any]]:
        filename = filename.lower()
        
        if filename.endswith(".pdf"):
            return FileParser._parse_pdf(content)
        elif filename.endswith(".csv"):
            return FileParser._parse_csv(content)
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            return FileParser._parse_excel(content)
        elif filename.endswith(".txt"):
            return FileParser._parse_txt(content)
        elif filename.endswith(".docx"):
            return FileParser._parse_docx(content)
        
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")

    @staticmethod
    def _parse_pdf(content: bytes) -> List[Dict[str, Any]]:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(content))
            text_content = "\n".join(page.extract_text() or "" for page in reader.pages)
            print(f"  📄 PDF: extracted {len(text_content)} chars")
            return [{"raw_transcript": text_content}]
        except ImportError:
            raise HTTPException(status_code=500, detail="PyPDF2 not installed")

    @staticmethod
    def _parse_csv(content: bytes) -> List[Dict[str, Any]]:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                decoded = content.decode("latin-1")
            except:
                raise HTTPException(status_code=400, detail="Unable to decode CSV file")
        
        reader = csv.DictReader(io.StringIO(decoded))
        return [row for row in reader]

    @staticmethod
    def _parse_excel(content: bytes) -> List[Dict[str, Any]]:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active # Get first sheet
            rows = list(ws.iter_rows(values_only=True))
            
            if not rows:
                return []
                
            headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
            data = []
            for row in rows[1:]:
                record = {}
                for i, val in enumerate(row):
                    if val is not None and i < len(headers):
                        record[headers[i]] = str(val)
                if record:
                    data.append(record)
            wb.close()
            return data
        except ImportError:
            raise HTTPException(status_code=500, detail="openpyxl not installed")

    @staticmethod
    def _parse_txt(content: bytes) -> List[Dict[str, Any]]:
        text_content = content.decode("utf-8")
        return [{"raw_transcript": text_content}]

    @staticmethod
    def _parse_docx(content: bytes) -> List[Dict[str, Any]]:
        try:
            from docx import Document
            doc = Document(io.BytesIO(content))
            text_content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            print(f"  📄 DOCX: extracted {len(text_content)} chars")
            return [{"raw_transcript": text_content}]
        except ImportError:
            raise HTTPException(status_code=500, detail="python-docx not installed")

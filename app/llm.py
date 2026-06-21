import json
import os
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing in .env file")

client = Groq(api_key=GROQ_API_KEY)


def _extract_json(raw_text: str) -> Dict[str, Any]:
    """
    Safely parse JSON returned by the LLM.
    Handles:
    - empty response
    - markdown fenced JSON
    - extra text before/after JSON
    """

    if not raw_text or not raw_text.strip():
        raise ValueError("LLM returned an empty response")

    text = raw_text.strip()

    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"LLM did not return valid JSON. Raw response: {raw_text}")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse extracted JSON. Raw response: {raw_text}") from e


def _chat_json(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """
    Calls Groq API and expects JSON output.
    Groq supports chat completions through the official SDK. 
    """

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content

    print("----- RAW GROQ RESPONSE START -----")
    print(raw_content)
    print("----- RAW GROQ RESPONSE END -----")

    return _extract_json(raw_content)


def analyze_transcript(transcript: str) -> Dict[str, Any]:
    if not transcript or not transcript.strip():
        raise ValueError("Transcript text is empty")

    system_prompt = """
You are an AI-powered Meeting Assistant.

You must return ONLY valid JSON.
Do not include markdown.
Do not include explanation text.
Do not wrap the response in ```json.

Your task is to analyze meeting transcripts and extract:
- meeting summary
- attendees
- action items
- decisions
- risks or concerns
"""

    user_prompt = f"""
Analyze the following meeting transcript.

Return JSON using exactly this structure:

{{
  "title": "",
  "summary": "",
  "attendees": [],
  "action_items": [
    {{
      "owner": "",
      "task": "",
      "deadline": "",
      "status": "pending"
    }}
  ],
  "decisions": [],
  "risks": [],
  "concerns": []
}}

Rules:
- If owner is unknown, use "Unassigned".
- If deadline is unknown, use an empty string.
- Action item status should default to "pending".
- Keep the summary professional and concise.
- Return valid JSON only.

Transcript:
{transcript}
"""

    return _chat_json(system_prompt, user_prompt)


def answer_meeting_question(question: str, context_text: str) -> Dict[str, Any]:
    if not question or not question.strip():
        raise ValueError("Question is empty")

    if not context_text or not context_text.strip():
        raise ValueError("Meeting context is empty")

    system_prompt = """
You are an AI Meeting Assistant answering questions from stored meeting data.

Return ONLY valid JSON.
Do not include markdown or explanation text.
"""

    user_prompt = f"""
Answer the user's question using only the meeting context below.

Return JSON using this structure:

{{
  "question": "",
  "answer": "",
  "supporting_points": []
}}

Question:
{question}

Meeting Context:
{context_text}
"""

    return _chat_json(system_prompt, user_prompt)


def generate_followup_email(
    transcript: str,
    analysis: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not transcript or not transcript.strip():
        raise ValueError("Transcript text is empty")

    analysis_json = json.dumps(analysis or {}, indent=2)

    system_prompt = """
You are an AI Meeting Assistant that writes professional follow-up emails.

Return ONLY valid JSON.
Do not include markdown or explanation text.
"""

    user_prompt = f"""
Generate a professional follow-up email based on this meeting.

Return JSON using this structure:

{{
  "subject": "",
  "body": ""
}}

The email should include:
- short greeting
- meeting summary
- action items with owners
- decisions made
- risks or concerns
- professional closing

Meeting Analysis:
{analysis_json}

Transcript:
{transcript}
"""

    return _chat_json(system_prompt, user_prompt)


def consolidate_meeting_insights(
    meetings_context: str,
    query: str,
) -> Dict[str, Any]:
    if not query or not query.strip():
        raise ValueError("Query is empty.")

    if not meetings_context or not meetings_context.strip():
        raise ValueError("Meetings context is empty.")

    system_prompt = """
You are an AI Meeting Assistant.

You analyze multiple previous meetings and generate consolidated insights.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanation text.
Use only the provided meeting context.
"""

    user_prompt = f"""
Analyze the previous meetings and answer the user query.

Return JSON in this exact structure:

{{
  "query": "",
  "summary": "",
  "previous_discussions": [],
  "planning_points": [],
  "important_decisions": [],
  "pending_action_items": [
    {{
      "owner": "",
      "task": "",
      "meeting_reference": ""
    }}
  ],
  "completed_action_items": [
    {{
      "owner": "",
      "task": "",
      "meeting_reference": ""
    }}
  ],
  "recurring_risks": [],
  "final_next_steps": [],
  "key_themes": []
}}
Query:
{query}

Previous Meetings Context:
{meetings_context}
"""

    return chat_json(system_prompt, user_prompt)

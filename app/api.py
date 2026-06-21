import json
import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def extract_json(raw_text: str) -> Dict[str, Any]:
    if not raw_text or not raw_text.strip():
        raise ValueError("LLM returned an empty response.")

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
        raise ValueError(f"Failed to parse LLM JSON. Raw response: {raw_text}") from e


def chat_json(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing in .env file.")

    try:
        client = Groq(api_key=GROQ_API_KEY)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.1,
            response_format={"type": "json_object"},
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
        )

        raw_content = response.choices[0].message.content

        print("----- RAW GROQ RESPONSE START -----")
        print(raw_content)
        print("----- RAW GROQ RESPONSE END -----")

        return extract_json(raw_content)

    except ValueError:
        raise

    except Exception as e:
        raise ValueError(f"Groq LLM call failed: {str(e)}") from e


def analyze_transcript(transcript: str) -> Dict[str, Any]:
    if not transcript or not transcript.strip():
        raise ValueError("Transcript is empty.")

    system_prompt = """
You are an AI Meeting Assistant.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanation text.
Always return every key from the required JSON structure.
"""

    user_prompt = f"""
Analyze the meeting transcript.

Return JSON in this exact structure:

{{
  "title": "",
  "summary": "",
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
- Extract meeting summary, action items, decisions, and risks/concerns.
- Extract action items only from clear action/task statements.
- A sentence should become an action item only if it clearly assigns work to a person.
- Lines starting with "Action:" are strong action item signals.
- Direct statements like "Alice will complete testing" can be action items.
- Do not convert every discussion sentence into an action item.
- Do not convert general discussion statements like "we need to confirm..." into action items unless a specific owner is clearly responsible.
- Do not duplicate action items with similar meaning.
- If owner is not clear, use "Unassigned".
- If deadline is unavailable, use an empty string.
- Action item status should be "pending" by default.
- Extract decisions only from clear decisions or agreed outcomes.
- Extract risks only from clear risk, concern, blocker, issue, or dependency statements.
- Do not convert normal dependencies into risks unless explicitly stated as risk, concern, blocker, issue, or dependency.
- Do not invent information.
- Return valid JSON only.

Transcript:
{transcript}
"""

    return chat_json(system_prompt, user_prompt)


def answer_meeting_question(question: str, context_text: str) -> Dict[str, Any]:
    if not question or not question.strip():
        raise ValueError("Question is empty.")

    if not context_text or not context_text.strip():
        raise ValueError("Meeting context is empty.")

    system_prompt = """
You are an AI Meeting Assistant answering questions from stored meeting data.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanation text.
Use only the provided meeting context.
Always return every key from the required JSON structure.
"""

    user_prompt = f"""
Answer the user question using only the meeting context.

Return JSON in this exact structure:

{{
  "question": "",
  "answer": "",
  "supporting_points": []
}}

Rules:
- Always include question, answer, and supporting_points.
- If the question asks about risks, list all risks found in the meeting context.
- If the question asks about decisions, list all decisions found in the meeting context.
- If the question asks about action items, include owner and task.
- If the question asks about pending action items, include only incomplete action items.
- If the answer is not available, say "No relevant information found in the meeting context."
- Do not invent information.
- Keep the answer concise and professional.

Question:
{question}

Meeting Context:
{context_text}
"""

    return chat_json(system_prompt, user_prompt)


def generate_followup_email(
    transcript: str,
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not transcript or not transcript.strip():
        raise ValueError("Transcript is empty.")

    system_prompt = """
You are an AI Meeting Assistant that writes professional follow-up emails.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanation text.
Always return every key from the required JSON structure.
"""

    user_prompt = f"""
Generate a professional follow-up email.

Return JSON in this exact structure:

{{
  "subject": "",
  "body": ""
}}

The email should include:
- greeting
- short meeting summary
- action items with owners
- decisions
- risks or concerns
- professional closing
- Do not use placeholders like [Your Name], [Company Name], [Recipient Name], or [Sender Name].
- If no sender name is available, close the email with:
  Best regards,
  Team

Rules:
- Use only the provided meeting analysis and transcript.
- Do not invent names, attendees, dates, or company details.
- Keep the tone professional and concise.
- Format the body with clear sections where appropriate.
- Return valid JSON only.

Meeting Analysis:
{json.dumps(analysis or {}, indent=2)}

Transcript:
{transcript}
"""

    return chat_json(system_prompt, user_prompt)


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
Always return every key from the required JSON structure.
"""

    user_prompt = f"""
Analyze the previous meetings and answer the user query.

Return JSON using EXACTLY this structure. Do not remove any key:

{{
  "query": "{query}",
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

Rules:
- Use only the provided meeting context.
- Do not invent information.
- Always include all keys from the JSON structure.
- If the query asks about risks, fill recurring_risks and focus summary on risks.
- If the query asks about action items, fill pending_action_items and completed_action_items.
- If the query asks about decisions, fill important_decisions.
- If the query asks about deployment, include planning_points, important_decisions, recurring_risks, and final_next_steps.
- Include only incomplete action items in pending_action_items.
- Include completed action items only in completed_action_items.
- If information is unavailable, return an empty list.
- meeting_reference must be the meeting title when available.
- Do not duplicate repeated action items, decisions, or risks.

Query:
{query}

Previous Meetings Context:
{meetings_context}
"""

    return chat_json(system_prompt, user_prompt)


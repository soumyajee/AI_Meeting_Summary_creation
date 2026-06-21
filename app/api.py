import hashlib
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from .db import get_session
from .llm import (
    analyze_transcript,
    answer_meeting_question,
    consolidate_meeting_insights,
    generate_followup_email,
)
from .models import ActionItem, Decision, Meeting, Risk, TranscriptChunk
from .schemas import (
    AnalyzeRequest,
    FollowupRequest,
    MultiMeetingInsightRequest,
    QARequest,
    SearchRequest,
    UpdateActionItemRequest,
)
from .utils import chunk_transcript, read_upload_file


router = APIRouter(
    prefix="/meetings",
    tags=["Meetings"],
)


# -------------------------------------------------------------------
# Text / Duplicate Helpers
# -------------------------------------------------------------------

def normalize_key(text: str) -> str:
    return " ".join((text or "").lower().strip().split())


def normalize_transcript_for_hash(transcript: str) -> str:
    return normalize_key(transcript)


def get_transcript_hash(transcript: str) -> str:
    normalized = normalize_transcript_for_hash(transcript)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_same_transcript(existing_transcript: str, new_transcript: str) -> bool:
    return get_transcript_hash(existing_transcript) == get_transcript_hash(new_transcript)


def find_duplicate_meeting(
    session: Session,
    transcript: str,
) -> Optional[Meeting]:
    meetings = session.exec(select(Meeting)).all()

    for meeting in meetings:
        if is_same_transcript(meeting.transcript, transcript):
            return meeting

    return None


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, dict):
        return str(
            value.get("text")
            or value.get("decision")
            or value.get("risk")
            or value.get("concern")
            or value.get("task")
            or json.dumps(value)
        ).strip()

    return str(value).strip()


def normalize_action_item(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        status = item.get("status", "pending")
        completed = item.get("completed", False)

        if isinstance(status, str) and status.lower() == "completed":
            completed = True

        return {
            "owner": item.get("owner") or "Unassigned",
            "task": item.get("task") or item.get("text") or "",
            "completed": bool(completed),
        }

    return {
        "owner": "Unassigned",
        "task": str(item),
        "completed": False,
    }


def remove_duplicate_action_items(action_items: List[Any]) -> List[Dict[str, Any]]:
    cleaned_items = []
    seen_tasks = set()

    for raw_item in action_items:
        item = normalize_action_item(raw_item)

        owner = (item.get("owner") or "Unassigned").strip()
        task = (item.get("task") or "").strip()

        if not task:
            continue

        task_key = normalize_key(task)

        if task_key in seen_tasks:
            continue

        seen_tasks.add(task_key)

        cleaned_items.append(
            {
                "owner": owner,
                "task": task,
                "completed": bool(item.get("completed", False)),
            }
        )

    return cleaned_items


def remove_duplicate_text_items(items: List[Any]) -> List[str]:
    cleaned_items = []
    seen_texts = set()

    for raw_item in items:
        text = normalize_text(raw_item)

        if not text:
            continue

        text_key = normalize_key(text)

        if text_key in seen_texts:
            continue

        seen_texts.add(text_key)
        cleaned_items.append(text)

    return cleaned_items


def clean_analysis_result(analysis: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(analysis, dict):
        analysis = {}

    action_items = remove_duplicate_action_items(
        analysis.get("action_items", [])
    )

    decisions = remove_duplicate_text_items(
        analysis.get("decisions", [])
    )

    risk_values = []

    if isinstance(analysis.get("risks"), list):
        risk_values.extend(analysis.get("risks", []))

    if isinstance(analysis.get("concerns"), list):
        risk_values.extend(analysis.get("concerns", []))

    risks = remove_duplicate_text_items(risk_values)

    return {
        "title": analysis.get("title", ""),
        "summary": analysis.get("summary", ""),
        "action_items": action_items,
        "decisions": decisions,
        "risks": risks,
        "concerns": [],
    }


def normalize_multi_meeting_response(
    insights: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    if not isinstance(insights, dict):
        insights = {}

    normalized = {
        "query": insights.get("query") or query,
        "summary": insights.get("summary") or "",
        "previous_discussions": insights.get("previous_discussions") or [],
        "planning_points": insights.get("planning_points") or [],
        "important_decisions": insights.get("important_decisions") or [],
        "pending_action_items": insights.get("pending_action_items") or [],
        "completed_action_items": insights.get("completed_action_items") or [],
        "recurring_risks": insights.get("recurring_risks") or insights.get("risks") or [],
        "final_next_steps": insights.get("final_next_steps") or [],
        "key_themes": insights.get("key_themes") or [],
    }

    list_keys = [
        "previous_discussions",
        "planning_points",
        "important_decisions",
        "pending_action_items",
        "completed_action_items",
        "recurring_risks",
        "final_next_steps",
        "key_themes",
    ]

    for key in list_keys:
        if not isinstance(normalized[key], list):
            normalized[key] = [normalized[key]]

    normalized["important_decisions"] = remove_duplicate_text_items(
        normalized["important_decisions"]
    )
    normalized["recurring_risks"] = remove_duplicate_text_items(
        normalized["recurring_risks"]
    )
    normalized["planning_points"] = remove_duplicate_text_items(
        normalized["planning_points"]
    )
    normalized["previous_discussions"] = remove_duplicate_text_items(
        normalized["previous_discussions"]
    )
    normalized["final_next_steps"] = remove_duplicate_text_items(
        normalized["final_next_steps"]
    )
    normalized["key_themes"] = remove_duplicate_text_items(
        normalized["key_themes"]
    )
    normalized["pending_action_items"] = remove_duplicate_action_items(
        normalized["pending_action_items"]
    )
    normalized["completed_action_items"] = remove_duplicate_action_items(
        normalized["completed_action_items"]
    )

    return normalized


# -------------------------------------------------------------------
# Database Save / Retrieve Helpers
# -------------------------------------------------------------------

def save_transcript_chunks(
    session: Session,
    meeting_id: int,
    transcript: str,
) -> None:
    chunks = chunk_transcript(transcript)
    start_pos = 0

    for chunk_text in chunks:
        session.add(
            TranscriptChunk(
                meeting_id=meeting_id,
                text=chunk_text,
                start_pos=start_pos,
            )
        )
        start_pos += len(chunk_text)


def save_analysis_to_db(
    session: Session,
    title: str,
    transcript: str,
    analysis: Dict[str, Any],
) -> Meeting:
    duplicate_meeting = find_duplicate_meeting(
        session=session,
        transcript=transcript,
    )

    if duplicate_meeting:
        return duplicate_meeting

    analysis = clean_analysis_result(analysis)

    meeting = Meeting(
        title=title,
        transcript=transcript,
        summary=analysis.get("summary", ""),
    )

    session.add(meeting)
    session.commit()
    session.refresh(meeting)

    if meeting.id is None:
        raise RuntimeError("Meeting ID was not created.")

    meeting_id = meeting.id

    for item in analysis.get("action_items", []):
        session.add(
            ActionItem(
                meeting_id=meeting_id,
                owner=item["owner"],
                task=item["task"],
                completed=bool(item["completed"]),
            )
        )

    for decision_text in analysis.get("decisions", []):
        session.add(
            Decision(
                meeting_id=meeting_id,
                text=decision_text,
            )
        )

    for risk_text in analysis.get("risks", []):
        session.add(
            Risk(
                meeting_id=meeting_id,
                text=risk_text,
            )
        )

    save_transcript_chunks(
        session=session,
        meeting_id=meeting_id,
        transcript=transcript,
    )

    session.commit()
    session.refresh(meeting)

    return meeting


def get_meeting_details(
    session: Session,
    meeting_id: int,
    include_chunks: bool = False,
    include_transcript: bool = True,
) -> Dict[str, Any]:
    meeting = session.get(Meeting, meeting_id)

    if not meeting:
        raise HTTPException(
            status_code=404,
            detail="Meeting not found.",
        )

    action_items = session.exec(
        select(ActionItem).where(ActionItem.meeting_id == meeting_id)
    ).all()

    decisions = session.exec(
        select(Decision).where(Decision.meeting_id == meeting_id)
    ).all()

    risks = session.exec(
        select(Risk).where(Risk.meeting_id == meeting_id)
    ).all()

    data = {
        "id": meeting.id,
        "title": meeting.title,
        "summary": meeting.summary,
        "action_items": [
            {
                "id": item.id,
                "owner": item.owner,
                "task": item.task,
                "completed": item.completed,
            }
            for item in action_items
        ],
        "decisions": [
            {
                "id": decision.id,
                "text": decision.text,
            }
            for decision in decisions
        ],
        "risks": [
            {
                "id": risk.id,
                "text": risk.text,
            }
            for risk in risks
        ],
    }

    if include_transcript:
        data["transcript"] = meeting.transcript

    if include_chunks:
        chunks = session.exec(
            select(TranscriptChunk).where(TranscriptChunk.meeting_id == meeting_id)
        ).all()

        data["chunks"] = [
            {
                "id": chunk.id,
                "text": chunk.text,
                "start_pos": chunk.start_pos,
            }
            for chunk in chunks
        ]

    return data


def build_meeting_context(
    session: Session,
    meetings: List[Meeting],
) -> str:
    context_parts = []
    seen_hashes = set()

    for meeting in meetings:
        if meeting.id is None:
            continue

        transcript_hash = get_transcript_hash(meeting.transcript)

        if transcript_hash in seen_hashes:
            continue

        seen_hashes.add(transcript_hash)

        details = get_meeting_details(
            session=session,
            meeting_id=meeting.id,
            include_chunks=False,
            include_transcript=True,
        )

        context_parts.append(
            f"""
Meeting ID: {details["id"]}
Title: {details["title"]}

Transcript:
{details["transcript"]}

Summary:
{details["summary"]}

Action Items:
{json.dumps(details["action_items"], indent=2)}

Decisions:
{json.dumps(details["decisions"], indent=2)}

Risks:
{json.dumps(details["risks"], indent=2)}
"""
        )

    return "\n\n---\n\n".join(context_parts)


# -------------------------------------------------------------------
# Search Helpers
# -------------------------------------------------------------------

def expand_search_terms(query: str) -> List[str]:
    raw_query = query.lower().strip()

    stop_words = {
        "what", "who", "when", "where", "why", "how",
        "were", "was", "is", "are", "be", "been",
        "the", "a", "an", "during", "meeting", "meetings",
        "identified", "made", "taken", "show", "find",
        "all", "about", "regarding", "related", "to",
        "of", "in", "for", "with", "on",
    }

    synonym_map = {
        "deployment": [
            "deployment", "deploy", "deployed", "staging",
            "production", "release", "rollout",
        ],
        "deploy": [
            "deployment", "deploy", "deployed", "staging",
            "production", "release", "rollout",
        ],
        "decisions": [
            "decision", "decisions", "decided", "agreed",
            "approved", "confirmed",
        ],
        "decision": [
            "decision", "decisions", "decided", "agreed",
            "approved", "confirmed",
        ],
        "risks": [
            "risk", "risks", "concern", "concerns",
            "blocker", "issue", "dependency",
        ],
        "risk": [
            "risk", "risks", "concern", "concerns",
            "blocker", "issue", "dependency",
        ],
        "actions": [
            "action", "actions", "task", "tasks",
            "owner", "assigned", "pending",
        ],
        "action": [
            "action", "actions", "task", "tasks",
            "owner", "assigned", "pending",
        ],
    }

    words = [
        word.strip("?.!,;:")
        for word in raw_query.split()
        if word.strip("?.!,;:")
        and word.strip("?.!,;:") not in stop_words
    ]

    expanded_terms = set()

    for word in words:
        expanded_terms.add(word)

        if word in synonym_map:
            expanded_terms.update(synonym_map[word])

    if not expanded_terms:
        expanded_terms.add(raw_query)

    return sorted(expanded_terms)


def make_snippet(
    text: str,
    matched_terms: List[str],
    size: int = 180,
) -> str:
    if not text:
        return ""

    lower_text = text.lower()
    first_index = -1

    for term in matched_terms:
        index = lower_text.find(term.lower())

        if index != -1:
            first_index = index
            break

    if first_index == -1:
        return text[:size] + ("..." if len(text) > size else "")

    start = max(first_index - 60, 0)
    end = min(first_index + size, len(text))

    snippet = text[start:end].strip()

    if start > 0:
        snippet = "..." + snippet

    if end < len(text):
        snippet = snippet + "..."

    return snippet


def find_matching_meetings(
    session: Session,
    query: str,
) -> List[Dict[str, Any]]:
    expanded_terms = expand_search_terms(query)
    meetings = session.exec(select(Meeting)).all()

    matched_meetings = []
    seen_transcript_hashes = set()

    for meeting in meetings:
        if meeting.id is None:
            continue

        transcript_hash = get_transcript_hash(meeting.transcript)

        if transcript_hash in seen_transcript_hashes:
            continue

        seen_transcript_hashes.add(transcript_hash)

        details = get_meeting_details(
            session=session,
            meeting_id=meeting.id,
            include_chunks=False,
            include_transcript=False,
        )

        searchable_text = json.dumps(details).lower()

        matched_terms = [
            term for term in expanded_terms
            if term in searchable_text
        ]

        if not matched_terms:
            continue

        snippet_source = " ".join(
            [
                details.get("summary") or "",
                " ".join(decision["text"] for decision in details.get("decisions", [])),
                " ".join(risk["text"] for risk in details.get("risks", [])),
                " ".join(item["task"] for item in details.get("action_items", [])),
            ]
        )

        matched_meetings.append(
            {
                "score": len(matched_terms),
                "matched_terms": matched_terms,
                "meeting_id": details["id"],
                "title": details["title"],
                "summary": details["summary"],
                "snippet": make_snippet(
                    text=snippet_source,
                    matched_terms=matched_terms,
                ),
                "action_items": details["action_items"],
                "decisions": details["decisions"],
                "risks": details["risks"],
            }
        )

    matched_meetings.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return matched_meetings


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------

@router.get("/action-items/pending/all")
def get_pending_action_items(
    session: Session = Depends(get_session),
):
    try:
        action_items = session.exec(
            select(ActionItem).where(ActionItem.completed == False)
        ).all()

        return {
            "success": True,
            "count": len(action_items),
            "data": [
                {
                    "id": item.id,
                    "meeting_id": item.meeting_id,
                    "owner": item.owner,
                    "task": item.task,
                    "completed": item.completed,
                }
                for item in action_items
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve pending action items: {str(e)}",
        )


@router.patch("/action-items/{action_item_id}")
def update_action_item_status(
    action_item_id: int,
    request: UpdateActionItemRequest,
    session: Session = Depends(get_session),
):
    try:
        action_item = session.get(ActionItem, action_item_id)

        if not action_item:
            raise HTTPException(
                status_code=404,
                detail="Action item not found.",
            )

        action_item.completed = request.completed

        session.add(action_item)
        session.commit()
        session.refresh(action_item)

        return {
            "success": True,
            "message": "Action item updated successfully.",
            "data": {
                "id": action_item.id,
                "meeting_id": action_item.meeting_id,
                "owner": action_item.owner,
                "task": action_item.task,
                "completed": action_item.completed,
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update action item: {str(e)}",
        )


@router.post("/analyze")
async def analyze(
    request: AnalyzeRequest,
    session: Session = Depends(get_session),
):
    try:
        transcript = request.transcript.strip()

        if not transcript:
            raise HTTPException(
                status_code=400,
                detail="Transcript text is required.",
            )

        existing_meeting = find_duplicate_meeting(
            session=session,
            transcript=transcript,
        )

        if existing_meeting:
            return {
                "success": True,
                "message": "Duplicate transcript found. Existing meeting returned.",
                "data": get_meeting_details(
                    session=session,
                    meeting_id=existing_meeting.id,
                    include_chunks=False,
                    include_transcript=True,
                ),
            }

        analysis = clean_analysis_result(
            analyze_transcript(transcript)
        )

        title = request.title or analysis.get("title") or "Untitled Meeting"

        meeting = save_analysis_to_db(
            session=session,
            title=title,
            transcript=transcript,
            analysis=analysis,
        )

        return {
            "success": True,
            "message": "Meeting analyzed successfully.",
            "data": get_meeting_details(
                session=session,
                meeting_id=meeting.id,
                include_chunks=False,
                include_transcript=True,
            ),
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM response error: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Meeting analysis failed: {str(e)}",
        )


@router.post("/upload")
async def upload_meeting_file(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    try:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file must have a filename.",
            )

        filename = file.filename.lower()

        if not (
            filename.endswith(".txt")
            or filename.endswith(".pdf")
            or filename.endswith(".docx")
        ):
            raise HTTPException(
                status_code=400,
                detail="Only .txt, .pdf, and .docx files are supported.",
            )

        transcript_text = read_upload_file(file)

        if not transcript_text or not transcript_text.strip():
            raise HTTPException(
                status_code=400,
                detail="Uploaded file did not contain readable text.",
            )

        transcript_text = transcript_text.strip()

        existing_meeting = find_duplicate_meeting(
            session=session,
            transcript=transcript_text,
        )

        if existing_meeting:
            return {
                "success": True,
                "message": "Duplicate transcript found. Existing meeting returned.",
                "filename": file.filename,
                "data": get_meeting_details(
                    session=session,
                    meeting_id=existing_meeting.id,
                    include_chunks=False,
                    include_transcript=True,
                ),
            }

        analysis = clean_analysis_result(
            analyze_transcript(transcript_text)
        )

        title = analysis.get("title") or file.filename

        meeting = save_analysis_to_db(
            session=session,
            title=title,
            transcript=transcript_text,
            analysis=analysis,
        )

        return {
            "success": True,
            "message": "File uploaded and analyzed successfully.",
            "filename": file.filename,
            "data": get_meeting_details(
                session=session,
                meeting_id=meeting.id,
                include_chunks=False,
                include_transcript=True,
            ),
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Upload analysis failed: {str(e)}",
        )


@router.get("")
def list_meetings(
    session: Session = Depends(get_session),
):
    try:
        meetings = session.exec(
            select(Meeting).order_by(Meeting.id.desc())
        ).all()

        seen_hashes = set()
        data = []

        for meeting in meetings:
            if meeting.id is None:
                continue

            transcript_hash = get_transcript_hash(meeting.transcript)

            if transcript_hash in seen_hashes:
                continue

            seen_hashes.add(transcript_hash)

            data.append(
                get_meeting_details(
                    session=session,
                    meeting_id=meeting.id,
                    include_chunks=False,
                    include_transcript=False,
                )
            )

        return {
            "success": True,
            "count": len(data),
            "data": data,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve meetings: {str(e)}",
        )


@router.post("/ask")
async def ask_meeting_question(
    request: QARequest,
    session: Session = Depends(get_session),
):
    try:
        if not request.question or not request.question.strip():
            raise HTTPException(
                status_code=400,
                detail="Question is required.",
            )

        if request.meeting_id:
            meeting = session.get(Meeting, request.meeting_id)

            if not meeting:
                raise HTTPException(
                    status_code=404,
                    detail="Meeting not found.",
                )

            meetings = [meeting]

        else:
            meetings = session.exec(
                select(Meeting).order_by(Meeting.id.desc())
            ).all()

            if not meetings:
                raise HTTPException(
                    status_code=404,
                    detail="No analyzed meetings found.",
                )

        context_text = build_meeting_context(
            session=session,
            meetings=meetings,
        )

        answer = answer_meeting_question(
            question=request.question,
            context_text=context_text,
        )

        return {
            "success": True,
            "message": "Question answered successfully.",
            "data": answer,
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM response error: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Question answering failed: {str(e)}",
        )


@router.post("/search")
def search_meetings(
    request: SearchRequest,
    session: Session = Depends(get_session),
):
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Search query is required.",
            )

        matched_meetings = find_matching_meetings(
            session=session,
            query=request.query,
        )

        if not matched_meetings:
            return {
                "success": True,
                "query": request.query,
                "answer": {
                    "question": request.query,
                    "answer": "No matching meetings found.",
                    "supporting_points": [],
                },
                "count": 0,
                "results": [],
            }

        matched_meeting_objects = []

        for item in matched_meetings:
            meeting_id = item["meeting_id"]
            meeting = session.get(Meeting, meeting_id)

            if meeting:
                matched_meeting_objects.append(meeting)

        context_text = build_meeting_context(
            session=session,
            meetings=matched_meeting_objects,
        )

        answer = answer_meeting_question(
            question=request.query,
            context_text=context_text,
        )

        return {
            "success": True,
            "query": request.query,
            "answer": answer,
            "count": len(matched_meetings),
            "results": matched_meetings,
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM response error: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Meeting search failed: {str(e)}",
        )


@router.post("/followup-email")
async def create_followup_email(
    request: FollowupRequest,
    session: Session = Depends(get_session),
):
    try:
        meeting = session.get(Meeting, request.meeting_id)

        if not meeting:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found.",
            )

        analysis = get_meeting_details(
            session=session,
            meeting_id=meeting.id,
            include_chunks=False,
            include_transcript=False,
        )

        email = generate_followup_email(
            transcript=meeting.transcript,
            analysis=analysis,
        )

        return {
            "success": True,
            "message": "Follow-up email generated successfully.",
            "data": email,
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM response error: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Follow-up email generation failed: {str(e)}",
        )


@router.post("/multi-meeting-insights")
async def get_multi_meeting_insights(
    request: MultiMeetingInsightRequest,
    session: Session = Depends(get_session),
):
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Insight query is required.",
            )

        if request.meeting_ids:
            meetings = session.exec(
                select(Meeting).where(Meeting.id.in_(request.meeting_ids))
            ).all()
        else:
            meetings = session.exec(
                select(Meeting).order_by(Meeting.id.desc()).limit(5)
            ).all()

        if not meetings:
            raise HTTPException(
                status_code=404,
                detail="No meetings found for insight generation.",
            )

        unique_meetings = []
        seen_hashes = set()

        for meeting in meetings:
            transcript_hash = get_transcript_hash(meeting.transcript)

            if transcript_hash in seen_hashes:
                continue

            seen_hashes.add(transcript_hash)
            unique_meetings.append(meeting)

        meetings_context = build_meeting_context(
            session=session,
            meetings=unique_meetings,
        )

        insights = consolidate_meeting_insights(
            meetings_context=meetings_context,
            query=request.query,
        )

        insights = normalize_multi_meeting_response(
            insights=insights,
            query=request.query,
        )

        return {
            "success": True,
            "message": "Multi-meeting insights generated successfully.",
            "meeting_count": len(unique_meetings),
            "meeting_titles": [
                meeting.title or f"Meeting {meeting.id}"
                for meeting in unique_meetings
            ],
            "data": insights,
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM response error: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Multi-meeting insight generation failed: {str(e)}",
        )


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: int,
    session: Session = Depends(get_session),
):
    return {
        "success": True,
        "data": get_meeting_details(
            session=session,
            meeting_id=meeting_id,
            include_chunks=True,
            include_transcript=True,
        ),
    }


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: int,
    session: Session = Depends(get_session),
):
    try:
        meeting = session.get(Meeting, meeting_id)

        if not meeting:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found.",
            )

        action_items = session.exec(
            select(ActionItem).where(ActionItem.meeting_id == meeting_id)
        ).all()

        decisions = session.exec(
            select(Decision).where(Decision.meeting_id == meeting_id)
        ).all()

        risks = session.exec(
            select(Risk).where(Risk.meeting_id == meeting_id)
        ).all()

        chunks = session.exec(
            select(TranscriptChunk).where(TranscriptChunk.meeting_id == meeting_id)
        ).all()

        for item in action_items:
            session.delete(item)

        for decision in decisions:
            session.delete(decision)

        for risk in risks:
            session.delete(risk)

        for chunk in chunks:
            session.delete(chunk)

        session.delete(meeting)
        session.commit()

        return {
            "success": True,
            "message": "Meeting deleted successfully.",
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete meeting: {str(e)}",
        )


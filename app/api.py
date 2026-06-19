import json
from typing import Any, Dict, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlmodel import Session, select

from .db import get_session
from .models import Meeting, ActionItem, Decision, Risk, TranscriptChunk
from .schemas import (
    AnalyzeRequest,
    QARequest,
    SearchRequest,
    FollowupRequest,
    MultiMeetingInsightRequest,
    UpdateActionItemRequest,
)
from .utils import read_upload_file, chunk_transcript
from .llm import (
    analyze_transcript,
    answer_meeting_question,
    generate_followup_email,
    consolidate_meeting_insights,
)


router = APIRouter(
    prefix="/meetings",
    tags=["Meetings"],
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, dict):
        return (
            value.get("text")
            or value.get("decision")
            or value.get("risk")
            or value.get("concern")
            or value.get("task")
            or json.dumps(value)
        )

    return str(value)


def normalize_action_item(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return {
            "owner": item.get("owner") or "Unassigned",
            "task": item.get("task") or item.get("text") or "",
            "completed": bool(item.get("completed", False)),
        }

    return {
        "owner": "Unassigned",
        "task": str(item),
        "completed": False,
    }


def save_transcript_chunks(session: Session, meeting_id: int, transcript: str) -> None:
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

    for raw_item in analysis.get("action_items", []):
        item = normalize_action_item(raw_item)

        if item["task"]:
            session.add(
                ActionItem(
                    meeting_id=meeting_id,
                    owner=item["owner"],
                    task=item["task"],
                    completed=item["completed"],
                )
            )

    for raw_decision in analysis.get("decisions", []):
        decision_text = normalize_text(raw_decision)

        if decision_text:
            session.add(
                Decision(
                    meeting_id=meeting_id,
                    text=decision_text,
                )
            )

    risks = []

    if isinstance(analysis.get("risks"), list):
        risks.extend(analysis.get("risks", []))

    if isinstance(analysis.get("concerns"), list):
        risks.extend(analysis.get("concerns", []))

    for raw_risk in risks:
        risk_text = normalize_text(raw_risk)

        if risk_text:
            session.add(
                Risk(
                    meeting_id=meeting_id,
                    text=risk_text,
                )
            )

    save_transcript_chunks(session, meeting_id, transcript)

    session.commit()
    session.refresh(meeting)

    return meeting


def get_meeting_details(session: Session, meeting_id: int) -> Dict[str, Any]:
    meeting = session.get(Meeting, meeting_id)

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

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

    return {
        "id": meeting.id,
        "title": meeting.title,
        "transcript": meeting.transcript,
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
        "chunks": [
            {
                "id": chunk.id,
                "text": chunk.text,
                "start_pos": chunk.start_pos,
            }
            for chunk in chunks
        ],
    }


def build_meeting_context(session: Session, meetings: List[Meeting]) -> str:
    context_parts = []

    for meeting in meetings:
        if meeting.id is None:
            continue

        details = get_meeting_details(session, meeting.id)

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


def find_matching_meetings(
    session: Session,
    query: str,
) -> List[Dict[str, Any]]:
    expanded_terms = expand_search_terms(query)

    meetings = session.exec(select(Meeting)).all()
    matched_meetings = []

    for meeting in meetings:
        if meeting.id is None:
            continue

        details = get_meeting_details(session, meeting.id)
        searchable_text = json.dumps(details).lower()

        matched_terms = [
            term for term in expanded_terms
            if term in searchable_text
        ]

        if matched_terms:
            matched_meetings.append(
                {
                    "score": len(matched_terms),
                    "matched_terms": matched_terms,
                    "meeting": details,
                }
            )

    matched_meetings.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return matched_meetings


@router.post("/analyze")
async def analyze(
    request: AnalyzeRequest,
    session: Session = Depends(get_session),
):
    try:
        if not request.transcript or not request.transcript.strip():
            raise HTTPException(status_code=400, detail="Transcript text is required.")

        analysis = analyze_transcript(request.transcript)

        title = request.title or analysis.get("title") or "Untitled Meeting"

        meeting = save_analysis_to_db(
            session=session,
            title=title,
            transcript=request.transcript,
            analysis=analysis,
        )

        return {
            "success": True,
            "message": "Meeting analyzed successfully.",
            "data": get_meeting_details(session, meeting.id),
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"LLM response error: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Meeting analysis failed: {str(e)}")


@router.post("/upload")
async def upload_meeting_file(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

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

        analysis = analyze_transcript(transcript_text)

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
            "data": get_meeting_details(session, meeting.id),
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload analysis failed: {str(e)}")


@router.get("")
def list_meetings(session: Session = Depends(get_session)):
    meetings = session.exec(
        select(Meeting).order_by(Meeting.id.desc())
    ).all()

    return {
        "success": True,
        "count": len(meetings),
        "data": [
            get_meeting_details(session, meeting.id)
            for meeting in meetings
            if meeting.id is not None
        ],
    }


@router.post("/ask")
async def ask_meeting_question(
    request: QARequest,
    session: Session = Depends(get_session),
):
    try:
        if not request.question or not request.question.strip():
            raise HTTPException(status_code=400, detail="Question is required.")

        if request.meeting_id:
            meeting = session.get(Meeting, request.meeting_id)

            if not meeting:
                raise HTTPException(status_code=404, detail="Meeting not found.")

            meetings = [meeting]

        else:
            meetings = session.exec(
                select(Meeting).order_by(Meeting.id.desc())
            ).all()

            if not meetings:
                raise HTTPException(status_code=404, detail="No analyzed meetings found.")

        context_text = build_meeting_context(session=session, meetings=meetings)

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
        raise HTTPException(status_code=502, detail=f"LLM response error: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Question answering failed: {str(e)}")


@router.post("/search")
def search_meetings(
    request: SearchRequest,
    session: Session = Depends(get_session),
):
    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Search query is required.")

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
            meeting_id = item["meeting"]["id"]
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
        raise HTTPException(status_code=502, detail=f"LLM response error: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Meeting search failed: {str(e)}")


@router.post("/followup-email")
async def create_followup_email(
    request: FollowupRequest,
    session: Session = Depends(get_session),
):
    try:
        meeting = session.get(Meeting, request.meeting_id)

        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found.")

        analysis = get_meeting_details(session, meeting.id)

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
        raise HTTPException(status_code=502, detail=f"LLM response error: {str(e)}")

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
            raise HTTPException(status_code=400, detail="Insight query is required.")

        if request.meeting_ids:
            meetings = session.exec(
                select(Meeting).where(Meeting.id.in_(request.meeting_ids))
            ).all()
        else:
            meetings = session.exec(
                select(Meeting).order_by(Meeting.id.desc()).limit(5)
            ).all()

        if not meetings:
            raise HTTPException(status_code=404, detail="No meetings found.")

        meetings_context = build_meeting_context(
            session=session,
            meetings=meetings,
        )

        insights = consolidate_meeting_insights(
            meetings_context=meetings_context,
            query=request.query,
        )

        return {
            "success": True,
            "message": "Multi-meeting insights generated successfully.",
            "meeting_count": len(meetings),
            "data": insights,
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"LLM response error: {str(e)}")

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Multi-meeting insight generation failed: {str(e)}",
        )


@router.get("/action-items/pending/all")
def get_pending_action_items(session: Session = Depends(get_session)):
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


@router.patch("/action-items/{action_item_id}")
def update_action_item_status(
    action_item_id: int,
    request: UpdateActionItemRequest,
    session: Session = Depends(get_session),
):
    action_item = session.get(ActionItem, action_item_id)

    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found.")

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


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: int,
    session: Session = Depends(get_session),
):
    return {
        "success": True,
        "data": get_meeting_details(session, meeting_id),
    }


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: int,
    session: Session = Depends(get_session),
):
    meeting = session.get(Meeting, meeting_id)

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

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
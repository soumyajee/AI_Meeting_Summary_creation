from typing import List, Optional
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    title: Optional[str] = None
    transcript: str


class AnalyzeResponse(BaseModel):
    meeting_id: int
    summary: str
    action_items: list
    decisions: list
    risks: list


class QARequest(BaseModel):
    meeting_id: Optional[int] = None
    question: str


class SearchRequest(BaseModel):
    query: str


class SearchResponse(BaseModel):
    query: str
    results: list


class FollowupRequest(BaseModel):
    meeting_id: Optional[int] = None
    transcript: Optional[str] = None


class MultiMeetingInsightRequest(BaseModel):
    query: str
    meeting_ids: Optional[List[int]] = None


class UpdateActionItemRequest(BaseModel):
    completed: bool
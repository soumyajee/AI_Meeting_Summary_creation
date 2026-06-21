from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    title: Optional[str] = None
    transcript: str = Field(..., min_length=1)


class AnalyzeResponse(BaseModel):
    meeting_id: int
    summary: str
    action_items: list
    decisions: list
    risks: list


class QARequest(BaseModel):
    meeting_id: Optional[int] = None
    question: str = Field(..., min_length=1)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)


class SearchResponse(BaseModel):
    query: str
    results: list


class FollowupRequest(BaseModel):
    meeting_id: int


class MultiMeetingInsightRequest(BaseModel):
    query: str = Field(..., min_length=1)
    meeting_ids: Optional[List[int]] = None


class UpdateActionItemRequest(BaseModel):
    completed: bool

from typing import Optional

from sqlmodel import (
    SQLModel,
    Field
)



class Meeting(SQLModel, table=True):

    id: Optional[int] = Field(
        default=None,
        primary_key=True
    )

    title:str | None = None

    transcript:str

    summary:str | None = None





class ActionItem(SQLModel, table=True):

    id:Optional[int] = Field(
        default=None,
        primary_key=True
    )


    meeting_id:int


    owner:str | None = None


    task:str


    completed:bool = False





class Decision(SQLModel, table=True):

    id:Optional[int] = Field(
        default=None,
        primary_key=True
    )


    meeting_id:int


    text:str






class Risk(SQLModel, table=True):

    id:Optional[int] = Field(
        default=None,
        primary_key=True
    )


    meeting_id:int


    text:str
    
class TranscriptChunk(SQLModel, table=True):

    id:Optional[int] = Field(
        default=None,
        primary_key=True
    )


    meeting_id:int


    text:str


    start_pos:int = 0
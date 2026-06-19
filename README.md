# AI Meeting Assistant

## Overview

AI Meeting Assistant is a FastAPI-based backend application that analyzes meeting transcripts and generates structured meeting insights.

The system can extract:

* Meeting summary
* Action items with owner and task
* Decisions taken
* Risks and concerns
* Follow-up email content
* Meeting Q&A answers
* Search results across previous meetings
* Multi-meeting consolidated insights

The application supports transcript input through direct text and file upload.

Supported file formats:

* `.txt`
* `.pdf`
* `.docx`

---

## Tech Stack

* Python
* FastAPI
* SQLModel
* SQLite
* Groq LLM API
* pdfplumber
* python-docx
* Swagger / OpenAPI

---

## Project Structure

```text
meeting_summary/
├── app/
│   ├── __init__.py
│   ├── api.py
│   ├── db.py
│   ├── llm.py
│   ├── models.py
│   ├── schemas.py
│   └── utils.py
│
├── main.py
├── requirements.txt
├── README.md
├── ARCHITECTURE.md
├── .env
└── .gitignore
```

---

## Module Description

### `main.py`

Creates the FastAPI application, initializes the database, registers routers, and enables Swagger documentation.

### `app/api.py`

Contains all API endpoints for meeting analysis, upload, retrieval, Q&A, search, follow-up emails, action items, and multi-meeting insights.

### `app/llm.py`

Handles Groq LLM integration, prompt construction, JSON response validation, and LLM-based workflows.

### `app/db.py`

Configures the database engine and provides SQLModel database sessions.

### `app/models.py`

Defines database tables:

* Meeting
* ActionItem
* Decision
* Risk
* TranscriptChunk

### `app/schemas.py`

Defines request and response schemas using Pydantic.

### `app/utils.py`

Handles file reading and transcript chunking.

---

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <your-github-repository-url>
cd meeting_summary
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

Activate environment on Windows:

```bash
venv\Scripts\activate
```

Activate environment on Linux/Mac:

```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create `.env` File

Create a `.env` file in the project root.

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=sqlite:///meeting_assistant.db
```

### 5. Run the Application

```bash
uvicorn main:app --reload
```

### 6. Open Swagger Documentation

Open this URL in browser:

```text
http://127.0.0.1:8000/docs
```

---

## API Endpoints

| Method | Endpoint                                  | Description                                  |
| ------ | ----------------------------------------- | -------------------------------------------- |
| POST   | `/meetings/analyze`                       | Analyze transcript from direct text          |
| POST   | `/meetings/upload`                        | Upload `.txt`, `.pdf`, or `.docx` transcript |
| GET    | `/meetings`                               | Get all analyzed meetings                    |
| GET    | `/meetings/{meeting_id}`                  | Get one meeting by ID                        |
| POST   | `/meetings/ask`                           | Ask questions about meeting data             |
| POST   | `/meetings/search`                        | Search across previous meetings              |
| POST   | `/meetings/followup-email`                | Generate professional follow-up email        |
| POST   | `/meetings/multi-meeting-insights`        | Generate insights across multiple meetings   |
| GET    | `/meetings/action-items/pending/all`      | List all pending action items                |
| PATCH  | `/meetings/action-items/{action_item_id}` | Update action item completion status         |
| DELETE | `/meetings/{meeting_id}`                  | Delete a meeting                             |

---

## Sample API Requests and Responses

### 1. Analyze Meeting Transcript

Endpoint:

```text
POST /meetings/analyze
```

Request:

```json
{
  "title": "Deployment Planning Meeting",
  "transcript": "Anita will verify the deployment checklist. David will coordinate deployment testing. The team decided to deploy to staging first, then production after sign-off. Risk identified: rollback plan is not finalized."
}
```

Response:

```json
{
  "success": true,
  "message": "Meeting analyzed successfully.",
  "data": {
    "id": 1,
    "title": "Deployment Planning Meeting",
    "summary": "The meeting focused on deployment planning, testing coordination, and release approval.",
    "action_items": [
      {
        "id": 1,
        "owner": "Anita",
        "task": "Verify the deployment checklist",
        "completed": false
      },
      {
        "id": 2,
        "owner": "David",
        "task": "Coordinate deployment testing",
        "completed": false
      }
    ],
    "decisions": [
      {
        "id": 1,
        "text": "Deploy to staging first, then production after sign-off."
      }
    ],
    "risks": [
      {
        "id": 1,
        "text": "Rollback plan is not finalized."
      }
    ]
  }
}
```

---

### 2. Upload Transcript File

Endpoint:

```text
POST /meetings/upload
```

Supported file types:

```text
.txt, .pdf, .docx
```

Response:

```json
{
  "success": true,
  "message": "File uploaded and analyzed successfully.",
  "filename": "meeting_transcript.pdf",
  "data": {
    "id": 2,
    "title": "meeting_transcript.pdf",
    "summary": "The meeting discussed project progress, deployment readiness, and open risks.",
    "action_items": [],
    "decisions": [],
    "risks": []
  }
}
```

---

### 3. Ask Question About a Meeting

Endpoint:

```text
POST /meetings/ask
```

Request:

```json
{
  "meeting_id": 1,
  "question": "What decisions were made regarding deployment?"
}
```

Response:

```json
{
  "success": true,
  "message": "Question answered successfully.",
  "data": {
    "question": "What decisions were made regarding deployment?",
    "answer": "The team decided to deploy to staging first, then production after sign-off.",
    "supporting_points": [
      "Deployment schedule was discussed.",
      "Production deployment requires sign-off."
    ]
  }
}
```

---

### 4. Search Previous Meetings

Endpoint:

```text
POST /meetings/search
```

Request:

```json
{
  "query": "deployment decisions"
}
```

Response:

```json
{
  "success": true,
  "query": "deployment decisions",
  "answer": {
    "question": "deployment decisions",
    "answer": "The deployment decision was to release to staging first and move to production after sign-off.",
    "supporting_points": [
      "Deployment planning was discussed.",
      "Staging and production environments were mentioned."
    ]
  },
  "count": 1,
  "results": [
    {
      "score": 2,
      "matched_terms": ["deployment", "decision"],
      "meeting": {
        "id": 1,
        "title": "Deployment Planning Meeting"
      }
    }
  ]
}
```

---

### 5. Generate Follow-up Email

Endpoint:

```text
POST /meetings/followup-email
```

Request:

```json
{
  "meeting_id": 1
}
```

Response:

```json
{
  "success": true,
  "message": "Follow-up email generated successfully.",
  "data": {
    "subject": "Follow-up: Deployment Planning Meeting",
    "body": "Hi Team,\n\nThank you for attending the deployment planning meeting. We discussed the deployment checklist, testing coordination, and release approval process.\n\nAction Items:\n- Anita will verify the deployment checklist.\n- David will coordinate deployment testing.\n\nDecision:\n- Deploy to staging first, then production after sign-off.\n\nRisk:\n- Rollback plan is not finalized.\n\nBest regards,"
  }
}
```

---

### 6. Multi-Meeting Insights

Endpoint:

```text
POST /meetings/multi-meeting-insights
```

Request:

```json
{
  "query": "Summarize deployment planning, pending action items, risks, and final next steps from previous meetings."
}
```

Response:

```json
{
  "success": true,
  "message": "Multi-meeting insights generated successfully.",
  "meeting_count": 3,
  "data": {
    "query": "Summarize deployment planning, pending action items, risks, and final next steps from previous meetings.",
    "summary": "Deployment discussions focused on staging validation, production readiness, payment integration, and release approvals.",
    "previous_discussions": [
      "Deployment schedule was discussed.",
      "Environment readiness was reviewed."
    ],
    "planning_points": [
      "Verify deployment checklist.",
      "Coordinate deployment testing.",
      "Confirm payment integration."
    ],
    "important_decisions": [
      "Deploy to staging first, then production after sign-off."
    ],
    "pending_action_items": [
      {
        "owner": "Anita",
        "task": "Verify deployment checklist",
        "meeting_reference": "Deployment Planning Meeting"
      }
    ],
    "recurring_risks": [
      "Production rollback plan is not finalized."
    ],
    "final_next_steps": [
      "Complete deployment testing.",
      "Finalize rollback plan.",
      "Deploy to staging.",
      "Move to production after sign-off."
    ],
    "key_themes": [
      "Deployment planning",
      "Environment readiness",
      "Release approvals"
    ]
  }
}
```

---

## Architecture

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for detailed architecture, request flow, retrieval strategy, and scalability considerations.

---

## Error Handling

The application includes error handling for:

* Empty transcript input
* Empty uploaded file
* Unsupported file type
* Missing meeting ID
* Meeting not found
* Action item not found
* LLM API failure
* Empty LLM response
* Invalid JSON returned by LLM
* Database errors

Common HTTP status codes:

| Status Code | Meaning                         |
| ----------- | ------------------------------- |
| 400         | Invalid request input           |
| 404         | Resource not found              |
| 502         | LLM response or parsing failure |
| 500         | Internal server error           |

---

## Retrieval and Memory Strategy

The application stores analyzed meeting data in structured SQLModel tables.

Stored entities:

* Meeting summary
* Full transcript
* Transcript chunks
* Action items
* Decisions
* Risks

Q&A and search retrieve meeting context from the database and send relevant context to the LLM. Multi-meeting insights combine context from multiple previous meetings to generate consolidated planning, risks, decisions, and next steps.

---

## Scalability Considerations

For production, the system can be improved with:

* PostgreSQL instead of SQLite
* Vector database such as FAISS, ChromaDB, Qdrant, Pinecone, or Weaviate
* Embeddings for semantic search
* Background workers for long LLM processing
* Pagination for meeting history
* Authentication and authorization
* Cloud file storage such as AWS S3
* Logging, monitoring, and tracing
* Retry logic for LLM failures
* Rate limiting

---

## Assumptions

* Meeting transcripts are in English.
* Uploaded PDFs contain extractable text, not scanned images.
* Action items are pending by default.
* If an action item owner is unclear, owner is stored as `Unassigned`.
* SQLite is used for local development.
* Groq API is used as the LLM provider.
* The application returns structured JSON responses.
* Vector search is considered a future production improvement.

---

## Running Tests Manually

Start the server:

```bash
uvicorn main:app --reload
```

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

Test these endpoints in order:

1. `POST /meetings/analyze`
2. `GET /meetings`
3. `POST /meetings/ask`
4. `POST /meetings/search`
5. `POST /meetings/followup-email`
6. `POST /meetings/multi-meeting-insights`

---

## GitHub Submission

Before pushing to GitHub, create `.gitignore`:

```gitignore
.env
__pycache__/
*.pyc
meeting_assistant.db
venv/
.venv/
```

Then push:

```bash
git init
git add .
git commit -m "Initial AI Meeting Assistant implementation"
git branch -M main
git remote add origin <your-github-repository-url>
git push -u origin main
```

---

## Author

Developed as part of the AI Meeting Assistant assignment.

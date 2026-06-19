# Sample API Requests & Responses

## Analyze Transcript

Request:
```http
POST /api/analyze
Content-Type: application/json

{
  "title": "Deployment Planning",
  "transcript": "...meeting transcript text..."
}
```

Response:
```json
{
  "meeting_id": 1,
  "summary": "Deployment schedule, environment readiness, and release approvals were discussed.",
  "action_items": [
    {"owner": "Anita", "task": "Verify deployment checklist."},
    {"owner": "David", "task": "Coordinate deployment testing."}
  ],
  "decisions": ["Deploy to staging first, then production after sign-off."],
  "risks": ["Production rollback plan is not finalized."]
}
```

## Upload Transcript

Request:
```http
POST /api/upload
Content-Type: multipart/form-data

file=@samples/meeting_notes_1.txt
```

## Search Meetings

Request:
```http
POST /api/search
Content-Type: application/json

{"query": "deployment"}
```

Response:
```json
{
  "query": "deployment",
  "results": [
    {
      "meeting_id": 2,
      "title": "Deployment Planning",
      "snippet": "Deploy to staging first, then production after sign-off.",
      "score": 0.12
    }
  ]
}
```

## Phase 2 — Document Management, Analytics, Chatbot, Admissions, Leads

### Quick Start
```bash
cd backend
pip install -r requirements.txt
# .env must have:
#   DATABASE_URL, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_MINUTES
#   UPLOAD_DIR, MAX_UPLOAD_SIZE_MB, ALLOWED_FILE_TYPES
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### New Tables (9)
| Table | Purpose |
|---|---|
| `documents` | Uploaded files (pdf/docx/txt) |
| `document_chunks` | Text chunks extracted from documents |
| `chatbot_settings` | Per-school chatbot appearance config |
| `chatbot_widgets` | Per-school widget embed config |
| `conversations` | Chat sessions scoped by visitor |
| `messages` | Individual messages within conversations |
| `analytics_events` | Event log (question_asked, failed_answer, etc.) |
| `admission_settings` | Per-school admission form field config |
| `leads` | Prospective student inquiries |

### Endpoints

#### Documents (`/documents`)
- `POST /upload?language={en|ar}` — upload file (pdf/docx/txt, max 20MB). Background processes text → chunks.
- `GET /` — list school's documents
- `GET /{id}` — get document metadata + status
- `GET /{id}/chunks` — list chunks for a document
- `DELETE /{id}` — delete document + chunks + file
- `POST /{id}/reprocess` — re-process document text → chunks

#### Chatbot (`/chatbot`)
- `GET /settings` — get settings (auto-creates defaults)
- `PUT /settings` — update settings
- `GET /widget` — get widget config (auto-creates defaults)
- `POST /widget` — create widget
- `PUT /widget/{id}` — update widget
- `PATCH /widget/{id}/status` — toggle active/inactive

#### Analytics (`/analytics`)
- `GET /dashboard` — aggregated stats: top questions, visitor stats, lead stats, success rate

#### Admissions (`/admissions`)
- `GET /settings` — get admission fields config (auto-creates defaults)
- `PUT /settings` — update fields config

#### Leads (`/leads`)
- `GET /` — list school's leads (filter by status)
- `GET /{id}` — get lead details
- `PATCH /{id}/status` — update lead status (new→contacted→converted)

### Config
| Env Var | Default | Description |
|---|---|---|
| `UPLOAD_DIR` | `uploads` | File storage root |
| `MAX_UPLOAD_SIZE_MB` | `20` | Max upload size in MB |
| `ALLOWED_FILE_TYPES` | `.pdf,.docx,.txt` | Comma-separated allowed extensions |

### Auth
All endpoints require `Authorization: Bearer <jwt>` header, scoped to the user's school.

### Analytics Dashboard Response
```json
{
  "top_questions": [{"question_text": "...", "count": 5}],
  "visitor_stats": {
    "visitors_today": 10,
    "total_conversations": 50,
    "avg_messages_per_conversation": 3.2,
    "languages": {"en": 30, "ar": 20}
  },
  "lead_stats": {
    "new_leads": 5,
    "contacted_leads": 3,
    "converted_leads": 1,
    "popular_programs": {"CS": 4, "EE": 2},
    "grade_interest": {"12": 3, "11": 2}
  },
  "unanswered_count": 2,
  "answer_success_rate": 95.0
}
```

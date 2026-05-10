# History & Persistence API Documentation

This document explains the multi-tenant saving architecture introduced to the Ishikawa Knowledge System. It covers how data is persisted across both Neo4j and Supabase, the Prisma database setup, and how to consume the new API endpoints from the frontend.

---

## 1. Architecture Overview (Dual-Save)

When a user finalizes an analysis, the system performs a **Dual-Save**:

1. **Neo4j (Knowledge Graph)**: The visual Ishikawa and 5-Whys data is translated into a standard `ProblemStatement` node with fully scaffolded D1-D7 phases. This ensures that user-saved analyses immediately contribute to the shared knowledge base, improving the quality of future LLM contexts and vector searches.
2. **Supabase (Relational History)**: The original JSON structures (`IshikawaCategory[]` and `FiveWhyChainItem[]`) are saved to Supabase via Prisma. This allows the frontend to easily fetch and accurately render past analysis sessions without having to re-parse the entire Neo4j graph.

### The Security Triplet
To enforce multi-tenant isolation, every saved row in Supabase carries three required UUIDs:
* `user_id`: The user who created the record.
* `master_user_id`: The ID of the designated "Master User" for the organization.
* `org_id`: The organization the user belongs to.

**Visibility Rule:** 
Regular users can only fetch history matching their `user_id`. Master Users (where the requesting `user_id` matches the `master_user_id`) bypass this and can fetch all history for the entire `org_id`.

---

## 2. Database Management (Prisma)

The backend uses **Prisma ORM** to connect to Supabase.

### Schema Location
The database structure is defined in `schema.prisma`. It includes the following tables:
* `Organization`
* `User`
* `AnalysisSession`
* `SavedIshikawa`
* `SavedFiveWhys`
* `SystemLog`

### Common Prisma Commands
If you ever modify `schema.prisma`, you must run these commands from the `TE-backend` directory to apply the changes:

```bash
# Push the schema changes directly to the Supabase database
.venv\Scripts\prisma db push --schema schema.prisma

# Regenerate the Python client so your code recognizes the new fields
.venv\Scripts\prisma generate --schema schema.prisma
```

---

## 3. API Endpoints

### A. Save Analysis
**`POST /api/save`**

Persists a finalized analysis to both Neo4j and Supabase. 

**Request Payload (`SaveAllRequest`)**
```json
{
  "domain": "Manufacturing",
  "query": "Connector torque failure during assembly",
  "past_record": 5,
  "session_title": "Assembly Line B Failure",
  "ticket_ref": "INC-10294",
  "part_number": "PN-74892",
  "ishikawa": [
    // Array of IshikawaCategory objects from the frontend
  ],
  "analysis": [
    // Array of FiveWhyChainItem objects from the frontend
  ],
  
  // Security Triplet (Required for Supabase history)
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "master_user_id": "987fcdeb-51a2-43d7-9012-345678901234",
  "org_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (`SaveAllResponse`)**
```json
{
  "success": true,
  "message": "Analysis saved to Neo4j (ps_id=...). Saved to Supabase (session=...).",
  "neo4j_ps_id": "neo4j-uuid-here",
  "neo4j_content_count": 14,
  "supabase_session_id": "supabase-session-uuid",
  "supabase_ishikawa_id": "supabase-ishikawa-uuid",
  "supabase_five_whys_id": "supabase-five-whys-uuid",
  "supabase_skipped": false
}
```

---

### B. Fetch History
**`POST /api/history`**

Retrieves a list of past analysis sessions. Automatically handles Master User visibility.

**Request Payload (`HistoryRequest`)**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "master_user_id": "987fcdeb-51a2-43d7-9012-345678901234",
  "org_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (`HistoryResponse`)**
```json
{
  "success": true,
  "message": null,
  "sessions": [
    {
      "session_id": "supabase-session-uuid",
      "query": "Connector torque failure during assembly",
      "domain": "Manufacturing",
      "title": "Assembly Line B Failure",
      "created_at": "2026-05-10T02:12:21.608Z",
      "cause_count": 5,
      "root_causes": [
        "Lack of automated maintenance alerts in legacy system"
      ],
      "ishikawa": [
        // Full Ishikawa JSON ready to be loaded into UI
      ],
      "five_whys": [
        // Full 5-Whys JSON ready to be loaded into UI
      ]
    }
  ]
}
```

### Displaying History in the Frontend
1. Call `/api/history` when the user opens the History page.
2. Use the top-level fields (`query`, `title`, `created_at`, `cause_count`, `root_causes`) to render a lightweight table or list of past sessions.
3. When a user clicks a specific row, you already have the full `ishikawa` and `five_whys` JSON arrays attached to that item. You can immediately inject those arrays into your visual diagram components without making a second API call.

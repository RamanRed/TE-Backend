# Ishikawa Knowledge System Backend

This is the backend API for the Ishikawa Knowledge System. It provides endpoints for root cause analysis (Ishikawa & 5-Whys), history tracking, and authentication. The backend is built using FastAPI and uses Supabase (PostgreSQL) and Neo4j for data persistence.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) (Extremely fast Python package installer and resolver)
- Python 3.12+ (managed automatically by uv if needed)
- Running instances of Neo4j and Supabase (PostgreSQL)

## Getting Started

Follow these steps to get the system up and running using `uv`.

### 1. Environment Setup

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Ensure you configure the `.env` file with your `NEO4J_URI`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `JWT_SECRET`.

### 2. Install Dependencies

Sync the environment using `uv` (this will automatically install all dependencies from `uv.lock`):

```bash
uv sync
```

### 3. Generate Prisma Client

The backend uses Prisma to interact with Supabase. You must generate the Prisma Python client code:

```bash
uv run prisma generate
```

*(Note: You must run this command whenever you update `schema.prisma` or set up the project for the first time)*

### 4. Push Database Schema (First Time Setup)

If your database doesn't have the tables yet, push the Prisma schema to your database:

```bash
uv run prisma db push
```

### 5. Run the Server

Start the FastAPI server:

```bash
uv run python main.py server
```

The server will automatically start on `http://0.0.0.0:8000` (or the port specified in your `.env`). It runs with live-reloading enabled by default.

---

## API & Project Structure

- **Root Cause Analysis (`/api/problem`, `/api/gen-five-why`)**: Uses LLM integration to generate Ishikawa diagrams and 5-Whys analyses based on user queries.
- **Data Persistence (`/api/save`)**: Implements dual-store saving. Analysis results are saved to both Neo4j (for knowledge graph) and Supabase (for relational tracking and user history).
- **Authentication & History (`/api/auth/*`, `/api/history`)**: Uses JWT tokens for secure authentication. User and organization data are managed with Prisma. 

For more detailed information on specific features, please see the extended documentation files:
- [JWT Testing & Auth Flow](./HISTORY_JWT_TESTING.md)
- [History API & Schema Documentation](./HISTORY_API_README.md)

## Troubleshooting

- **`ModuleNotFoundError: No module named 'prisma'`**: This happens if you ran `python main.py server` using your global Python installation. Always prefix your commands with `uv run` (e.g., `uv run python main.py server`).
- **Ollama / LLM Connection Issues**: Ensure your Ollama server (or other LLM provider) is running in the background and accessible at the host/port configured in your `.env`.

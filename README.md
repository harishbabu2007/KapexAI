# KapexAI

KapexAI is a business consultant chatbot. A user describes their business idea
and KapexAI helps them think it through: it asks a few questions, can research
topics on the web, and can produce analyses like a SWOT breakdown.

## How it works

The project is split into three parts that run together:

- **Backend** (`backend/`) - a FastAPI app that exposes the chat endpoints and
  streams responses to the frontend over a WebSocket.
- **Worker** (`worker/`) - a background process that picks up each user message
  and decides what to do with it. Every message either gets a conversational
  reply or is handed to one of the available tools.
- **Services** (`services/`) - PostgreSQL for storing conversations and Redis
  for the job queue and real-time streaming.

## Tools

Tools are the capabilities the chatbot can use. They are registered in one place
(`worker/tools/registry.py`), so adding a new one means writing a class and
registering it.

Currently available:

- **Questionnaire** - asks targeted questions about the business idea to gather
  context before the assistant gives advice.
- **Web search** - researches a topic, a competitor, or a market on the web.
- **SWOT** - produces a SWOT (strengths, weaknesses, opportunities, threats)
  analysis.

## Getting started

Requirements: Python 3.12+ and `uv`, plus a running PostgreSQL and Redis with
connection strings set in a `.env` file (`DATABASE_URL`, `REDIS_URL`, and API
keys for the LLM and search provider).

```sh
make install       # install dependencies
make generate      # generate the Prisma client
make migrate       # apply database migrations
```

Then start the two processes in separate terminals:

```sh
make dev-backend   # FastAPI server
make dev-worker    # background worker
```

The frontend is not built yet. Until it is, the chat session can be driven
through the backend API directly.

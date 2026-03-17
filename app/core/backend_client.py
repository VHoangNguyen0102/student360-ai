"""
Backend Client — async HTTP client to call NestJS internal APIs.
Used by tools that need to read business data (jars, transactions, profile...).

Rule: AI service NEVER writes directly to business tables.
      All writes go through NestJS APIs.
"""
# TODO: Phase 1A — implement (httpx.AsyncClient)

"""Paginated browser control-plane endpoints with transaction-scoped authorization."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request

from .console_queries import ConsoleQueries
from .routes_retrieval import context, envelope, workspace


def console_router(services):
    queries = ConsoleQueries(services.db, services.auth)
    router = APIRouter()
    team = APIRouter(prefix="/v1/workspaces/{workspace_id}", dependencies=[Depends(workspace)])

    @team.get("/jobs", tags=["workbench"])
    def jobs(request: Request, knowledge_base_id: str, status: Optional[Literal[
            "queued", "parsing", "cancel_requested", "cancelled", "failed", "needs_review",
            "awaiting_publish", "publishing", "ready"]] = None,
            cursor: str = "", limit: int = Query(20, ge=1, le=100)):
        return envelope(request, queries.jobs(context(request), knowledge_base_id, status, cursor, limit))

    @team.get("/review-queue", tags=["workbench"])
    def reviews(request: Request, knowledge_base_id: str, cursor: str = "", limit: int = Query(20, ge=1, le=100)):
        return envelope(request, queries.reviews(context(request), knowledge_base_id, cursor, limit))

    @team.get("/documents/{book_id}/revisions", tags=["workbench"])
    def revisions(book_id: str, request: Request, cursor: str = "", limit: int = Query(20, ge=1, le=100)):
        return envelope(request, queries.revisions(context(request), book_id, cursor, limit))

    @team.get("/knowledge-bases/{kb_id}/members", tags=["admin"])
    def members(kb_id: str, request: Request, cursor: str = "", limit: int = Query(20, ge=1, le=100)):
        return envelope(request, queries.members(context(request), kb_id, cursor, limit))

    @router.get("/v1/users", tags=["admin"])
    def users(request: Request, cursor: str = "", limit: int = Query(20, ge=1, le=100)):
        return envelope(request, queries.users(context(request), cursor, limit))

    @router.get("/v1/tokens", tags=["identity"])
    def tokens(request: Request, cursor: str = "", limit: int = Query(20, ge=1, le=100)):
        return envelope(request, queries.tokens(context(request), cursor, limit))

    router.include_router(team)
    return router

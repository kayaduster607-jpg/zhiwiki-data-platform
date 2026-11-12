"""Small, authorized read models for the team workbench; never return credentials."""

import json

from .common import ServiceError, digest, encode
from .cursors import decode_scoped, issue_scoped


JOB_STATES = (
    "queued", "parsing", "cancel_requested", "cancelled", "failed",
    "needs_review", "awaiting_publish", "publishing", "ready",
)


class ConsoleQueries:
    def __init__(self, database, authorization):
        self.db, self.auth = database, authorization

    def session(self, connection, principal):
        """Control-plane lists are for browser sessions, not Agent tokens."""
        current = self.auth.current(connection, principal)
        if current["kind"] != "session":
            raise ServiceError(403, "PERMISSION_DENIED")
        return current

    def library(self, connection, principal, kb_id):
        current = self.session(connection, principal)
        self.auth.require(connection, current, [kb_id], "ingest", "editor")
        epoch = connection.execute("SELECT acl_epoch FROM team_kbs WHERE id=?", (kb_id,)).fetchone()[0]
        return current, epoch

    def page(self, connection, current, scope, cursor, limit, sql, parameters):
        """Only constant SQL fragments reach here; all external values are bound."""
        query_identity = digest(encode(scope))
        after = decode_scoped(self.db.cursor_key, cursor, current["id"], query_identity, limit) if cursor else ""
        rows = connection.execute(sql, [*parameters, after, limit + 1]).fetchall()
        visible = [dict(row) for row in rows[:limit]]
        following = issue_scoped(self.db.cursor_key, current["id"], query_identity, visible[-1]["id"], limit) if len(rows) > limit else None
        return visible, following

    def jobs(self, principal, kb_id, status, cursor, limit):
        with self.db.tx() as connection:
            current, epoch = self.library(connection, principal, kb_id)
            # Match Jobs.get: another owner's tasks require current editor rights.
            scope = ["jobs", "default", kb_id, status, epoch]
            state_filter = " AND j.status=?" if status else ""
            parameters = [kb_id, *([status] if status else [])]
            rows, following = self.page(connection, current, scope, cursor, limit,
                "SELECT j.id,j.id AS job_id,j.revision_id,j.status,j.pages_total,j.pages_done,j.attempt,"
                "j.updated AS updated_at,j.error,r.book_id AS document_id,r.number AS revision_number,"
                "r.status AS revision_status,r.quality AS quality_summary,b.title,b.source_key,b.current_revision "
                "FROM team_jobs j JOIN team_revisions r ON r.id=j.revision_id "
                "JOIN team_books b ON b.id=r.book_id WHERE j.kb_id=?" + state_filter +
                " AND j.id>? ORDER BY j.id LIMIT ?", parameters)
        for row in rows:
            row["quality_summary"] = json.loads(row["quality_summary"])
        return {"jobs": rows, "next_cursor": following}

    def reviews(self, principal, kb_id, cursor, limit):
        with self.db.tx() as connection:
            current, epoch = self.library(connection, principal, kb_id)
            rows, following = self.page(connection, current, ["reviews", "default", kb_id, epoch], cursor, limit,
                "SELECT r.id,r.id AS revision_id,r.book_id AS document_id,r.number,r.status,r.reviewed,"
                "r.quality,b.title,b.source_key,b.current_revision,"
                "(SELECT j.id FROM team_jobs j WHERE j.revision_id=r.id ORDER BY j.id DESC LIMIT 1) AS job_id "
                "FROM team_revisions r JOIN team_books b ON b.id=r.book_id "
                "WHERE b.kb_id=? AND r.status IN ('needs_review','awaiting_publish') "
                "AND r.id>? ORDER BY r.id LIMIT ?", [kb_id])
        for row in rows:
            row["quality"] = json.loads(row["quality"])
            row["reviewed"] = bool(row["reviewed"])
        return {"revisions": rows, "next_cursor": following}

    def revisions(self, principal, book_id, cursor, limit):
        with self.db.tx() as connection:
            book = connection.execute("SELECT kb_id,current_revision FROM team_books WHERE id=?", (book_id,)).fetchone()
            if not book:
                raise ServiceError(404, "RESOURCE_NOT_FOUND")
            current, epoch = self.library(connection, principal, book["kb_id"])
            rows, following = self.page(connection, current, ["revisions", "default", book_id, epoch], cursor, limit,
                "SELECT r.id,r.id AS revision_id,r.number,r.status,r.reviewed,r.filename,r.created,"
                "(SELECT COUNT(*) FROM team_pages p WHERE p.revision_id=r.id) AS page_count "
                "FROM team_revisions r WHERE r.book_id=? AND r.id>? ORDER BY r.id LIMIT ?", [book_id])
        for row in rows:
            row["reviewed"] = bool(row["reviewed"])
        return {"revisions": rows, "current_revision": book["current_revision"], "next_cursor": following}

    def users(self, principal, cursor, limit):
        with self.db.tx() as connection:
            current = self.auth.admin(connection, principal)
            rows, following = self.page(connection, current, ["users"], cursor, limit,
                "SELECT id,username,admin,disabled FROM team_users WHERE id>? ORDER BY id LIMIT ?", [])
        for row in rows:
            row["admin"], row["disabled"] = bool(row["admin"]), bool(row["disabled"])
        return {"users": rows, "next_cursor": following}

    def members(self, principal, kb_id, cursor, limit):
        with self.db.tx() as connection:
            current = self.auth.admin(connection, principal)
            kb = connection.execute("SELECT acl_epoch FROM team_kbs WHERE id=?", (kb_id,)).fetchone()
            if not kb:
                raise ServiceError(404, "RESOURCE_NOT_FOUND")
            rows, following = self.page(connection, current, ["members", "default", kb_id, kb[0]], cursor, limit,
                "SELECT u.id,u.username,u.disabled,g.role FROM team_grants g "
                "JOIN team_users u ON u.id=g.user_id WHERE g.kb_id=? AND u.id>? ORDER BY u.id LIMIT ?", [kb_id])
        for row in rows:
            row["disabled"] = bool(row["disabled"])
        return {"members": rows, "next_cursor": following}

    def tokens(self, principal, cursor, limit):
        with self.db.tx() as connection:
            current = self.session(connection, principal)
            rows, following = self.page(connection, current, ["tokens"], cursor, limit,
                "SELECT hash AS id,hash AS token_id,scopes,kb_ids AS knowledge_base_ids,expires AS expires_at,"
                "created AS created_at,revoked FROM team_tokens WHERE user_id=? AND kind='token' "
                "AND hash>? ORDER BY hash LIMIT ?", [current["id"]])
        for row in rows:
            row["scopes"] = json.loads(row["scopes"])
            row["knowledge_base_ids"] = json.loads(row["knowledge_base_ids"])
            row["revoked"] = bool(row["revoked"])
        return {"tokens": rows, "next_cursor": following}

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.db import get_db_connection

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    region: Optional[str] = None,
    days: Optional[int] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where = []
    params = []

    if region:
        where.append('"Region" = %s')
        params.append(region)

    if days:
        where.append('"PostedDate" >= NOW() - (%s || \' days\')::interval')
        params.append(days)

    if is_active is not None:
        where.append('"IsActive" = %s')
        params.append(is_active)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f'''
        SELECT *
        FROM "seek_jobs"
        {where_sql}
        ORDER BY "PostedDate" DESC NULLS LAST
        LIMIT %s OFFSET %s
    '''
    params.extend([limit, offset])

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return {
        "items": rows,
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{job_id}")
def get_job(job_id: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM "seek_jobs" WHERE "Id" = %s', (job_id,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return row
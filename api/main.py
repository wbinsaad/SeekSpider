import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

# Configuration
DATABASE_ENGINE = (os.getenv('DATABASE_ENGINE') or 'postgres').strip().lower()
SQLITE_DB_PATH = os.getenv('SQLITE_DB_PATH')

DB_HOST = os.getenv('POSTGRES_HOST') or os.getenv('POSTGRESQL_HOST') or 'postgres'
DB_PORT = int((os.getenv('POSTGRES_PORT') or os.getenv('POSTGRESQL_PORT') or 5432))
DB_USER = os.getenv('POSTGRES_USER') or os.getenv('POSTGRESQL_USER') or 'seekuser'
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD') or os.getenv('POSTGRESQL_PASSWORD') or 'seekpass'
DB_NAME = os.getenv('POSTGRES_DB') or os.getenv('POSTGRESQL_DATABASE') or 'seekdb'
DB_TABLE = (
    os.getenv('DATABASE_TABLE')
    or os.getenv('POSTGRES_TABLE')
    or os.getenv('POSTGRESQL_TABLE')
    or 'seek_jobs'
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Seek Jobs API", version="1.0.0", description="Read-only API for Seek job listings")


# Models
class JobItem(BaseModel):
    id: str
    job_title: Optional[str]
    business_name: Optional[str]
    work_type: Optional[str]
    pay_range: Optional[str]
    suburb: Optional[str]
    area: Optional[str]
    region: Optional[str]
    url: Optional[str]
    advertiser_id: Optional[str]
    job_type: Optional[str]
    posted_date: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_active: Optional[bool]
    is_new: Optional[bool]

    class Config:
        from_attributes = True


class JobsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobItem]


class RegionResponse(BaseModel):
    regions: list[str]


# Database connection helper
def get_db_connection():
    """Create a new database connection"""
    try:
        if DATABASE_ENGINE == 'sqlite':
            if not SQLITE_DB_PATH:
                raise ValueError('SQLITE_DB_PATH is required when DATABASE_ENGINE=sqlite')

            project_root = Path(__file__).resolve().parents[1]
            sqlite_path = Path(SQLITE_DB_PATH)
            if not sqlite_path.is_absolute():
                sqlite_path = project_root / sqlite_path

            conn = sqlite3.connect(sqlite_path)
            conn.row_factory = sqlite3.Row
            return conn

        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursor_factory=RealDictCursor
        )
        conn.set_session(autocommit=True)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


def execute_query(sql: str, params=None, fetch: str = 'all'):
    """Execute a query with engine-aware placeholders and row conversion."""
    params = tuple(params or ())
    query = sql.replace('%s', '?') if DATABASE_ENGINE == 'sqlite' else sql

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if fetch == 'none':
            return None

        if fetch == 'one':
            row = cursor.fetchone()
            if row is None:
                return None
            if DATABASE_ENGINE == 'sqlite':
                return dict(row)
            return row

        rows = cursor.fetchall()
        if DATABASE_ENGINE == 'sqlite':
            return [dict(row) for row in rows]
        return rows
    finally:
        cursor.close()
        conn.close()


# Routes
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        execute_query("SELECT 1", fetch='one')
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database connection failed")


@app.get("/regions", response_model=RegionResponse)
async def get_regions():
    """Get list of available regions"""
    try:
        rows = execute_query(
            f'SELECT DISTINCT "Region" FROM "{DB_TABLE}" WHERE "Region" IS NOT NULL ORDER BY "Region"'
        )
        regions = [row['Region'] for row in rows]
        
        return {"regions": regions}
    except Exception as e:
        logger.error(f"Failed to get regions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve regions")


@app.get("/jobs", response_model=JobsResponse)
async def get_jobs(
    region: Optional[str] = Query(None, description="Filter by region"),
    search: Optional[str] = Query(None, description="Search in job title and business name"),
    work_type: Optional[str] = Query(None, description="Filter by work type"),
    date_field: Optional[str] = Query(None, regex="^(posted_date|created_at|updated_at)$", description="Date field for date filtering"),
    date_from: Optional[datetime] = Query(None, description="Filter records with selected date field >= this datetime (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Filter records with selected date field <= this datetime (ISO 8601)"),
    limit: int = Query(20, ge=1, le=100, description="Number of results (max 100)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("posted_date", regex="^(posted_date|created_at|updated_at)$", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """
    Get jobs with optional filters and pagination.
    
    Parameters:
    - region: Filter by region (e.g., Melbourne, Perth)
    - search: Search in job titles and business names
    - work_type: Filter by work type
    - date_field: Date field used for date filtering (posted_date, created_at, updated_at)
    - date_from: Inclusive lower bound datetime for selected date field
    - date_to: Inclusive upper bound datetime for selected date field
    - limit: Number of results (default 20, max 100)
    - offset: Pagination offset (default 0)
    - sort_by: Sort field (posted_date, created_at, updated_at)
    - sort_order: Sort order (asc or desc)
    - is_active: Filter by active status (true/false)
    """
    try:
        # Build WHERE clause
        conditions = []
        params = []
        
        if region:
            conditions.append('"Region" = %s')
            params.append(region)
        
        if search:
            search_term = f"%{search}%"
            if DATABASE_ENGINE == 'sqlite':
                conditions.append('(LOWER("JobTitle") LIKE LOWER(%s) OR LOWER("BusinessName") LIKE LOWER(%s))')
            else:
                conditions.append('("JobTitle" ILIKE %s OR "BusinessName" ILIKE %s)')
            params.extend([search_term, search_term])
        
        if work_type:
            conditions.append('"WorkType" = %s')
            params.append(work_type)

        date_column_map = {
            "posted_date": '"PostedDate"',
            "created_at": '"CreatedAt"',
            "updated_at": '"UpdatedAt"'
        }
        selected_date_column = date_column_map.get(date_field) if date_field else None

        if date_from:
            filter_column = selected_date_column or '"PostedDate"'
            conditions.append(f"{filter_column} >= %s")
            params.append(date_from)

        if date_to:
            filter_column = selected_date_column or '"PostedDate"'
            conditions.append(f"{filter_column} <= %s")
            params.append(date_to)
        
        if is_active is not None:
            conditions.append('"IsActive" = %s')
            params.append(is_active)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Map sort_by to actual column names (handle snake_case from API)
        sort_column_map = {
            "posted_date": '"PostedDate"',
            "created_at": '"CreatedAt"',
            "updated_at": '"UpdatedAt"'
        }
        sort_column = sort_column_map.get(sort_by, '"PostedDate"')
        sort_order_sql = "DESC" if sort_order == "desc" else "ASC"
        
        # Get total count
        count_sql = f'SELECT COUNT(*) as total FROM "{DB_TABLE}" WHERE {where_clause}'
        total = execute_query(count_sql, params, fetch='one')['total']
        
        # Get paginated results
        if DATABASE_ENGINE == 'sqlite':
            order_clause = f'ORDER BY ({sort_column} IS NULL) ASC, {sort_column} {sort_order_sql}'
        else:
            order_clause = f'ORDER BY {sort_column} {sort_order_sql} NULLS LAST'

        query_sql = f"""
            SELECT 
                "Id" as id,
                "JobTitle" as job_title,
                "BusinessName" as business_name,
                "WorkType" as work_type,
                "PayRange" as pay_range,
                "Suburb" as suburb,
                "Area" as area,
                "Region" as region,
                "Url" as url,
                "AdvertiserId" as advertiser_id,
                "JobType" as job_type,
                "PostedDate" as posted_date,
                "CreatedAt" as created_at,
                "UpdatedAt" as updated_at,
                "IsActive" as is_active,
                "IsNew" as is_new
            FROM "{DB_TABLE}"
            WHERE {where_clause}
            {order_clause}
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        rows = execute_query(query_sql, params)
        
        items = [JobItem(**row) for row in rows]
        
        return JobsResponse(total=total, limit=limit, offset=offset, items=items)
    
    except Exception as e:
        logger.error(f"Failed to get jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve jobs")


@app.get("/jobs/{job_id}", response_model=JobItem)
async def get_job(job_id: str):
    """Get a specific job by ID"""
    try:
        query_sql = f"""
            SELECT 
                "Id" as id,
                "JobTitle" as job_title,
                "BusinessName" as business_name,
                "WorkType" as work_type,
                "PayRange" as pay_range,
                "Suburb" as suburb,
                "Area" as area,
                "Region" as region,
                "Url" as url,
                "AdvertiserId" as advertiser_id,
                "JobType" as job_type,
                "PostedDate" as posted_date,
                "CreatedAt" as created_at,
                "UpdatedAt" as updated_at,
                "IsActive" as is_active,
                "IsNew" as is_new
            FROM "{DB_TABLE}"
            WHERE "Id" = %s
        """
        row = execute_query(query_sql, (job_id,), fetch='one')
        
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return JobItem(**row)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job")


@app.get("/")
async def root():
    """API root endpoint with documentation link"""
    return {
        "message": "Seek Jobs API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "jobs": "/jobs",
            "job_by_id": "/jobs/{job_id}",
            "regions": "/regions"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

"""
Seek Job Spider Pipeline

Scrapes job listings from Seek.com.au for IT positions.
"""

import asyncio
import sys
import os
import signal
from typing import Literal, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from dateutil import tz

import psycopg2
from apscheduler.triggers.cron import CronTrigger
from plombery import register_pipeline, task, Trigger, get_logger
from plombery.pipeline.context import run_context

# Global dictionary to track running processes by run_id
_running_processes: Dict[int, asyncio.subprocess.Process] = {}


def get_running_process(run_id: int):
    """Get the running process for a specific run_id"""
    return _running_processes.get(run_id)

# Get project directories
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SCRAPER_DIR = os.path.join(PROJECT_ROOT, "scraper")

# Australian regions
REGIONS = Literal[
    "Perth",
    "Sydney",
    "Melbourne",
    "Brisbane",
    "Gold Coast",
    "Adelaide",
    "Canberra",
    "Hobart",
    "Darwin",
]

# Job classifications
CLASSIFICATIONS = Literal[
    "6281",  # Information & Communication Technology
    "1200",  # Accounting
    "6251",  # Banking & Financial Services
    "6304",  # Engineering
    "6317",  # Healthcare & Medical
]


class SeekSpiderParams(BaseModel):
    """Parameters for Seek Spider"""

    region: REGIONS = Field(
        default="Melbourne",
        description="Australian region to search for jobs"
    )
    classification: CLASSIFICATIONS = Field(
        default="6281",
        description="Job classification (6281=IT, 1200=Accounting, 6304=Engineering)"
    )
    run_post_processing: bool = Field(
        default=True,
        description="Run AI-powered post-processing (requires AI API configuration)"
    )
    concurrent_requests: int = Field(
        default=16,
        ge=1,
        le=32,
        description="Number of concurrent requests"
    )
    download_delay: float = Field(
        default=2.0,
        ge=0.5,
        le=10.0,
        description="Delay between requests in seconds"
    )


@task
async def run_seek_spider(params: SeekSpiderParams) -> dict:
    """Run the Seek job spider using subprocess"""

    logger = get_logger()
    logger.info("Starting Seek Spider")
    logger.info(f"Parameters: region={params.region}, classification={params.classification}")
    logger.info(f"Post-processing enabled: {params.run_post_processing}")

    # Get current run_id from context
    pipeline_run = run_context.get()
    run_id = pipeline_run.id if pipeline_run else None

    process = None
    try:
        # Set up environment
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{PROJECT_ROOT}:{SCRAPER_DIR}:{env.get('PYTHONPATH', '')}"
        env['SCRAPY_SETTINGS_MODULE'] = 'SeekSpider.settings'

        # Build scrapy command with spider arguments (using region instead of location)
        cmd = [
            sys.executable, '-m', 'scrapy', 'crawl', 'seek',
            '-a', f'region={params.region}',
            '-a', f'classification={params.classification}',
            '-s', f'CONCURRENT_REQUESTS={params.concurrent_requests}',
            '-s', f'DOWNLOAD_DELAY={params.download_delay}',
            '-s', 'LOG_LEVEL=INFO',
        ]

        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"Working directory: {SCRAPER_DIR}")

        # Run the spider using async subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=SCRAPER_DIR,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # Register the process if we have a run_id
        if run_id:
            _running_processes[run_id] = process
            logger.info(f"Registered process for run #{run_id} (PID: {process.pid})")

        # Stream output to logger asynchronously
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line = line.decode('utf-8').strip()
            if line:
                logger.info(line)

        # Wait for process to complete
        return_code = await process.wait()

        if return_code != 0:
            # Check if it was cancelled
            if return_code == -signal.SIGTERM or return_code == -signal.SIGKILL:
                logger.info(f"Spider was cancelled (return code: {return_code})")
                return {
                    "status": "cancelled",
                    "message": "Spider was cancelled by user",
                    "timestamp": datetime.now().isoformat()
                }

            return {
                "status": "error",
                "error": f"Spider exited with code {return_code}",
                "timestamp": datetime.now().isoformat()
            }

        result = {
            "status": "success",
            "message": "Seek Spider completed successfully",
            "region": params.region,
            "classification": params.classification,
            "post_processing": params.run_post_processing,
            "timestamp": datetime.now().isoformat()
        }

        logger.info("Seek Spider completed successfully")
        return result

    except asyncio.CancelledError:
        # Task was cancelled
        logger.info("Task was cancelled")
        if process and process.returncode is None:
            logger.info(f"Terminating process PID: {process.pid}")
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Process did not terminate gracefully, killing PID: {process.pid}")
                process.kill()
                await process.wait()

        # Re-raise the exception so executor marks the task as cancelled
        raise

    except Exception as e:
        logger.error(f"Seek Spider failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

    finally:
        # Always unregister the process
        if run_id and run_id in _running_processes:
            del _running_processes[run_id]
            logger.info(f"Unregistered process for run #{run_id}")


# Perth timezone for all Australian regions
PERTH_TZ = tz.gettz("Australia/Perth")

register_pipeline(
    id="seek_spider",
    description="Scrape job listings from Seek.com.au",
    tasks=[run_seek_spider],
    params=SeekSpiderParams,
    triggers=[

        # Melbourne - Daily 09 AM
        Trigger(
            id="melbourne_daily_09am",
            name="Melbourne Daily 09 AM",
            description="Scrape Melbourne IT jobs at 09:00 AM",
            params=SeekSpiderParams(
                region="Melbourne",
                classification="6281",
                run_post_processing=True,
            ),
            schedule=CronTrigger(hour=9, minute=00, timezone=PERTH_TZ),
        ),

        # Melbourne - Daily 12 PM
        Trigger(
            id="melbourne_daily_12pm",
            name="Melbourne Daily 12 PM",
            description="Scrape Melbourne IT jobs at 12:45 PM",
            params=SeekSpiderParams(
                region="Melbourne",
                classification="6281",
                run_post_processing=True,
            ),
            schedule=CronTrigger(hour=12, minute=45, timezone=PERTH_TZ),
        ),

        # Melbourne - Daily 05 PM
        Trigger(
            id="melbourne_daily_05pm",
            name="Melbourne Daily 05 PM",
            description="Scrape Melbourne IT jobs at 05:25 PM",
            params=SeekSpiderParams(
                region="Melbourne",
                classification="6281",
                run_post_processing=True,
            ),
            schedule=CronTrigger(hour=17, minute=25, timezone=PERTH_TZ),
        ),

        # Melbourne - Daily 10 PM
        Trigger(
            id="melbourne_daily_10pm",
            name="Melbourne Daily 10 PM",
            description="Scrape Melbourne IT jobs at 10:25 PM",
            params=SeekSpiderParams(
                region="Melbourne",
                classification="6281",
                run_post_processing=True,
            ),
            schedule=CronTrigger(hour=22, minute=25, timezone=PERTH_TZ),
        ),
    ],
)


# ============================================================================
# Backfill Job Descriptions Pipeline
# ============================================================================

class BackfillParams(BaseModel):
    """Parameters for Backfill Job Descriptions task"""

    limit: Optional[int] = Field(
        default=None,
        description="Maximum number of jobs to process (default: no limit)",
        ge=1,
    )
    delay: float = Field(
        default=5.0,
        ge=0.5,
        le=30.0,
        description="Base delay between requests in seconds"
    )
    headless: bool = Field(
        default=False,
        description="Run browser in headless mode (default: False for better success rate)"
    )
    workers: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Number of concurrent workers (1-5, default: 3)"
    )
    region: Optional[REGIONS] = Field(
        default=None,
        description="Region to process (if None, processes all regions; if specified, only processes that region)"
    )
    include_inactive: bool = Field(
        default=False,
        description="Include inactive jobs in backfill"
    )
    skip_ai: bool = Field(
        default=False,
        description="Skip AI analysis after backfill"
    )
    restart_interval: int = Field(
        default=30,
        ge=5,
        le=100,
        description="Restart Chrome driver every N jobs (only for serial mode)"
    )


@task
async def run_backfill(params: BackfillParams) -> dict:
    """Run the backfill script to fetch missing job descriptions"""

    logger = get_logger()
    logger.info("Starting Backfill Job Descriptions")
    logger.info(f"Parameters: limit={params.limit}, delay={params.delay}, workers={params.workers}")
    logger.info(f"Region filter: {params.region or 'All regions'}")
    logger.info(f"Headless mode: {params.headless}, Include inactive: {params.include_inactive}")

    # Get current run_id from context
    pipeline_run = run_context.get()
    run_id = pipeline_run.id if pipeline_run else None

    process = None
    try:
        # Set up environment
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{PROJECT_ROOT}:{SCRAPER_DIR}:{env.get('PYTHONPATH', '')}"

        # Build backfill command using module
        backfill_cwd = os.path.join(SCRAPER_DIR, 'SeekSpider')
        cmd = [sys.executable, '-m', 'backfill']

        if params.limit:
            cmd.extend(['--limit', str(params.limit)])

        cmd.extend(['--delay', str(params.delay)])
        cmd.extend(['--workers', str(params.workers)])
        cmd.extend(['--restart-interval', str(params.restart_interval)])

        if params.region:
            # Use region for both output organization and filtering
            cmd.extend(['--region', params.region])
            cmd.extend(['--region-filter', params.region])

        if params.headless:
            cmd.append('--headless')

        if params.include_inactive:
            cmd.append('--include-inactive')

        if params.skip_ai:
            cmd.append('--skip-ai')

        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"Working directory: {backfill_cwd}")

        # Run the backfill module using async subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=backfill_cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # Register the process if we have a run_id
        if run_id:
            _running_processes[run_id] = process
            logger.info(f"Registered process for run #{run_id} (PID: {process.pid})")

        # Stream output to logger asynchronously
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line = line.decode('utf-8').strip()
            if line:
                logger.info(line)

        # Wait for process to complete
        return_code = await process.wait()

        if return_code != 0:
            # Check if it was cancelled
            if return_code == -signal.SIGTERM or return_code == -signal.SIGKILL:
                logger.info(f"Backfill was cancelled (return code: {return_code})")
                return {
                    "status": "cancelled",
                    "message": "Backfill was cancelled by user",
                    "timestamp": datetime.now().isoformat()
                }

            return {
                "status": "error",
                "error": f"Backfill exited with code {return_code}",
                "timestamp": datetime.now().isoformat()
            }

        result = {
            "status": "success",
            "message": "Backfill completed successfully",
            "region": params.region or "All regions",
            "limit": params.limit,
            "timestamp": datetime.now().isoformat()
        }

        logger.info("Backfill completed successfully")
        return result

    except asyncio.CancelledError:
        # Task was cancelled
        logger.info("Task was cancelled")
        if process and process.returncode is None:
            logger.info(f"Terminating process PID: {process.pid}")
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Process did not terminate gracefully, killing PID: {process.pid}")
                process.kill()
                await process.wait()

        # Re-raise the exception so executor marks the task as cancelled
        raise

    except Exception as e:
        logger.error(f"Backfill failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

    finally:
        # Always unregister the process
        if run_id and run_id in _running_processes:
            del _running_processes[run_id]
            logger.info(f"Unregistered process for run #{run_id}")


register_pipeline(
    id="backfill_job_descriptions",
    description="Backfill missing job descriptions from Seek job pages (per region)",
    tasks=[run_backfill],
    params=BackfillParams,
    triggers=[

        # Melbourne - 9:15 AM
        Trigger(
            id="melbourne_9am",
            name="Melbourne 9:15 AM Backfill",
            description="Backfill missing job descriptions for Melbourne at 9:15 AM",
            params=BackfillParams(
                limit=None,
                delay=5.0,
                headless=True,
                region="Melbourne",
                include_inactive=False,
                skip_ai=False,
                restart_interval=30,
            ),
            schedule=CronTrigger(hour=9, minute=15, timezone=PERTH_TZ),
        ),
        # Melbourne - 12:35 PM
        Trigger(
            id="melbourne_12_35pm",
            name="Melbourne 12:35 PM Backfill",
            description="Backfill missing job descriptions for Melbourne at 12:35 PM",
            params=BackfillParams(
                limit=None,
                delay=5.0,
                headless=True,
                region="Melbourne",
                include_inactive=False,
                skip_ai=False,
                restart_interval=30,
            ),
            schedule=CronTrigger(hour=12, minute=35, timezone=PERTH_TZ),
        ),
        # Melbourne - 3:35 PM
        Trigger(
            id="melbourne_3_35pm",
            name="Melbourne 3:35 PM Backfill",
            description="Backfill missing job descriptions for Melbourne at 3:35 PM",
            params=BackfillParams(
                limit=None,
                delay=5.0,
                headless=True,
                region="Melbourne",
                include_inactive=False,
                skip_ai=False,
                restart_interval=30,
            ),
            schedule=CronTrigger(hour=15, minute=35, timezone=PERTH_TZ),
        ),
        # Melbourne - 5:35 PM
        Trigger(
            id="melbourne_5_35pm",
            name="Melbourne 5:35 PM Backfill",
            description="Backfill missing job descriptions for Melbourne at 5:35 PM",
            params=BackfillParams(
                limit=None,
                delay=5.0,
                headless=True,
                region="Melbourne",
                include_inactive=False,
                skip_ai=False,
                restart_interval=30,
            ),
            schedule=CronTrigger(hour=17, minute=35, timezone=PERTH_TZ),
        ),
        # Melbourne - 10:45 PM
        Trigger(
            id="melbourne_10pm",
            name="Melbourne 10:45 PM Backfill",
            description="Backfill missing job descriptions for Melbourne at 10:45 PM",
            params=BackfillParams(
                limit=None,
                delay=5.0,
                headless=True,
                region="Melbourne",
                include_inactive=False,
                skip_ai=False,
                restart_interval=30,
            ),
            schedule=CronTrigger(hour=22, minute=45, timezone=PERTH_TZ),
        ),

    ],
)

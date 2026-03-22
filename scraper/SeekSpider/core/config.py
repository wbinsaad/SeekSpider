import os
from pathlib import Path

from dotenv import load_dotenv


def _load_environment_file():
    """Load .env from common runtime locations and return the loaded path."""
    current_file = Path(__file__).resolve()
    scraper_root = current_file.parents[2]  # .../scraper
    project_root = current_file.parents[3]  # .../SeekSpider_Waleed

    candidate_paths = [
        Path.cwd() / '.env',
        scraper_root / '.env',
        project_root / '.env',
    ]

    seen = set()
    for env_path in candidate_paths:
        resolved = env_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)

        if env_path.is_file():
            load_dotenv(dotenv_path=env_path, override=False)
            return str(env_path)

    load_dotenv(override=False)
    return None


class Config:
    def __init__(self):
        self.ENV_FILE_PATH = _load_environment_file()

        # Database engine
        self.DATABASE_ENGINE = (os.getenv('DATABASE_ENGINE') or 'postgres').strip().lower()

        # Shared/normalized table name
        configured_table = (
            os.getenv('DATABASE_TABLE')
            or os.getenv('POSTGRESQL_TABLE')
            or os.getenv('POSTGRES_TABLE')
        )
        if self.DATABASE_ENGINE == 'postgres':
            self.DATABASE_TABLE = configured_table or 'seek_jobs'
        else:
            self.DATABASE_TABLE = configured_table

        # Database settings - support both naming conventions
        self.POSTGRESQL_HOST = os.getenv('POSTGRESQL_HOST') or os.getenv('POSTGRES_HOST')
        port = os.getenv('POSTGRESQL_PORT') or os.getenv('POSTGRES_PORT')
        if not port and self.DATABASE_ENGINE == 'postgres':
            port = '5432'
        self.POSTGRESQL_PORT = self._safe_int(port)
        self.POSTGRESQL_USER = os.getenv('POSTGRESQL_USER') or os.getenv('POSTGRES_USER')
        self.POSTGRESQL_PASSWORD = os.getenv('POSTGRESQL_PASSWORD') or os.getenv('POSTGRES_PASSWORD')
        self.POSTGRESQL_DATABASE = os.getenv('POSTGRESQL_DATABASE') or os.getenv('POSTGRES_DB')
        self.POSTGRESQL_TABLE = self.DATABASE_TABLE

        # SQLite settings
        self.SQLITE_DB_PATH = os.getenv('SQLITE_DB_PATH')

    @staticmethod
    def _safe_int(value):
        if value in (None, ''):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


    def validate(self):
        """Validate required configuration fields"""
        if self.DATABASE_ENGINE not in {'postgres', 'sqlite'}:
            raise ValueError('DATABASE_ENGINE must be either "postgres" or "sqlite"')

        if self.DATABASE_ENGINE == 'sqlite':
            required_fields = [
                'SQLITE_DB_PATH',
                'DATABASE_TABLE',
            ]
        else:
            required_fields = [
                'POSTGRESQL_HOST',
                'POSTGRESQL_PORT',
                'POSTGRESQL_USER',
                'POSTGRESQL_PASSWORD',
                'POSTGRESQL_DATABASE',
                'DATABASE_TABLE',
            ]

        missing_fields = []
        for field in required_fields:
            if not getattr(self, field):
                missing_fields.append(field)

        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")


config = Config()

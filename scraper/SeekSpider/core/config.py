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

        # Database settings - support both naming conventions
        self.POSTGRESQL_HOST = os.getenv('POSTGRESQL_HOST') or os.getenv('POSTGRES_HOST')
        port = os.getenv('POSTGRESQL_PORT') or os.getenv('POSTGRES_PORT') or '5432'
        self.POSTGRESQL_PORT = int(port)
        self.POSTGRESQL_USER = os.getenv('POSTGRESQL_USER') or os.getenv('POSTGRES_USER')
        self.POSTGRESQL_PASSWORD = os.getenv('POSTGRESQL_PASSWORD') or os.getenv('POSTGRES_PASSWORD')
        self.POSTGRESQL_DATABASE = os.getenv('POSTGRESQL_DATABASE') or os.getenv('POSTGRES_DB')
        self.POSTGRESQL_TABLE = os.getenv('POSTGRESQL_TABLE', 'seek_jobs')


    def validate(self):
        """Validate required configuration fields"""
        required_fields = [
            'POSTGRESQL_HOST',
            'POSTGRESQL_PORT',
            'POSTGRESQL_USER',
            'POSTGRESQL_PASSWORD',
            'POSTGRESQL_DATABASE',
            'POSTGRESQL_TABLE',
        ]

        missing_fields = []
        for field in required_fields:
            if not getattr(self, field):
                missing_fields.append(field)

        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")


config = Config()

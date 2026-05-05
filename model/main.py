import logging

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

# load in app user-agent or any other app config
app = FastAPI()

# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/{full_path:path}")
def deprecated(request: Request, full_path: str):
    """All endpoints return same deprecation message."""
    deprecation_message = ("wiki-search-referrals.wmcloud.org has been deprecated. "
                           "For more details, see: https://wikitech.wikimedia.org/wiki/Data_Platform/Data_Lake/Traffic/referrer_daily/Dashboard. "
                           "If you have questions, you may reach out to https://meta.wikimedia.org/wiki/User:Isaac_(WMF).")
    return {"error": deprecation_message}


if __name__ == '__main__':
    app.run()
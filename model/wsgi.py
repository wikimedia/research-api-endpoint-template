import logging
import os

from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)


# Enable CORS for API endpoints
cors = CORS(app, resources={r'/*': {'origins': '*'}})

@app.route('/', methods=['GET'], defaults={'u_path': ''})
@app.route('/<path:u_path>', methods=['GET'])
def deprecated(u_path):
    """All endpoints return same deprecation message."""
    deprecation_message = ("wiki-search-referrals.wmcloud.org has been deprecated. "
                           "For more details, see: https://wikitech.wikimedia.org/wiki/Data_Platform/Data_Lake/Traffic/referrer_daily/Dashboard. "
                           "If you have questions, you may reach out to https://meta.wikimedia.org/wiki/User:Isaac_(WMF).")
    return jsonify({"error": deprecation_message})


if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
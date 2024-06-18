import logging
import os

from flask import Flask, request, jsonify
from flask_cors import CORS
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/*': {'origins': '*'}})

@app.route('/', methods=['GET'], defaults={'u_path': ''})
@app.route('/<path:u_path>', methods=['GET'])
def deprecated(u_path):
    """All endpoints return same deprecation message."""
    deprecation_message = ("GapFinder has been deprecated. "
                           "Background: https://phabricator.wikimedia.org/T367549. "
                           "For the API, please use the LiftWing endpoint. "
                           "Documentation: https://api.wikimedia.org/wiki/Lift_Wing_API/Reference/Get_content_translation_recommendation. "
                           "Example migration: https://es.wikipedia.org/w/index.php?title=MediaWiki:Gadget-WikiProject.js&diff=prev&oldid=160820835. "
                           "For the UI, please use Content Translation: "
                           "https://www.mediawiki.org/wiki/Content_translation#Try_the_tool")
    return jsonify({"error": deprecation_message})


if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
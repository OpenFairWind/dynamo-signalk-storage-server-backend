import logging
import os
import json

from sqlalchemy import create_engine, MetaData
from flask import Flask

from os.path import isfile

from flask_cors import CORS


# Create the logger
log = logging.getLogger('app')

# Set the default logger level as debug
log.setLevel(logging.DEBUG)

# Create the logger formatter
fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s')

# Get the handler
h = logging.StreamHandler()

# Set the formatter
h.setFormatter(fmt)

# Add the handler to the logger
log.addHandler(h)

flask_app = None


def create_app() -> Flask:
    app_root = os.getcwd()

    # Log a debug message
    log.debug("App root:" + app_root)

    # Create the Flask application
    app = Flask(__name__)

    # Set the api enabled for cross server invocation
    CORS(app)

    # Check if the file config.json exists
    if not isfile(app_root + os.sep + 'config.json'):
        log.error("Missing config.json file"),
        exit(-1)

    # Configure the application from the config file
    app.config.from_file(app_root + os.sep + "config.json", load=json.load)

    # Override config.json configuration with environmental variables
    app.config.from_prefixed_env()

    # Log a debug message
    log.debug("app.config: " + str(app.config))

    # Check if the database backend is up and running

    # Connect the database server
    engine = create_engine(app.config["CONNECTION_STRING"], echo=False)

    # Retrieve the metadata
    metadata = MetaData()

    try:
        # Create the actual connection
        metadata.create_all(engine)

    except Exception as exception:
        # Log the error message
        log.error("Database connection error. Check the connection string: " +
                  app.config["CONNECTION_STRING"] + ": " +
                  str(exception))

        # Exit with error code
        exit(-1)

    # Log the info message
    log.info("Private key: " + app.config['PRIVATE_KEY_FILENAME'])
    log.info("Public key: " + app.config['PUBLIC_KEY_FILENAME'])
    log.info("Public key directory root: " + app.config['PUBLIC_KEY_ROOT'])
    log.info("Database connection string: " + app.config['CONNECTION_STRING'])

    with app.app_context():
        from . import routes

    return app


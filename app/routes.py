import logging
import os
import tempfile
import xml.etree.cElementTree as ET

from flask import current_app, send_file, render_template, request, Response
from sqlalchemy import create_engine, text
from werkzeug.datastructures import FileStorage
from datetime import datetime, timedelta

from flask import request, jsonify
from flask_restx import Api, Resource, fields
from flask_httpauth import HTTPBasicAuth

# Create the logger
log = logging.getLogger('routes')

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

# Create the api object using restx
api = Api(current_app)

publickey_model = api.model("publickey", {
    "key": fields.String,
})

# Get the HTTP Basic Authentication object
auth = HTTPBasicAuth()

log.debug("Routes")


@api.route('/publickey')
class PublicKey(Resource):
    def get(self):

        # Push the application context
        with current_app.app_context():

            # Log a debug message
            log.debug("PUBLIC_KEY_FILENAME:" + current_app.config["PUBLIC_KEY_FILENAME"])

            # Get the public key filename
            public_key_filename = current_app.config["PUBLIC_KEY_FILENAME"]

            # Check if the filename is relative
            if not os.path.isabs(public_key_filename):

                # Move one directory level up
                public_key_filename = ".." + os.sep + public_key_filename

            return send_file(public_key_filename, as_attachment=True)


@auth.verify_password
def authenticate(username, password):
    if username and password:
        if username == 'admin' and password == 'password':
            return True

        if username == 'user' and password == 'password':
            return True

    return False


# Create an api parser for public key upload
upload_publickey_parser = api.parser()

# Add parser for file storage
upload_publickey_parser.add_argument('file', location='files', type=FileStorage, required=True,
                                     help='DYNAMO Public Key -public.pem file')


@api.route('/upload/publickey/<string:self_id>')
@api.expect(publickey_model)
class PublicKeyUpload(Resource):
    @auth.login_required
    def post(self, self_id):

        json_data = request.get_json(force=True)
        public_key = json_data['key']

        # Push the application context
        with current_app.app_context():

            # Get the public key root
            public_key_root = current_app.config["PUBLIC_KEY_ROOT"]

            # Check if self_id starts with "vessels."
            if not self_id.startswith("vessels."):

                # Add the vessels prefix
                self_id = "vessels." + self_id

            # Compose the destination file path name
            file_path = os.path.join(public_key_root, self_id + "-public.pem")

            with open(file_path, 'w') as f:
                f.write(public_key)

            # Log the status
            log.debug("Saved public key as: " + file_path)

            return {"result": "ok", "user": auth.current_user()}, 200


@api.route('/lastPosition')
class LastPosition(Resource):
    def get(self):
        positions = []

        connection_string = current_app.config["CONNECTION_STRING"]
        engine = create_engine(connection_string, echo=False)
        conn = engine.connect()

        try:
            sql_string = "SELECT ctx.context, pos.timestamp, ctx.value as info, pos.position FROM public.context ctx, "\
                         "(SELECT context, timestamp, value as position FROM public.navigation_position np1 WHERE timestamp = "\
                         "(SELECT MAX(np2.timestamp) FROM public.navigation_position np2 WHERE np1.context = np2.context) "\
                         "ORDER BY context) pos WHERE ctx.context = pos.context LIMIT 1;"
            result = conn.execute(text(sql_string))
            for row in result:
                positions.append({
                    "id": row[0].split(":")[-1],
                    "timestamp": str(row[1]),
                    "info": row[2],
                    "position": row[3]
                })
            conn.close()
        except Exception as exception:
            log.error("SQL: " + str(exception))
            conn.close()

        return positions


@api.route('/position/<string:self_id>')
class Position(Resource):
    def get(self, self_id):
        # Check if self_id starts with "vessels."
        if not self_id.startswith("vessels."):
            # Add the vessels prefix
            self_id = "vessels." + self_id

        query = "SELECT * FROM public.navigation_position WHERE context='" + self_id + "' "

        connection_string = current_app.config["CONNECTION_STRING"]
        engine = create_engine(connection_string, echo=False)
        conn = engine.connect()

        gpx = ET.Element("gpx", attrib={"xmlns": "http://www.topografix.com/GPX/1/1"})
        trk = ET.SubElement(gpx, "trk")
        trkseg = ET.SubElement(trk, "trkseg")

        start = request.args.get('start')
        end = request.args.get('end')
        hours = request.args.get('hours')
        minutes = request.args.get('minutes')
        seconds = request.args.get('seconds')

        try:
            if start is not None and end is not None:
                startTime = datetime.strptime(start, '%Y%m%dZ%H%M%S')
                endTime = datetime.strptime(end, '%Y%m%dZ%H%M%S')
                query += f"AND timestamp >= '{startTime}' AND timestamp <= '{endTime}' ".format(startTime, endTime)

            elif start is not None and (hours is not None or minutes is not None or seconds is not None):
                startTime = datetime.strptime(start, '%Y%m%dZ%H%M%S')
                endTime = startTime + timedelta(hours=int(hours or 0), minutes=int(minutes or 0),
                                                seconds=int(seconds or 0))
                query += f"AND timestamp >= '{startTime}' AND timestamp <= '{endTime}' ".format(startTime, endTime)

            elif end is not None and (hours is not None or minutes is not None or seconds is not None):
                endTime = datetime.strptime(end, '%Y%m%dZ%H%M%S')
                startTime = endTime - timedelta(hours=int(hours or 0), minutes=int(minutes or 0),
                                                seconds=int(seconds or 0))
                query += f"AND timestamp >= '{startTime}' AND timestamp <= '{endTime}' ".format(startTime, endTime)

            else:
                query += "AND timestamp >= NOW() - INTERVAL '15 minutes' "

        except Exception as e:
            query += "AND timestamp >= NOW() - INTERVAL '15 minutes' "

        query += "ORDER BY timestamp ASC;"

        try:
            result = conn.execute(text(query))
            for row in result:
                trkpt = ET.SubElement(trkseg, "trkpt", attrib={"lat": str(row[5]), "lon": str(row[4])})
                ET.SubElement(trkpt, "time").text = str(row[1])

            conn.close()
        except Exception as e:
            log.error("SQL: " + str(e))
            conn.close()

        return Response(ET.tostring(gpx), mimetype='text/xml')

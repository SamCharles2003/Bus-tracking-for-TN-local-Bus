from flask import Flask, request, jsonify, render_template
from flask_ngrok import run_with_ngrok
import pymysql
import pymysqlpool
import math

app = Flask(__name__)

# Database connection
remote_db_config = {
    "host": "sql12.freesqldatabase.com",
    "user": "sql12753688",
    "password": "RZsLU1gQDB",
    "database": "sql12753688",
    "port": 3306
}

remote_conn =pymysqlpool.ConnectionPool(size=2, maxsize=3, pre_create_num=2, name='pool1', **remote_db_config)
cursor = remote_conn.get_connection()


# Function to calculate distance between two coordinates
def haversine(lat1, lon1, lat2, lon2):
    dLat = (float(lat2) - float(lat1)) * math.pi / 180.0
    dLon = (float(lon2) - float(lon1)) * math.pi / 180.0

    # convert to radians
    lat1 = float((lat1)) * math.pi / 180.0
    lat2 = float((lat2)) * math.pi / 180.0

    # apply formulae
    a = (pow(math.sin(dLat / 2), 2) +
         pow(math.sin(dLon / 2), 2) *
         math.cos(lat1) * math.cos(lat2));
    rad = 6371
    c = 2 * math.asin(math.sqrt(a))
    return rad * c


@app.route("/")
def main_route():
    return render_template(template_name_or_list="index.html")


@app.route("/find-nearest", methods=["POST"])
def find_nearest():
    data = request.json
    user_lat = data.get("latitude")
    user_lng = data.get("longitude")

    if user_lat is None or user_lng is None:
        return jsonify({"success": False, "message": "Invalid coordinates."}), 400

    try:
        global cursor

        cursor.execute("SELECT place, latitude, longitude FROM bus_stops")
        bus_stops = cursor.fetchall()

        nearest_place = None
        min_distance = float("inf")

        # Find the nearest stop
        for stop in bus_stops:
            place, lat, lng = stop
            distance = haversine(user_lat, user_lng, lat, lng)
            if distance < min_distance:
                min_distance = distance
                nearest_place = place

        if nearest_place:
            return jsonify({"success": True, "place": nearest_place})

        else:
            return jsonify({"success": False, "message": "No nearby bus stops found."})

    except Exception as e:
        print(f"Error occurred: {e}")
        # Reconnect to the database
        try:
            global remote_conn
            print("Reconnecting....")
            remote_conn = pymysql.connect(**remote_db_config)
            cursor = remote_conn.cursor()
            # After reconnecting, retry fetching data
            cursor.execute("SELECT place, latitude, longitude FROM bus_stops")
            bus_stops = cursor.fetchall()
            cursor.close()

            nearest_place = None
            min_distance = float("inf")

            # Find the nearest stop
            for stop in bus_stops:
                place, lat, lng = stop
                distance = haversine(user_lat, user_lng, lat, lng)
                if distance < min_distance:
                    min_distance = distance
                    nearest_place = place

            if nearest_place:
                return jsonify({"success": True, "place": nearest_place})

            else:
                return jsonify({"success": False, "message": "No nearby bus stops found."})

        except Exception as reconnect_error:
            print(f"Error during reconnection: {reconnect_error}")
            return jsonify({"success": False, "message": "Failed to connect to the database."}), 500




if __name__ == "__main__":
    app.run()

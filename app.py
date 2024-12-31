from flask import Flask, render_template, jsonify, request
import psycopg2
import math
from highwaypoints import fetch_route_coordinates_with_via_dict as frcv
from highwaypoints import update_bus_location as ubl

app = Flask(__name__)

# Remote PostgreSQL Database Configuration
remote_db_config = {
    "host": "dpg-ctparopopnds73fnhhg0-a.oregon-postgres.render.com",
    "user": "sam_db",
    "password": "hJTmmPb0kiJHHhFfQtILOrtR41O8sVV4",
    "dbname": "bus_tracking",
    "port": 5432
}


def get_db_connection():
    return psycopg2.connect(**remote_db_config)


@app.route('/')
def index():
    return render_template('map.html')


@app.route('/get-markers')
def get_markers():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Modify this query according to your database structure
        cursor.execute("SELECT bus_no, latitude, longitude, route_no, route_name FROM bus_info")
        markers = []

        for row in cursor.fetchall():
            markers.append({
                'name': row[0],
                'lat': float(row[1]),
                'lng': float(row[2]),
                'route_no': row[3],
                'route_name': row[4]
            })

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'markers': markers})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on Earth."""
    try:
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(lambda x: float(x) * math.pi / 180.0, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371  # Radius of Earth in kilometers
        return c * r
    except Exception as e:
        print(f"Error in haversine calculation: {e}")
        raise


def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculate the bearing between two points."""
    try:
        lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        dlon = lon2 - lon1
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360
    except Exception as e:
        print(f"Error in bearing calculation: {e}")
        raise


@app.route("/find-nearest", methods=["POST"])
def find_nearest():
    data = request.json
    user_lat = data.get("latitude")
    user_lng = data.get("longitude")

    if user_lat is None or user_lng is None:
        return jsonify({"success": False, "message": "Invalid coordinates."}), 400

    try:
        global cursor, coordinates
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
                cursor.execute("SELECT latitude, longitude FROM bus_stops WHERE place = %s", (nearest_place,))
                route = cursor.fetchall()
                print(route)
                coordinates = [{'lat': float(lat), 'lng': float(lng)} for lat, lng in route]

        if nearest_place:
            return jsonify({
                "success": True,
                "place": nearest_place,
                "distance_km": round(min_distance, 2),
                "coordinates": coordinates
            })

        else:
            return jsonify({"success": False, "message": "No nearby bus stops found."})

    except Exception as e:
        print(f"Error occurred: {e}")
        # Reconnect to the database
        try:
            global remote_conn
            print("Reconnecting....")
            remote_conn = psycopg2.connect(**remote_db_config)
            cursor = remote_conn.cursor()
            # After reconnecting, retry fetching data
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
                    cursor.execute("SELECT latitude, longitude FROM bus_stops WHERE place = %s", (nearest_place,))
                    route = cursor.fetchall()
                    print(route)
                    coordinates = [{'lat': float(lat), 'lng': float(lng)} for lat, lng in route]

            if nearest_place:
                return jsonify({
                    "success": True,
                    "place": nearest_place,
                    "distance_km": round(min_distance, 2),
                    "coordinates": coordinates
                })

            else:
                return jsonify({"success": False, "message": "No nearby bus stops found."})

        except Exception as reconnect_error:
            print(f"Error during reconnection: {reconnect_error}")
            return jsonify({"success": False, "message": "Failed to connect to the database."}), 500


@app.route('/get-bus-details/<bus_no>')
def get_bus_details(bus_no):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get bus information including departure, arrival, and via points
        cursor.execute("""
                    SELECT bi.bus_no, bi.route_no, bi.route_name, bi.latitude, bi.longitude, 
                           bi.avg_speed, bi.departure, bi.arrival, bi.via, bi.departure_time,
                           bi.next_stop, bi.eta
                    FROM bus_info bi
                    WHERE bi.bus_no = %s
                """, (bus_no,))
        bus_info = cursor.fetchone()

        if not bus_info:
            return jsonify({'success': False, 'error': 'Bus not found'})

        # Get coordinates for departure, arrival, and via points
        departure_place = bus_info[6]
        arrival_place = bus_info[7]
        via_places = bus_info[8].split(',') if bus_info[8] else []

        # Get coordinates for departure point
        cursor.execute("""
            SELECT latitude, longitude 
            FROM bus_stops 
            WHERE place = %s
        """, (departure_place,))
        start_coords = cursor.fetchone()

        # Get coordinates for arrival point
        cursor.execute("""
            SELECT latitude, longitude 
            FROM bus_stops 
            WHERE place = %s
        """, (arrival_place,))
        end_coords = cursor.fetchone()

        # Get coordinates for via points
        via_coordinates = []
        for via_place in via_places:
            cursor.execute("""
                SELECT latitude, longitude 
                FROM bus_stops 
                WHERE place = %s
            """, (via_place.strip(),))
            via_point = cursor.fetchone()
            if via_point:
                via_coordinates.append([float(via_point[0]), float(via_point[1])])

        route_points = {
            'start': {
                'lat': float(start_coords[0]),
                'lng': float(start_coords[1])
            },
            'end': {
                'lat': float(end_coords[0]),
                'lng': float(end_coords[1])
            },
            'via': frcv(start_lat=float(start_coords[0]), start_lng=float(start_coords[1]),
                        end_lat=float(end_coords[0]), end_lng=float(end_coords[1]), via_points=via_coordinates)
        }

        response = {
            'success': True,
            'bus_details': {
                'bus_no': bus_info[0],
                'route_no': bus_info[1],
                'route_name': bus_info[2],
                'avg_speed': float(bus_info[5]),
                'departure': bus_info[6],
                'arrival': bus_info[7],
                'departure_time': str(bus_info[9]),
                'next_stop': bus_info[10],
                'eta': str(bus_info[11])
            },
            'route_points': route_points
        }
        return jsonify(response)

    except Exception as e:
        print(e, "MAP Tester")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/get-bus-details-interval/<bus_no>')
def get_bus_details_interval(bus_no):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get bus information including departure, arrival, and via points
        cursor.execute("""
                    SELECT bi.bus_no, bi.route_no, bi.route_name, bi.latitude, bi.longitude, 
                           bi.avg_speed, bi.departure, bi.arrival, bi.via, bi.departure_time,
                           bi.next_stop, bi.eta
                    FROM bus_info bi
                    WHERE bi.bus_no = %s
                """, (bus_no,))
        bus_info = cursor.fetchone()

        if not bus_info:
            return jsonify({'success': False, 'error': 'Bus not found'})

        response = {
            'success': True,
            'bus_details': {
                'bus_no': bus_info[0],
                'route_no': bus_info[1],
                'route_name': bus_info[2],
                'avg_speed': float(bus_info[5]),
                'departure': bus_info[6],
                'arrival': bus_info[7],
                'departure_time': str(bus_info[9]),
                'next_stop': bus_info[10],
                'eta': str(bus_info[11])
            }
        }
        return jsonify(response)

    except Exception as e:
        print(e, "MAP Tester")
        return jsonify({'success': False, 'error': str(e)})

@app.route("/bus_loc", methods=["POST"])
def bus_loc():
    try:
        data = request.json
        lat = data.get("latitude")
        lng = data.get("longitude")
        avgSpeed = data.get("speed")
        bus_no = data.get("bus_no")
        ubl(bus_no, lat,lng, avgSpeed)  # Fixed latlng variable
        return jsonify({"success": True, "data": 200})  # Fixed true -> True
    except Exception as e:
        print("Error: ", e)
        return jsonify({"success": False, "error": str(e)}), 500  # Added error response


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9900)

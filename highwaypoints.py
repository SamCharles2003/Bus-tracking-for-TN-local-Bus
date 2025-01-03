import requests
import pymysql
import time
import random
import math
from config import db_config

# Database Configuration



def fetch_route_coordinates_with_via_dict(start_lat, start_lng, end_lat, end_lng, via_points):
    """
    Fetch the route coordinates between two locations using the OSRM API, including via points.

    Parameters:
    - start_lat, start_lng: Starting latitude and longitude.
    - end_lat, end_lng: Ending latitude and longitude.
    - via_points: List of tuples containing lat, lng for via points.

    Returns:
    - List of tuples containing latitude and longitude values along the route.
    """
    try:
        # Constructing the locations string with via points
        locations = f"{start_lng},{start_lat};"
        for lat, lng in via_points:
            locations += f"{lng},{lat};"
        locations += f"{end_lng},{end_lat}"

        url = f"http://router.project-osrm.org/route/v1/driving/{locations}"
        params = {
            "overview": "full",
            "geometries": "geojson"
        }
        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            print(f"Error: Unable to fetch route. Status Code: {response.status_code}")
            return []

        data = response.json()
        route = data["routes"][0]["geometry"]["coordinates"]
        coordinates = [{'lat': lat, 'lng': lng} for lng, lat in route]  # Convert to {'lat': value, 'lng': value}
        return coordinates


    except Exception as e:
        print(f"Error fetching route coordinates: {e}")
        return []



def fetch_route_coordinates_with_via(start_lat, start_lng, end_lat, end_lng, via_points):
    """
    Fetch the route coordinates between two locations using the OSRM API, including via points.

    Parameters:
    - start_lat, start_lng: Starting latitude and longitude.
    - end_lat, end_lng: Ending latitude and longitude.
    - via_points: List of tuples containing lat, lng for via points.

    Returns:
    - List of tuples containing latitude and longitude values along the route.
    """
    try:
        # Constructing the locations string with via points
        locations = f"{start_lng},{start_lat};"
        for lat, lng in via_points:
            locations += f"{lng},{lat};"
        locations += f"{end_lng},{end_lat}"

        url = f"http://router.project-osrm.org/route/v1/driving/{locations}"
        params = {
            "overview": "full",
            "geometries": "geojson"
        }
        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            print(f"Error: Unable to fetch route. Status Code: {response.status_code}")
            return []

        data = response.json()
        route = data["routes"][0]["geometry"]["coordinates"]
        coordinates = [(lat, lng) for lng, lat in route]  # Convert to (lat, lng)
        return coordinates

    except Exception as e:
        print(f"Error fetching route coordinates: {e}")
        return []


def update_bus_location(bus_no, lat, lng, avg_speed):

    """
    Update the bus location and average speed in the database.

    Parameters:
    - bus_no: Bus number.
    - lat, lng: Latitude and longitude to update.
    - avg_speed: Average speed of the bus (in km/h).
    """
    global cursor, coordinates, connection, previous_location
    try:
        # Connect to the database
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()

        cursor.execute('SELECT latitude, longitude FROM bus_info WHERE bus_no= %s',args=(bus_no,))
        previous_location=cursor.fetchall()
        # SQL to update the bus location and speed
        sql = """
        UPDATE bus_info
        SET latitude = %s, longitude = %s, avg_speed = %s
        WHERE bus_no = %s
        """
        cursor.execute(sql, (lat, lng, avg_speed, bus_no))
        connection.commit()
        print(f"Updated {bus_no} location to Latitude: {lat}, Longitude: {lng}, Avg Speed: {avg_speed} km/h")

    except pymysql.Error as e:
        print(f"Error updating database: {e}")


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


def find_nearest(user_lat,user_lng,bus_no):
    try:
        # Fetch the "via" route, departure, arrival, and next stop for the given bus number
        cursor.execute("SELECT via, arrival FROM bus_info WHERE bus_no = %s", (bus_no,))
        paths = cursor.fetchone()
        via = paths[0].split(',')  # Split the 'via' string into individual places
        arrival = paths[1]  # Arrival stop
        all_stopings =  via + [arrival]
        for bus_Stand in all_stopings:
            prox_dist={}
            cursor.execute("SELECT latitude, longitude FROM bus_stops WHERE place = %s", (bus_Stand,))
            bus_Stand_Coordinates = cursor.fetchall()
            for lat,lng in bus_Stand_Coordinates:
                distance=haversine(user_lat,user_lng,lat,lng)
                if 0 < distance < 1:
                    return bus_Stand
    except Exception as e:
        print("FIND NEAREST ()",e)

def next_stop(user_lat, user_lng, bus_no):
    global cursor
    try:
        # Calculate bearing
        bus_Stand = find_nearest(user_lat, user_lng, bus_no)

        if bus_Stand:
            print(f"Updating: {bus_no} - {bus_Stand}")
            try:
                cursor.execute("UPDATE bus_info SET next_stop = %s WHERE bus_no = %s", (str(bus_Stand), bus_no))
                connection.commit()
                print(f"Database updated: {bus_no} - {bus_Stand}")
                print(f"Rows affected: {cursor.rowcount}")
            except Exception as e:
                print(f"Error updating database: {e}")
        else:
            print("No nearest bus stand found.")
    except Exception as e:
        print(f"Error in next_stop: {e}")

def place_query(place):
    cursor.execute("SELECT latitude,longitude FROM bus_stops WHERE place = %s", (place,))
    coords = cursor.fetchone()
    return coords



from datetime import datetime, timedelta

def calculate_eta(bus_no):
    # Fetch departure time and average speed from the database
    cursor.execute("SELECT arrival, departure, avg_Speed, departure_time FROM bus_info WHERE bus_no = %s", (bus_no,))
    paths = cursor.fetchone()
    arrival_coords = place_query(paths[0])
    depart_coords = place_query(paths[1])
    avg_speed = paths[2]
    departure_time_str=str(paths[3])
    distance = haversine(arrival_coords[0], arrival_coords[1], depart_coords[0], depart_coords[1])
    time_in_hours = distance / float(avg_speed)
    hours = int(time_in_hours)
    minutes = int((time_in_hours - hours) * 60)
    departure_time = datetime.strptime(departure_time_str, "%H:%M:%S")
    eta_timedelta = timedelta(hours=hours, minutes=minutes)
    new_eta_time = departure_time + eta_timedelta
    new_eta_str = new_eta_time.strftime("%H:%M:%S")
    cursor.execute("UPDATE bus_info SET eta = %s WHERE bus_no = %s", (new_eta_str, bus_no))
    connection.commit()

    print(f"Updated ETA for bus {bus_no} to: {new_eta_str}")





if __name__ == "__main__":
    # Starting and ending locations
    start_lat, start_lng = 8.97137300, 77.30163700  # Starting location
    end_lat, end_lng = 8.70124300, 77.72579800  # Ending location
    bus_no = "TN-72-AN-2538"

    # Define via points (Example)
    via_points = [
        (8.91941080, 77.37842910),
        (8.86684800, 77.49553700),
        (8.81822000, 77.56402400),
        (8.74578300, 77.66045200),
        (8.73052000, 77.71013300)
    ]

    # Fetch route coordinates with via points
    route_coordinates = fetch_route_coordinates_with_via(start_lat, start_lng, end_lat, end_lng, via_points)

    if route_coordinates:
        print("Updating database with route coordinates...")
        for lat, lng in route_coordinates:
            avg_speed = random.uniform(40, 60)  # Generate a realistic average speed in km/h
            update_bus_location(bus_no, lat, lng, avg_speed)
            next_stop(lat,lng,bus_no)
            calculate_eta(bus_no)
            time.sleep(1)  # Wait 1 second before updating the next location
    else:
        print("No route coordinates found.")

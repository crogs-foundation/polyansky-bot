import csv
import json

with open("./data/stops.json", "r") as f:
    stops_json = json.load(f)

data = stops_json["features"]

stops = []
for stop in data:
    print(stop["properties"]["@id"])
    try:
        stops.append(
            {
                "name": stop["properties"]["official_name"]
                if stop["properties"].get("official_name")
                else stop["properties"]["name"],
                "is_active": True,
                "latitude": stop["geometry"]["coordinates"][0],
                "longitude": stop["geometry"]["coordinates"][1],
            }
        )
    except:
        pass

with open("./data/stops.csv", "w") as f:
    stops_writer = csv.DictWriter(f, ["name", "is_active", "latitude", "longitude"])
    stops_writer.writeheader()
    stops_writer.writerows(stops)

import json
import os
import sys

import requests

# Path to an image file for testing
# Replace with a path to your own image file
filename = sys.argv[1] if len(sys.argv) > 1 else "snowman.png"
image_path = os.path.expanduser(filename)

# Check if the file exists
if not os.path.exists(image_path):
    print(f"Error: Image file not found at {image_path}")
    print("Please update the image_path variable to point to a valid image file")
    exit(1)

# Prepare the files for upload
files = {"content": open(image_path, "rb")}

# Send the request to the API
try:
    response = requests.post("http://127.0.0.1:8001/stats", files=files)

    # Print the status code and response
    print(f"Status: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), indent=2))

except Exception as e:
    print(f"Error: {e}")
finally:
    # Close the file
    files["content"].close()

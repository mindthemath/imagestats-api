# Image Stats API

This project provides an API to extract statistical information from images, including EXIF data and color analysis (average and dominant colors).

## Features

*   **EXIF Data Extraction**: Retrieves standard EXIF (Exchangeable image file format) data from images.
    *   Processes and validates GPS information, filtering out empty or default values.
    *   Handles non-serializable EXIF values by converting them to string representations.
*   **Color Analysis**:
    *   **Average Color**: Calculates the average color of an image. Supports multiple averaging methods:
        *   `arithmetic` (default)
        *   `harmonic`
        *   `geometric`
        (Configurable via the `AVERAGING_METHOD` environment variable).
    *   **Dominant Color**: Identifies the most prominent color in an image using HSV color space clustering.
*   **Image Processing**:
    *   Handles image input via file upload or URL.
    *   Resizes large images (max dimension > 512px) to a thumbnail for faster processing while preserving aspect ratio.
    *   Converts images to RGBA format and filters out transparent pixels before color analysis.
*   **LitServe Integration**: Built using `litserve` for efficient serving.

## Running the Server

The server is implemented in `server.py`.

### Using `uv` (recommended via Makefile):

The `makefile` provides a convenient way to run the server:

```bash
make run
```

This command uses `uv run server.py`.

### Manually:

You can also run it directly using a Python interpreter capable of running the dependencies (e.g., after setting up a virtual environment and installing packages):

```bash
python server.py
```

### Environment Variables:

The server can be configured using the following environment variables:

*   `PORT`: Port to run the server on (default: `8010`).
*   `LOG_LEVEL`: Logging level (e.g., `INFO`, `DEBUG`; default: `INFO`).
*   `AVERAGING_METHOD`: Method for calculating average color (`arithmetic`, `harmonic`, `geometric`; default: `arithmetic`).
*   `NUM_API_SERVERS`: Number of API server instances (default: `1`).
*   `WORKERS_PER_DEVICE`: Number of worker threads per device (default: `1`).

## API Endpoint

### `POST /stats`

*   **Description**: Analyzes an image and returns its EXIF data and color statistics.
*   **Request**:
    *   **Method**: `POST`
    *   **Content-Type**: `multipart/form-data` (for file uploads) or `application/json` (for URL inputs).
    *   **Body**:
        *   For file upload: Form data with a file field named `content`.
        *   For URL input: JSON object with a key `content` whose value is the image URL string (e.g., `{"content": "http://example.com/image.jpg"}`).
            *   *Note*: The server includes a hack to replace `localhost:3210` with `backend:3210` in URLs, which might be relevant for specific deployment scenarios.

*   **Response**: `application/json`
    *   **Success (200 OK)**:
        ```json
        {
          "exif_data": {
            // ... various EXIF tags and values ...
            "GPSInfo": { /* GPS data if valid, otherwise omitted */ }
          },
          "color_data": {
            "avg_color": {
              "rgb": [0.R, 0.G, 0.B], // RGB values (0-1 range)
              "hex": "#RRGGBB",       // Hex color code
              "method": "method_used"
            },
            "dominant_color": {
              "rgb": [0.R, 0.G, 0.B], // RGB values (0-1 range)
              "hex": "#RRGGBB"        // Hex color code
            }
          }
        }
        ```
        If `color_data` could not be determined (e.g., image has no valid pixels), it might be `null`.
        If `exif_data` could not be extracted, it might be empty or partially filled.

## Client Examples

### 1. Python Client (`client.py`)

The `client.py` script provides a simple command-line interface to send an image to the API and print the response.

**Usage**:

```bash
python client.py [path_to_your_image]
```

If no image path is provided, it defaults to trying to send `snowman.png` from the current directory.

The script will:
1.  Check if the image file exists.
2.  Send a POST request to `http://127.0.0.1:8001/stats` with the image file.
3.  Print the HTTP status code and the JSON response from the server.

**Example (using `uv` via Makefile)**:

First, ensure you have an image (e.g., `snowman.png`, which can be downloaded using `make snowman.png`). Then:
```bash
make client-test
```
This will run `uv run client.py snowman.png` (implicitly, as `snowman.png` is the default if no argument is given to `client.py` after `uv run`).

To test with a different image:
```bash
uv run client.py my_image.jpg
```

### 2. cURL Example

The `makefile` includes a `curl-test` target that demonstrates how to interact with the API using `curl`.

**Command from Makefile**:
```bash
curl -X POST -F "content=@snowman.png" http://127.0.0.1:8001/stats | jq
```

**Explanation**:
*   `curl -X POST`: Sends a POST request.
*   `-F "content=@snowman.png"`: Sends the file `snowman.png` as part of a `multipart/form-data` request. The `@` symbol tells `curl` to read the content from the specified file. The field name is `content`.
*   `http://127.0.0.1:8001/stats`: The URL of the API endpoint.
*   `| jq`: Pipes the JSON output to `jq` for pretty-printing.

**Usage (via Makefile)**:
```bash
make curl-test
```
This target first ensures `snowman.png` is downloaded if it doesn't exist (due to the `snowman.png` dependency in the Makefile rule).

## Makefile Targets

The `makefile` provides several useful targets:

*   `run`: Runs the server using `uv run server.py`.
*   `snowman.png`: Downloads a sample image (`snowman.png`) from Hugging Face if it doesn't already exist in the current directory. This is used for testing.
*   `curl-test`: Tests the API endpoint using `curl` with `snowman.png`. It depends on the `snowman.png` target. The output is piped to `jq` for readability.
*   `client-test`: Tests the API endpoint using the `client.py` script with `snowman.png` (by default). It runs `uv run client.py`.

## Dependencies
Key dependencies include:
- `litserve`: For the API server framework.
- `Pillow (PIL)`: For image manipulation.
- `numpy`: For numerical operations, especially on pixel data.
- `requests`: Used by `server.py` to fetch images from URLs and by `client.py` to interact with the API.
- `uv`: Used in the Makefile for running python scripts and managing environments (implied).

`uv run` will ensure dependencies are installed.
If you need a `requirements.txt` file, the command

```bash
uv pip compile pyproject.toml -o requirements.txt
```
can be used to gnerate one.

import json
import logging
import os
from collections import Counter
from colorsys import rgb_to_hsv
from io import BytesIO

import litserve as ls
import numpy as np
import requests
from PIL import ExifTags, Image

# Environment configurations
PORT = int(os.environ.get("PORT", "8001"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
NUM_API_SERVERS = int(os.environ.get("NUM_API_SERVERS", "1"))
AVERAGING_METHOD = os.environ.get("AVERAGING_METHOD", "arithmetic")

# Set up logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Maximum size for thumbnail processing
MAX_THUMB_SIZE = 512


def resize_for_processing(image):
    """Create a thumbnail if image is too large"""
    # Check if resizing is needed
    if max(image.size) > MAX_THUMB_SIZE:
        logger.info(f"Resizing large image from {image.size} for color processing")
        # Calculate proportional height
        width, height = image.size
        if width > height:
            new_width = MAX_THUMB_SIZE
            new_height = int(height * (MAX_THUMB_SIZE / width))
        else:
            new_height = MAX_THUMB_SIZE
            new_width = int(width * (MAX_THUMB_SIZE / height))

        # Create a thumbnail
        thumb = image.copy()
        thumb.thumbnail((new_width, new_height), Image.LANCZOS)
        return thumb

    return image


def get_exif_data(image):
    """Extract EXIF data from image and handle serialization issues"""
    exif_data = {}
    try:
        if hasattr(image, "_getexif") and image._getexif():
            for tag, value in image._getexif().items():
                if tag in ExifTags.TAGS:
                    tag_name = ExifTags.TAGS[tag]
                    # Handle non-serializable EXIF values
                    try:
                        # Convert rational numbers to floats
                        if hasattr(value, "numerator") and hasattr(
                            value, "denominator"
                        ):
                            if value.denominator != 0:
                                value = float(value.numerator) / value.denominator
                            else:
                                value = 0
                        # Test if value is JSON serializable
                        json.dumps(value)
                        exif_data[tag_name] = value
                    except (TypeError, OverflowError):
                        # Convert problematic types to string representation
                        try:
                            exif_data[tag_name] = str(value)
                        except:
                            exif_data[tag_name] = "Unable to serialize value"
    except Exception as e:
        logger.warning(f"Error extracting EXIF data: {e}")
    return exif_data


def calculate_arithmetic_mean(valid_pixels):
    """Calculate arithmetic mean of valid pixels"""
    return valid_pixels[:, :3].mean(axis=0) / 255.0


def calculate_harmonic_mean(valid_pixels):
    """Calculate harmonic mean of valid pixels"""
    # Convert to float and handle zeros to prevent division by zero
    rgb_values = valid_pixels[:, :3].astype(float)
    # Add small epsilon to prevent division by zero
    eps = 1e-8
    rgb_values = np.maximum(rgb_values, eps)

    # Calculate harmonic mean for each channel
    reciprocal_mean = np.mean(1.0 / rgb_values, axis=0)
    harmonic_mean = 1.0 / reciprocal_mean

    return harmonic_mean / 255.0


def calculate_geometric_mean(valid_pixels):
    """Calculate geometric mean of valid pixels"""
    # Convert to float and handle zeros
    rgb_values = valid_pixels[:, :3].astype(float)
    # Add small epsilon to prevent log(0)
    eps = 1e-8
    rgb_values = np.maximum(rgb_values, eps)

    # Calculate geometric mean for each channel
    log_values = np.log(rgb_values)
    log_mean = np.mean(log_values, axis=0)
    geometric_mean = np.exp(log_mean)

    return geometric_mean / 255.0


def calculate_color_average(valid_pixels, method="arithmetic"):
    """Calculate color average based on specified method"""
    if method == "harmonic":
        return calculate_harmonic_mean(valid_pixels)
    elif method == "geometric":
        return calculate_geometric_mean(valid_pixels)
    else:  # Default to arithmetic
        return calculate_arithmetic_mean(valid_pixels)


def rgb_to_hex(rgb_array):
    """Convert RGB array (0-1 range) to hex color code"""
    r_int, g_int, b_int = [int(c * 255) for c in rgb_array]
    return f"#{r_int:02x}{g_int:02x}{b_int:02x}"


def find_dominant_color(valid_pixels):
    """Find the dominant color using HSV clustering"""
    # Convert to HSV for better color grouping
    rgb_pixels = valid_pixels[:, :3] / 255.0
    hsv_pixels = np.array([rgb_to_hsv(r, g, b) for r, g, b in rgb_pixels])

    # Quantize colors to reduce unique count
    quantized = (
        (hsv_pixels[:, 0] * 10).astype(int) * 1000
        + (hsv_pixels[:, 1] * 10).astype(int) * 10
        + (hsv_pixels[:, 2] * 10).astype(int)
    )

    # Count occurrences
    color_counts = Counter(quantized)

    # Get most common color
    most_common_key = color_counts.most_common(1)[0][0]

    # Find an actual pixel with this quantization
    idx = np.where(quantized == most_common_key)[0][0]
    dominant_rgb = valid_pixels[idx, :3] / 255.0

    return dominant_rgb


def get_image_colors(image, averaging_method="arithmetic"):
    """Extract color information from image, ignoring alpha/masked pixels"""
    # Create a thumbnail for processing if image is large
    process_image = resize_for_processing(image)

    # Convert image to RGBA if it isn't already
    if process_image.mode != "RGBA":
        process_image = process_image.convert("RGBA")

    # Get image data
    pixels = np.array(process_image)

    # Reshape to list of pixels
    pixels = pixels.reshape(-1, 4)

    # Filter out fully transparent or masked pixels (alpha < 128)
    valid_pixels = pixels[pixels[:, 3] >= 128]

    if len(valid_pixels) == 0:
        return None

    # Calculate average color using specified method
    avg_color = calculate_color_average(valid_pixels, averaging_method)
    avg_hex = rgb_to_hex(avg_color)

    # Find dominant color
    dominant_rgb = find_dominant_color(valid_pixels)
    dominant_hex = rgb_to_hex(dominant_rgb)

    return {
        "avg_color": {
            "rgb": avg_color.tolist(),  # Float values in range [0,1]
            "hex": avg_hex,
            "method": averaging_method,
        },
        "dominant_color": {
            "rgb": dominant_rgb.tolist(),  # Float values in range [0,1]
            "hex": dominant_hex,
        },
    }


class ImageStatsAPI(ls.LitAPI):
    def setup(self, device):
        logger.info("Setting up Image Stats API.")
        # No device needed for CPU operations

    def decode_request(self, request):
        file_obj = request["content"]

        if isinstance(file_obj, str) and "http" in file_obj:
            file_obj = file_obj.replace("localhost:3210", "backend:3210")  # HACK
            image = Image.open(requests.get(file_obj, stream=True).raw)
            logger.info("Processing URL input.")
            return image
        try:
            file_bytes = file_obj.file.read()
            image = Image.open(BytesIO(file_bytes))
            logger.info("Processing file input.")
            return image
        except AttributeError:
            logger.warning("Failed to process request")
        finally:
            if not isinstance(file_obj, str):
                file_obj.file.close()

    def predict(self, image):
        logger.info(f"Processing image using {AVERAGING_METHOD} averaging method.")

        exif_data = get_exif_data(image)
        color_data = get_image_colors(image, AVERAGING_METHOD)

        return {"exif_data": exif_data, "color_data": color_data}


if __name__ == "__main__":
    server = ls.LitServer(
        ImageStatsAPI(max_batch_size=1),
        accelerator="cpu",
        track_requests=True,
        api_path="/stats",
        workers_per_device=NUM_API_SERVERS,
    )
    server.run(
        port=PORT,
        host="0.0.0.0",
        log_level=LOG_LEVEL.lower(),
    )

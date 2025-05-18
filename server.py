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


def process_gps_info(gps_info):
    """
    Process GPS information to determine if it contains valid data.
    Returns None if the GPS data is empty or contains only default values.
    Otherwise returns the original GPS data.
    """
    # Initialize as invalid by default
    has_valid_gps = False

    # Check if GPSInfo is a string representation (common due to serialization)
    if isinstance(gps_info, str):
        # Check for patterns indicating default/empty values
        if (
            "(0.0, 0.0, 0.0)" in gps_info
            or "'1970:01:01'" in gps_info
            or "0.0" in gps_info
        ):
            # These patterns suggest default or empty values
            pass
        else:
            # No default patterns found - likely has actual data
            has_valid_gps = True
    elif isinstance(gps_info, dict):
        # For dictionary representation, check for actual coordinate values
        coordinates = gps_info.get(2, (0, 0, 0))  # 2 is the tag for GPSLatitude
        if coordinates != (0, 0, 0):
            has_valid_gps = True

    return gps_info if has_valid_gps else None


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

    # Process GPS information if present
    if "GPSInfo" in exif_data:
        processed_gps = process_gps_info(exif_data["GPSInfo"])
        if processed_gps is None:
            # Remove invalid GPS data
            del exif_data["GPSInfo"]
            logger.info("Filtered out empty/default GPS information")
        else:
            # Keep the valid GPS data
            exif_data["GPSInfo"] = processed_gps

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


def prepare_image_for_color_analysis(image):
    """
    Prepare image for color analysis by creating a thumbnail and converting to RGBA.
    Also extracts valid (non-transparent) pixels.

    Returns:
        valid_pixels: Array of non-transparent pixel values
        or None if no valid pixels found
    """
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

    return valid_pixels


def get_average_color(valid_pixels, averaging_method="arithmetic"):
    """
    Calculate the average color of an image using the specified method.

    Args:
        valid_pixels: Array of non-transparent pixel values
        averaging_method: The method to use for averaging ("arithmetic", "harmonic", or "geometric")

    Returns:
        Dictionary containing RGB values and hex code for the average color
    """
    avg_color = calculate_color_average(valid_pixels, averaging_method)
    avg_hex = rgb_to_hex(avg_color)

    return {
        "rgb": avg_color.tolist(),  # Float values in range [0,1]
        "hex": avg_hex,
        "method": averaging_method,
    }


def get_dominant_color(valid_pixels):
    """
    Find the dominant color in an image using HSV clustering.

    Args:
        valid_pixels: Array of non-transparent pixel values

    Returns:
        Dictionary containing RGB values and hex code for the dominant color
    """
    dominant_rgb = find_dominant_color(valid_pixels)
    dominant_hex = rgb_to_hex(dominant_rgb)

    return {
        "rgb": dominant_rgb.tolist(),  # Float values in range [0,1]
        "hex": dominant_hex,
    }


def get_image_colors(image, averaging_method="arithmetic"):
    """
    Extract color information from image, including average and dominant colors.
    This function can later be converted to use async operations for parallel processing.

    Args:
        image: PIL Image object
        averaging_method: Method to use for calculating average color

    Returns:
        Dictionary containing average and dominant color information,
        or None if no valid pixels were found
    """
    valid_pixels = prepare_image_for_color_analysis(image)

    if valid_pixels is None:
        return None

    # Calculate average and dominant colors
    avg_color_data = get_average_color(valid_pixels, averaging_method)
    dominant_color_data = get_dominant_color(valid_pixels)

    return {
        "avg_color": avg_color_data,
        "dominant_color": dominant_color_data,
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

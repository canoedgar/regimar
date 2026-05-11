from PIL import Image
import numpy as np

# Create a 32x32 image with the logo design.
# Based on the previous output, the logo is essentially a hexagon shape made of vertical stripes.
# I will create a simple representation.

img_size = 32
# Create an RGBA image (transparent background)
img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
pixels = img.load()

# Define some colors for the logo based on the original (oranges/browns)
color1 = (235, 120, 50, 255) # Light orange
color2 = (200, 90, 40, 255)  # Darker orange/brown

# Draw the logo shape (approximation)
# The logo has a hexagonal shape.
# Let's fill the central area to resemble the logo structure.
for y in range(8, 24):
    for x in range(8, 24):
        # A simple hexagon-like mask or just filling a block
        # For a 32x32 icon, a simplified blocky design is best.
        if (x >= 10 and x <= 22):
            if (x < 14):
                pixels[x, y] = color1
            elif (x >= 14 and x < 18):
                pixels[x, y] = color2
            elif (x >= 18):
                pixels[x, y] = color1

# Save as PNG
file_path = "logo_32x32.png"
img.save(file_path)
"""
Sample Photo Library Generator for LuminaPhoto.
Creates sample folder trees with simulated real camera photos, EXIF metadata, GPS geotags,
exact duplicates, near-duplicates, and screenshots.
"""

import os
import shutil
import piexif
from typing import Optional

def create_sample_library(base_path: Optional[str] = None):
    if base_path is None:
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_library")
    os.makedirs(base_path, exist_ok=True)

    folders = [
        "Vacation_Hawaii_2024",
        "Vacation_Hawaii_2024/Beach_Sunset",
        "Family_Birthdays/Emma_7th_Birthday",
        "Mountain_Hiking_Trip",
        "Downloads_And_Screenshots",
        "Project_Assets"
    ]

    for f in folders:
        os.makedirs(os.path.join(base_path, f), exist_ok=True)

    print(f"Creating sample photos in: {base_path}")

    # 1. Sunset on the beach (Canon EOS R5)
    sunset_path = os.path.join(base_path, "Vacation_Hawaii_2024/Beach_Sunset", "IMG_4821_sunset.jpg")
    img1 = Image.new("RGB", (1920, 1080), color=(240, 100, 40))
    d1 = ImageDraw.Draw(img1)
    # Draw ocean and sun
    d1.rectangle([(0, 600), (1920, 1080)], fill=(20, 60, 140))
    d1.ellipse([(860, 450), (1060, 650)], fill=(255, 230, 80))
    
    exif1 = {
        "0th": {
            piexif.ImageIFD.Make: "Canon",
            piexif.ImageIFD.Model: "Canon EOS R5",
            piexif.ImageIFD.Software: "Adobe Lightroom 13.2"
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: "2024:08:14 19:42:10",
            piexif.ExifIFD.ISOSpeedRatings: 100,
            piexif.ExifIFD.FNumber: (40, 10), # f/4.0
            piexif.ExifIFD.ExposureTime: (1, 500),
            piexif.ExifIFD.FocalLength: (35, 1),
            piexif.ExifIFD.LensModel: "RF 24-70mm F2.8 L IS USM"
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: "N",
            piexif.GPSIFD.GPSLatitude: ((21, 1), (18, 1), (45, 1)), # Hawaii
            piexif.GPSIFD.GPSLongitudeRef: "W",
            piexif.GPSIFD.GPSLongitude: ((157, 1), (51, 1), (30, 1)),
            piexif.GPSIFD.GPSAltitude: (5, 1)
        }
    }
    img1.save(sunset_path, "jpeg", quality=95, exif=piexif.dump(exif1))

    # Duplicate of sunset in Vacation root
    sunset_dup = os.path.join(base_path, "Vacation_Hawaii_2024", "IMG_4821_sunset_backup.jpg")
    shutil.copy2(sunset_path, sunset_dup)

    # 2. Birthday cake celebration (Apple iPhone 15 Pro)
    cake_path = os.path.join(base_path, "Family_Birthdays/Emma_7th_Birthday", "IMG_0932_cake.jpg")
    img2 = Image.new("RGB", (1600, 1200), color=(60, 30, 80))
    d2 = ImageDraw.Draw(img2)
    d2.rectangle([(500, 600), (1100, 1000)], fill=(230, 190, 140)) # Cake
    d2.rectangle([(750, 480), (780, 600)], fill=(255, 255, 255)) # Candle
    d2.ellipse([(740, 420), (790, 480)], fill=(255, 180, 20)) # Flame
    
    exif2 = {
        "0th": {
            piexif.ImageIFD.Make: "Apple",
            piexif.ImageIFD.Model: "iPhone 15 Pro",
            piexif.ImageIFD.Software: "iOS 18.1"
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: "2024:11:05 17:15:30",
            piexif.ExifIFD.ISOSpeedRatings: 400,
            piexif.ExifIFD.FNumber: (18, 10), # f/1.8
            piexif.ExifIFD.ExposureTime: (1, 60),
            piexif.ExifIFD.FocalLength: (24, 1),
            piexif.ExifIFD.LensModel: "iPhone 15 Pro back triple camera 6.86mm f/1.78"
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: "N",
            piexif.GPSIFD.GPSLatitude: ((37, 1), (46, 1), (0, 1)),
            piexif.GPSIFD.GPSLongitudeRef: "W",
            piexif.GPSIFD.GPSLongitude: ((122, 1), (25, 1), (0, 1))
        }
    }
    img2.save(cake_path, "jpeg", quality=92, exif=piexif.dump(exif2))

    # 3. Snowy mountain peak (Sony Alpha 7 IV)
    mountain_path = os.path.join(base_path, "Mountain_Hiking_Trip", "DSC09241_mountain.jpg")
    img3 = Image.new("RGB", (2000, 1333), color=(140, 180, 230))
    d3 = ImageDraw.Draw(img3)
    d3.polygon([(300, 1333), (1000, 300), (1700, 1333)], fill=(240, 245, 255)) # Snowy peak
    d3.polygon([(700, 1333), (1400, 450), (2000, 1333)], fill=(210, 220, 240))
    
    exif3 = {
        "0th": {
            piexif.ImageIFD.Make: "Sony",
            piexif.ImageIFD.Model: "ILCE-7M4",
            piexif.ImageIFD.Software: "ILCE-7M4 v2.00"
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: "2025:01:20 11:30:00",
            piexif.ExifIFD.ISOSpeedRatings: 100,
            piexif.ExifIFD.FNumber: (80, 10), # f/8.0
            piexif.ExifIFD.ExposureTime: (1, 1000),
            piexif.ExifIFD.FocalLength: (70, 1),
            piexif.ExifIFD.LensModel: "FE 24-105mm F4 G OSS"
        }
    }
    img3.save(mountain_path, "jpeg", quality=95, exif=piexif.dump(exif3))

    # 4. Dog playing on green grass (Nikon Z8)
    dog_path = os.path.join(base_path, "Vacation_Hawaii_2024", "NZ8_3021_dog_park.jpg")
    img4 = Image.new("RGB", (1800, 1200), color=(40, 160, 60))
    d4 = ImageDraw.Draw(img4)
    d4.ellipse([(700, 500), (1100, 800)], fill=(160, 110, 60)) # Dog body
    d4.ellipse([(1000, 400), (1200, 600)], fill=(160, 110, 60)) # Dog head
    
    exif4 = {
        "0th": {
            piexif.ImageIFD.Make: "Nikon",
            piexif.ImageIFD.Model: "NIKON Z 8",
            piexif.ImageIFD.Software: "Ver.01.00"
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: "2024:08:18 15:10:00",
            piexif.ExifIFD.ISOSpeedRatings: 250,
            piexif.ExifIFD.FNumber: (28, 10),
            piexif.ExifIFD.ExposureTime: (1, 2000),
            piexif.ExifIFD.FocalLength: (85, 1),
            piexif.ExifIFD.LensModel: "NIKKOR Z 85mm f/1.2 S"
        }
    }
    img4.save(dog_path, "jpeg", quality=95, exif=piexif.dump(exif4))

    # 5. Screenshot (Excluded by classifier)
    screen_path = os.path.join(base_path, "Downloads_And_Screenshots", "Screenshot 2026-08-15 at 14.30.12.png")
    img_screen = Image.new("RGB", (1920, 1080), color=(30, 32, 40))
    d_s = ImageDraw.Draw(img_screen)
    d_s.rectangle([(100, 100), (1820, 980)], outline=(100, 120, 150), width=2)
    img_screen.save(screen_path, "png")

    # 6. Small App Icon (Excluded by classifier)
    icon_path = os.path.join(base_path, "Project_Assets", "button_icon_256.png")
    img_icon = Image.new("RGBA", (256, 256), color=(0, 0, 0, 0))
    d_i = ImageDraw.Draw(img_icon)
    d_i.ellipse([(20, 20), (236, 236)], fill=(16, 185, 129, 255))
    img_icon.save(icon_path, "png")

    print("[SUCCESS] Sample photo library generated successfully!")
    print(f"Directory: {base_path}")
    return base_path

if __name__ == "__main__":
    create_sample_library()

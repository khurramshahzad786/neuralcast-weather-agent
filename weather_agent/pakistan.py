"""Major Pakistani cities: name -> (latitude, longitude, province/territory).

Kept offline so a country-wide scan needs no geocoding calls.
"""

PAKISTAN_CITIES: dict[str, tuple[float, float, str]] = {
    "Karachi": (24.8608, 67.0104, "Sindh"),
    "Lahore": (31.5497, 74.3436, "Punjab"),
    "Islamabad": (33.7215, 73.0433, "Islamabad Capital Territory"),
    "Rawalpindi": (33.6007, 73.0679, "Punjab"),
    "Faisalabad": (31.4180, 73.0790, "Punjab"),
    "Multan": (30.1968, 71.4782, "Punjab"),
    "Peshawar": (34.0080, 71.5785, "Khyber Pakhtunkhwa"),
    "Quetta": (30.1841, 67.0014, "Balochistan"),
    "Hyderabad": (25.3960, 68.3578, "Sindh"),
    "Sialkot": (32.4927, 74.5313, "Punjab"),
    "Gujranwala": (32.1557, 74.1871, "Punjab"),
    "Sukkur": (27.7052, 68.8574, "Sindh"),
    "Bahawalpur": (29.3956, 71.6836, "Punjab"),
    "Larkana": (27.5590, 68.2120, "Sindh"),
    "Abbottabad": (34.1463, 73.2117, "Khyber Pakhtunkhwa"),
    "Murree": (33.9070, 73.3943, "Punjab"),
    "Gilgit": (35.9208, 74.3089, "Gilgit-Baltistan"),
    "Skardu": (35.2971, 75.6333, "Gilgit-Baltistan"),
    "Muzaffarabad": (34.3700, 73.4711, "Azad Kashmir"),
    "Gwadar": (25.1264, 62.3225, "Balochistan"),
}

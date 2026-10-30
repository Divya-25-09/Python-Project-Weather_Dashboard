"""
Weather Dashboard
-----------------
A beginner-friendly desktop app built with Tkinter.

Features:
  - Search any city and see its current weather + 5-day forecast
  - Uses the free Open-Meteo API (no API key needed)
  - Saves every searched city in a local SQLite database
  - Double-click a saved city to load its weather again

Run:
  pip install requests
  python weather_dashboard.py
"""

import os
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime

import requests

# Store the database file next to this script, wherever it is run from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "weather.db")

# ---------------------------------------------------------------------------
# API helpers (Open-Meteo -- free, no API key required)
# ---------------------------------------------------------------------------

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes -> (description, emoji)
WEATHER_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Icy fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Heavy drizzle", "🌦️"),
    56: ("Freezing drizzle", "🌧️"),
    57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌧️"),
    63: ("Rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"),
    67: ("Freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"),
    73: ("Snow", "🌨️"),
    75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "🌨️"),
    80: ("Light showers", "🌦️"),
    81: ("Showers", "🌦️"),
    82: ("Violent showers", "⛈️"),
    85: ("Snow showers", "🌨️"),
    86: ("Snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Storm with hail", "⛈️"),
    99: ("Storm with hail", "⛈️"),
}


def describe_weather(code):
    """Turn a WMO weather code into a (description, emoji) pair."""
    return WEATHER_CODES.get(code, ("Unknown", "🌡️"))


def geocode_city(city):
    """
    Convert a city name into coordinates using Open-Meteo's geocoding API.
    Returns (display_name, latitude, longitude), or None if not found.
    Raises requests.RequestException on network failure.
    """
    params = {"name": city, "count": 1, "language": "en", "format": "json"}
    resp = requests.get(GEOCODE_URL, params=params, timeout=10)
    resp.raise_for_status()  # raises if the server returned an error page
    data = resp.json()       # parse the JSON body into a Python dict

    results = data.get("results")
    if not results:
        return None

    place = results[0]
    name = place["name"]
    country = place.get("country", "")
    display = f"{name}, {country}" if country else name
    return display, place["latitude"], place["longitude"]


def fetch_weather(latitude, longitude):
    """
    Fetch current weather + 5-day forecast for a pair of coordinates.
    Returns the parsed JSON as a Python dict.
    Raises requests.RequestException on network failure.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 5,
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# SQLite helpers -- remembers every city you search
# ---------------------------------------------------------------------------

def init_db(path=DB_PATH):
    """Create the cities table if it doesn't exist yet."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            searched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_city(name, latitude, longitude, path=DB_PATH):
    """Insert a city, or refresh it if it was already saved."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO cities (name, latitude, longitude, searched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            searched_at = excluded.searched_at
        """,
        (name, latitude, longitude, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_saved_cities(path=DB_PATH):
    """Return [(name, latitude, longitude), ...], most recent first."""
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT name, latitude, longitude FROM cities ORDER BY searched_at DESC"
    ).fetchall()
    conn.close()
    return rows


def delete_city(name, path=DB_PATH):
    """Remove one city from the saved list."""
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM cities WHERE name = ?", (name,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tkinter GUI
# ---------------------------------------------------------------------------

class WeatherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Weather Dashboard")
        self.geometry("560x660")
        self.resizable(False, False)
        init_db()
        self._saved_rows = []
        self._build_ui()
        self.refresh_saved_list()

    def _build_ui(self):
        # --- search bar ---
        search_frame = ttk.Frame(self, padding=12)
        search_frame.pack(fill="x")

        ttk.Label(search_frame, text="City:").pack(side="left")
        self.city_entry = ttk.Entry(search_frame, width=30)
        self.city_entry.pack(side="left", padx=8)
        self.city_entry.bind("<Return>", lambda event: self.search())
        ttk.Button(search_frame, text="Get Weather",
                   command=self.search).pack(side="left")

        # --- current weather ---
        current_frame = ttk.LabelFrame(self, text="Current Weather", padding=12)
        current_frame.pack(fill="x", padx=12, pady=6)

        self.place_label = ttk.Label(current_frame,
                                     text="Search a city to begin",
                                     font=("Segoe UI", 13, "bold"))
        self.place_label.pack(anchor="w")
        self.temp_label = ttk.Label(current_frame, text="",
                                    font=("Segoe UI", 28))
        self.temp_label.pack(anchor="w")
        self.desc_label = ttk.Label(current_frame, text="",
                                    font=("Segoe UI", 11))
        self.desc_label.pack(anchor="w")
        self.details_label = ttk.Label(current_frame, text="",
                                       font=("Segoe UI", 10))
        self.details_label.pack(anchor="w", pady=(4, 0))

        # --- 5-day forecast ---
        forecast_frame = ttk.LabelFrame(self, text="5-Day Forecast", padding=12)
        forecast_frame.pack(fill="x", padx=12, pady=6)

        self.forecast_cells = []
        row = ttk.Frame(forecast_frame)
        row.pack(fill="x")
        for _ in range(5):
            cell = ttk.Frame(row, padding=6)
            cell.pack(side="left", expand=True, fill="x")
            day = ttk.Label(cell, text="", font=("Segoe UI", 10, "bold"),
                            anchor="center")
            day.pack()
            icon = ttk.Label(cell, text="", font=("Segoe UI", 18),
                             anchor="center")
            icon.pack()
            temps = ttk.Label(cell, text="", font=("Segoe UI", 10),
                              anchor="center")
            temps.pack()
            self.forecast_cells.append((day, icon, temps))

        # --- saved cities ---
        saved_frame = ttk.LabelFrame(self,
                                     text="Saved Cities (double-click to load)",
                                     padding=12)
        saved_frame.pack(fill="both", expand=True, padx=12, pady=6)

        self.saved_listbox = tk.Listbox(saved_frame, height=6)
        self.saved_listbox.pack(side="left", fill="both", expand=True)
        self.saved_listbox.bind("<Double-Button-1>", self.load_saved_city)

        btn_frame = ttk.Frame(saved_frame)
        btn_frame.pack(side="left", padx=(8, 0))
        ttk.Button(btn_frame, text="Delete",
                   command=self.delete_selected).pack(pady=2)

    # --- actions ---

    def search(self):
        city = self.city_entry.get().strip()
        if not city:
            messagebox.showwarning("Missing input",
                                   "Please enter a city name.")
            return
        try:
            place = geocode_city(city)
        except requests.RequestException:
            messagebox.showerror("Network error",
                                 "Could not reach the weather service.\n"
                                 "Check your internet connection.")
            return
        if place is None:
            messagebox.showinfo("Not found",
                                f'No results for "{city}". Try another spelling.')
            return
        name, lat, lon = place
        self.show_weather(name, lat, lon)
        save_city(name, lat, lon)   # remember it for next time
        self.refresh_saved_list()

    def load_saved_city(self, event=None):
        selected = self.saved_listbox.curselection()
        if not selected:
            return
        name, lat, lon = self._saved_rows[selected[0]]
        self.show_weather(name, lat, lon)

    def delete_selected(self):
        selected = self.saved_listbox.curselection()
        if not selected:
            return
        delete_city(self._saved_rows[selected[0]][0])
        self.refresh_saved_list()

    def show_weather(self, name, lat, lon):
        try:
            data = fetch_weather(lat, lon)
        except requests.RequestException:
            messagebox.showerror("Network error",
                                 "Could not reach the weather service.\n"
                                 "Check your internet connection.")
            return

        current = data["current"]
        desc, emoji = describe_weather(current["weather_code"])
        self.place_label.config(text=name)
        self.temp_label.config(text=f"{current['temperature_2m']:.0f}°C {emoji}")
        self.desc_label.config(text=desc)
        self.details_label.config(
            text=(f"Feels like {current['apparent_temperature']:.0f}°C   •   "
                  f"Humidity {current['relative_humidity_2m']}%   •   "
                  f"Wind {current['wind_speed_10m']:.0f} km/h")
        )

        daily = data["daily"]
        for i, (day_lbl, icon_lbl, temps_lbl) in enumerate(self.forecast_cells):
            date = datetime.strptime(daily["time"][i], "%Y-%m-%d")
            _, emoji = describe_weather(daily["weather_code"][i])
            day_lbl.config(text=date.strftime("%a"))
            icon_lbl.config(text=emoji)
            temps_lbl.config(
                text=f"{daily['temperature_2m_max'][i]:.0f}° / "
                     f"{daily['temperature_2m_min'][i]:.0f}°"
            )

    def refresh_saved_list(self):
        self._saved_rows = get_saved_cities()
        self.saved_listbox.delete(0, tk.END)
        for name, lat, lon in self._saved_rows:
            self.saved_listbox.insert(tk.END, name)


if __name__ == "__main__":
    app = WeatherApp()
    app.mainloop()

# scripts/fetch_and_store.py
import requests
import polars as pl
import sqlite3
from datetime import datetime, timedelta

# Список городов с координатами
CITIES = {
    "London": (51.5074, -0.1278),
    "Tokyo": (35.6895, 139.6917),
    "New York": (40.7128, -74.0060),
    "Moscow": (55.7558, 37.6173),
    "Paris": (48.8566, 2.3522),
    "Beijing": (39.9042, 116.4074),
    "Berlin": (52.5200, 13.4050),
    "Istanbul": (41.0082, 28.9784),
    "Madrid": (40.4168, -3.7038),
    "Rome": (41.9028, 12.4964),
    "Cairo": (30.0444, 31.2357),
    "Dubai": (25.276987, 55.296249),
    "Sydney": (-33.8688, 151.2093),
    "Los Angeles": (34.0522, -118.2437),
    "Singapore": (1.3521, 103.8198),
    "Seoul": (37.5665, 126.9780),
    "Bangkok": (13.7563, 100.5018),
    "Rio de Janeiro": (-22.9068, -43.1729),
    "Cape Town": (-33.9249, 18.4241),
    "Toronto": (43.6532, -79.3832),
}

# DB_PATH = "../data/weather.db" # Этот путь будет относительно /opt/airflow/project в контейнере
DB_PATH = "/opt/airflow/project/data/weather.db" # Абсолютный путь в контейнере

def get_weather_data(lat, lon, city_name):
    # Исторические данные: последние 90 дней
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=90)

    # ИСПРАВЛЕНО: Удалены лишние пробелы в URL
    hist_url = "https://archive-api.open-meteo.com/v1/archive"
    hist_params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "timezone": "UTC"
    }

    # Прогноз на 7 дней
    # ИСПРАВЛЕНО: Удалены лишние пробелы в URL
    forecast_url = "https://api.open-meteo.com/v1/forecast"
    forecast_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "forecast_days": 7,
        "timezone": "UTC"
    }

    # Запросы
    hist_resp = requests.get(hist_url, params=hist_params)
    forecast_resp = requests.get(forecast_url, params=forecast_params)

    if not hist_resp.ok or not forecast_resp.ok:
        raise Exception(f"API error for {city_name}")

    hist_data = hist_resp.json()["hourly"]
    forecast_data = forecast_resp.json()["hourly"]

    # Объединяем
    all_time = hist_data["time"] + forecast_data["time"]
    all_temp = hist_data["temperature_2m"] + forecast_data["temperature_2m"]
    all_precip = hist_data["precipitation"] + forecast_data["precipitation"]
    all_wind = hist_data["wind_speed_10m"] + forecast_data["wind_speed_10m"]

    df = pl.DataFrame({
        "timestamp": pl.Series(all_time).str.to_datetime(),
        "city": city_name,
        "temperature": all_temp,
        "precipitation": all_precip,
        "wind_speed": all_wind
    })

    # Агрегация по дням
    df_daily = df.group_by(
        pl.col("city"),
        pl.col("timestamp").dt.date().alias("date")
    ).agg(
        pl.col("temperature").mean().alias("avg_temp"),
        pl.col("precipitation").sum().alias("total_precip"),
        pl.col("wind_speed").mean().alias("avg_wind")
    ).sort("date")

    # Флаг дождливого дня
    df_daily = df_daily.with_columns(
        (pl.col("total_precip") > 1.0).cast(pl.Int8).alias("is_rainy")
    )

    return df_daily

def save_to_db(df: pl.DataFrame):
    conn = sqlite3.connect(DB_PATH)
    # Преобразуем в pandas для удобства записи в SQLite
    df.to_pandas().to_sql("weather", conn, if_exists="append", index=False)
    conn.close()

def deduplicate_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM weather
        WHERE rowid NOT IN (
            SELECT MIN(rowid)
            FROM weather
            GROUP BY city, date
        )
    """)
    conn.commit()
    conn.close()

# --- НОВЫЕ ФУНКЦИИ, КОТОРЫЕ ИМПОРТИРУЕТСЯ В DAG ---
def fetch_historical():
    print("Fetching historical weather data...")
    all_data = []
    for city, (lat, lon) in CITIES.items():
        print(f"Processing historical data for {city}...")
        # Получаем полные данные (включая историю)
        df = get_weather_data(lat, lon, city)
        # Оставляем только исторические (до сегодняшнего дня)
        today = datetime.utcnow().date()
        df_hist = df.filter(pl.col("date") < today)
        all_data.append(df_hist)

    if all_data:
        full_df = pl.concat(all_data)
        save_to_db(full_df)
        deduplicate_db()
        print("✅ Historical data saved and deduplicated.")
    else:
        print("⚠️ No historical data to save.")


def fetch_forecast():
    print("Fetching forecast weather data...")
    all_data = []
    for city, (lat, lon) in CITIES.items():
        print(f"Processing forecast data for {city}...")
        # Получаем полные данные (включая прогноз)
        df = get_weather_data(lat, lon, city)
        # Оставляем только прогноз (сегодня и вперёд)
        today = datetime.utcnow().date()
        df_forecast = df.filter(pl.col("date") >= today)
        all_data.append(df_forecast)

    if all_data:
        full_df = pl.concat(all_data)
        save_to_db(full_df)
        deduplicate_db()
        print("✅ Forecast data saved and deduplicated.")
    else:
        print("⚠️ No forecast data to save.")


# --- ОРИГИНАЛЬНАЯ ФУНКЦИЯ main() ---
def main():
    print("Fetching weather data...")
    all_data = []
    for city, (lat, lon) in CITIES.items():
        print(f"Processing {city}...")
        df = get_weather_data(lat, lon, city)
        all_data.append(df)

    if all_data: # Добавлена проверка
        full_df = pl.concat(all_data)
        save_to_db(full_df)
        deduplicate_db()
        print("✅ Data saved and deduplicated.")
    else:
        print("⚠️ No data to save.")

if __name__ == "__main__":
    main()

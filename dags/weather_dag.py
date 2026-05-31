# dags/weather_dag.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import os

# Абсолютный путь к папке scripts внутри контейнера
SCRIPTS_DIR = '/opt/airflow/project/scripts'
sys.path.insert(0, SCRIPTS_DIR)

from fetch_and_store import fetch_historical, fetch_forecast

default_args = {
    'owner': 'student',
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'weather_pipeline',
    default_args=default_args,
    description='Fetch forecast + historical weather',
    schedule_interval='@hourly',  # каждый день
    # schedule_interval='*/60 * * * *',  # каждый день
    start_date=datetime(2025, 10, 1),
    catchup=False,
)

# 1. Получить свежий прогноз (на сегодня и завтра)
forecast_task = PythonOperator(
    task_id='fetch_forecast',
    python_callable=fetch_forecast,
    dag=dag,
)

# 2. Получить вчерашние реальные данные
historical_task = PythonOperator(
    task_id='fetch_historical',
    python_callable=fetch_historical,
    dag=dag,
)


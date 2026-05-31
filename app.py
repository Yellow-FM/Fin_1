import streamlit as st
import sqlite3
import polars as pl
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import date, timedelta

st.set_page_config(page_title="Просмотр данных", layout="wide")
st.title("📊 Интерактивный анализ метеорологических данных")

DB_PATH = "data/weather.db"

@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pl.read_database("SELECT * FROM weather ORDER BY date", conn)
    conn.close()
    return df

try:
    df_raw = load_data()
except Exception as e:
    st.error("❌ Не удалось загрузить данные. Убедитесь, что база данных существует и доступна.")
    st.stop()

def add_derived_columns(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        pl.when(pl.col("avg_temp") < 10).then(pl.lit("Холодно"))
        .when(pl.col("avg_temp") <= 25).then(pl.lit("Умеренно"))
        .otherwise(pl.lit("Жарко"))
        .alias("temp_category")
    )
    df = df.with_columns(
        pl.when(pl.col("total_precip") == 0).then(pl.lit("Без осадков"))
        .when(pl.col("total_precip") <= 5).then(pl.lit("Небольшие"))
        .otherwise(pl.lit("Сильные"))
        .alias("precip_level")
    )
    df = df.with_columns(
        pl.when(
            (pl.col("avg_temp") >= 18) & (pl.col("avg_temp") <= 25) & (pl.col("avg_wind") < 5)
        ).then(pl.lit("Комфортно"))
        .otherwise(pl.lit("Дискомфортно"))
        .alias("comfort_index")
    )
    return df
df = add_derived_columns(df_raw)
min_date = df["date"].min()
max_date = df["date"].max()
st.sidebar.header("🔍 Фильтры")
cities = sorted(df["city"].unique().to_list())
selected_city = st.sidebar.selectbox("Выберите город", cities, index=0)
date_range = st.sidebar.date_input(
    "Диапазон дат",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
if isinstance(date_range, (date,)):
    start_date = date_range
    end_date = date_range
elif len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date
city_data = df.filter(
    (pl.col("city") == selected_city) &
    (pl.col("date") >= str(start_date)) &
    (pl.col("date") <= str(end_date))
)
st.subheader(f"📊 Статистика для {selected_city} ({start_date} – {end_date})")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Записей", city_data.shape[0])
col2.metric("Средняя температура", f"{city_data['avg_temp'].mean():.1f}°C")
col3.metric("Макс. осадков", f"{city_data['total_precip'].max():.1f} мм")
col4.metric("Дождливых дней", city_data["is_rainy"].sum())
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📋 Данные", "📈 Распределения", "🏙️ Сравнение городов", "⏳ Временные ряды", "⚠️ Аномалии"]
)
with tab1:
    st.subheader("📋 Данные с производными показателями")
    disp_df = city_data.to_pandas()
    all_columns = disp_df.columns.tolist()
    default_columns = ["date", "avg_temp", "total_precip", "avg_wind", "is_rainy",
                       "temp_category", "precip_level", "comfort_index"]
    selected_cols = st.multiselect(
        "Выберите столбцы для отображения",
        options=all_columns,
        default=[c for c in default_columns if c in all_columns]
    )
    if selected_cols:
        st.dataframe(
            disp_df[selected_cols],
            use_container_width=True,
            hide_index=True,
            height=400
        )
    else:
        st.info("Выберите хотя бы один столбец для отображения.")
with tab2:
    st.subheader("📈 Разведочный анализ распределений")
    if city_data.is_empty():
        st.warning("Нет данных для выбранного города и периода.")
    else:
        metric = st.selectbox(
            "Выберите показатель",
            options=["avg_temp", "total_precip", "avg_wind"],
            format_func=lambda x: {"avg_temp": "Температура",
                                   "total_precip": "Осадки",
                                   "avg_wind": "Ветер"}[x]
        )
        pds = city_data.to_pandas()
        col_h, col_b = st.columns(2)
        with col_h:
            fig_hist = px.histogram(pds, x=metric, nbins=30, title=f"Гистограмма: {metric}")
            st.plotly_chart(fig_hist, use_container_width=True)
        with col_b:
            fig_box = px.box(pds, y=metric, title=f"Boxplot: {metric}")
            st.plotly_chart(fig_box, use_container_width=True)

        st.write("**Описательная статистика**")
        st.dataframe(pds[[metric]].describe(), use_container_width=True)
with tab3:
    st.subheader("🏙️ Сравнение погодных показателей между городами")
    cities_for_compare = st.multiselect(
        "Выберите города для сравнения",
        options=cities,
        default=cities[:min(3, len(cities))]  # первые 3 по умолчанию
    )
    compare_df = df.filter(
        (pl.col("date") >= str(start_date)) &
        (pl.col("date") <= str(end_date)) &
        (pl.col("city").is_in(cities_for_compare))
    )
    if cities_for_compare and not compare_df.is_empty():
        comp_pd = compare_df.to_pandas()
        agg_metrics = comp_pd.groupby("city")[["avg_temp", "total_precip", "avg_wind"]].mean().reset_index()
        metric_comp = st.selectbox(
            "Показатель для сравнения",
            options=["avg_temp", "total_precip", "avg_wind"],
            format_func=lambda x: {"avg_temp": "Средняя температура",
                                   "total_precip": "Сумма осадков",
                                   "avg_wind": "Скорость ветра"}[x]
        )
        fig_bar = px.bar(
            agg_metrics,
            x="city",
            y=metric_comp,
            color="city",
            title=f"{metric_comp} по городам (среднее за период)",
            labels={"city": "Город", metric_comp: metric_comp}
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        st.write("**Средние значения**")
        st.dataframe(agg_metrics, use_container_width=True, hide_index=True)
    else:
        st.info("Выберите города и/или подходящий период.")
with tab4:
    st.subheader("⏳ Динамика температуры и простой прогноз")
    if city_data.is_empty():
        st.warning("Нет данных для отображения.")
    else:
        ts_pd = city_data.to_pandas().sort_values("date")
        ts_metric = st.selectbox(
            "Показатель",
            options=["avg_temp"],
            format_func=lambda x: "Средняя температура"
        )
        window = st.slider("Окно скользящего среднего (дней)", min_value=2, max_value=30, value=7)
        ts_pd["SMA"] = ts_pd[ts_metric].rolling(window=window, center=True).mean()
        fig_ts = go.Figure()
        fig_ts.add_trace(go.Scatter(
            x=ts_pd["date"], y=ts_pd[ts_metric],
            mode='lines+markers', name='Факт',
            line=dict(width=2)
        ))
        fig_ts.add_trace(go.Scatter(
            x=ts_pd["date"], y=ts_pd["SMA"],
            mode='lines', name=f'SMA ({window} дн.)',
            line=dict(width=2, dash='dash')
        ))
        today = date.today()
        if start_date <= today <= end_date:
            fig_ts.add_vline(x=today, line_width=1, line_dash="dot", line_color="gray")
            fig_ts.add_annotation(x=today, y=1, yref="paper", text="Сегодня", showarrow=False)

        fig_ts.update_layout(
            title=f"Динамика {ts_metric} с прогнозом скользящим средним",
            xaxis_title="Дата",
            yaxis_title="Температура (°C)" if ts_metric == "avg_temp" else ts_metric,
            hovermode="x unified"
        )
        st.plotly_chart(fig_ts, use_container_width=True)

        st.caption("Пунктирная линия показывает скользящее среднее за выбранное окно. "
                   "Вертикальная линия — сегодняшний день.")
with tab5:
    st.subheader("⚠️ Дни с аномальными осадками (по критерию is_rainy = 1)")
    anomalies = city_data.filter(pl.col("is_rainy") == 1)
    if not anomalies.is_empty():
        st.write(f"Найдено {anomalies.shape[0]} дождливых дней в {selected_city} за выбранный период.")
        st.dataframe(anomalies.to_pandas(), use_container_width=True, hide_index=True)
    else:
        st.info("В выбранном периоде нет дождливых дней (is_rainy = 1).")
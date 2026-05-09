import io
import zipfile
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import yfinance as yf


st.set_page_config(
    page_title="yFinance Equity Downloader",
    layout="wide",
)

st.title("yFinance Equity Data Downloader")
st.write(
    "Upload a CSV with a `Symbol` column, select a date range and timeframe, "
    "then download one CSV file for each symbol."
)


TIMEFRAME_OPTIONS = {
    "Daily": "1d",
    "Weekly": "1wk",
    "Monthly": "1mo",
}


def normalize_symbol(value):
    if pd.isna(value):
        return ""

    symbol = str(value).strip().upper()
    if symbol and "." not in symbol:
        symbol = f"{symbol}.NS"

    return symbol


def make_safe_file_name(symbol, timeframe, start_date, end_date):
    safe_symbol = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
    return f"{safe_symbol}_{timeframe.lower()}_{start_date}_{end_date}.csv"


@st.cache_data(show_spinner=False)
def fetch_history(symbol, start_date, end_date, interval):
    try:
        data = yf.download(
            tickers=symbol,
            start=start_date,
            end=end_date,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
            multi_level_index=False,
        )
    except Exception as exc:
        return pd.DataFrame(), f"{symbol}: {exc}"

    if data is None or data.empty:
        return pd.DataFrame(), f"{symbol}: No data found"

    data = data.reset_index()

    if "Datetime" in data.columns:
        data = data.rename(columns={"Datetime": "Date"})
    elif "index" in data.columns:
        data = data.rename(columns={"index": "Date"})

    data.insert(0, "Symbol", symbol)
    return data, ""


def build_zip(csv_files):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_name, csv_bytes in csv_files.items():
            zip_file.writestr(file_name, csv_bytes)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

date_col1, date_col2, timeframe_col = st.columns(3)

with date_col1:
    start_date = st.date_input("Start date", value=date.today() - timedelta(days=365))

with date_col2:
    end_date = st.date_input("End date", value=date.today())

with timeframe_col:
    selected_timeframe = st.selectbox("Time frame", list(TIMEFRAME_OPTIONS.keys()))

if uploaded_file is None:
    st.info("Upload a CSV file with a column named `Symbol` to begin.")
    st.stop()

try:
    input_data = pd.read_csv(uploaded_file)
except Exception as exc:
    st.error(f"Could not read the CSV file: {exc}")
    st.stop()

if "Symbol" not in input_data.columns:
    st.error('The uploaded CSV must contain a column named "Symbol".')
    st.stop()

symbols = input_data["Symbol"].apply(normalize_symbol)
symbols = [symbol for symbol in symbols.drop_duplicates().tolist() if symbol]

st.subheader("Symbols found")
st.dataframe(pd.DataFrame({"Symbol": symbols}), width="stretch")

if not symbols:
    st.warning("No valid symbols were found in the Symbol column.")
    st.stop()

if start_date > end_date:
    st.error("Start date must be earlier than or equal to end date.")
    st.stop()

if "csv_files" not in st.session_state:
    st.session_state.csv_files = {}
if "preview_data" not in st.session_state:
    st.session_state.preview_data = pd.DataFrame()
if "download_errors" not in st.session_state:
    st.session_state.download_errors = []
if "zip_file_name" not in st.session_state:
    st.session_state.zip_file_name = ""

if st.button("Fetch data", type="primary"):
    interval = TIMEFRAME_OPTIONS[selected_timeframe]
    download_end_date = end_date + timedelta(days=1)
    csv_files = {}
    preview_frames = []
    errors = []

    progress = st.progress(0)
    status = st.empty()

    for index, symbol in enumerate(symbols, start=1):
        status.write(f"Downloading {symbol} ({index}/{len(symbols)})...")

        history, error = fetch_history(
            symbol=symbol,
            start_date=start_date.isoformat(),
            end_date=download_end_date.isoformat(),
            interval=interval,
        )

        if error:
            errors.append(error)
        else:
            file_name = make_safe_file_name(
                symbol=symbol,
                timeframe=selected_timeframe,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
            csv_files[file_name] = history.to_csv(index=False).encode("utf-8")
            preview_frames.append(history.head(5))

        progress.progress(index / len(symbols))

    status.empty()

    st.session_state.csv_files = csv_files
    st.session_state.preview_data = (
        pd.concat(preview_frames, ignore_index=True) if preview_frames else pd.DataFrame()
    )
    st.session_state.download_errors = errors
    st.session_state.zip_file_name = (
        f"equity_data_{selected_timeframe.lower()}_"
        f"{start_date.isoformat()}_{end_date.isoformat()}.zip"
    )

    if not csv_files:
        st.error("No data could be downloaded for the uploaded symbols.")
        st.stop()

if st.session_state.download_errors:
    with st.expander("Symbols with issues"):
        for error in st.session_state.download_errors:
            st.write(error)

if st.session_state.csv_files:
    st.success(f"Data downloaded for {len(st.session_state.csv_files)} symbol(s).")

    if not st.session_state.preview_data.empty:
        st.subheader("Preview")
        st.dataframe(st.session_state.preview_data, width="stretch")

    st.download_button(
        label="Download all CSV files as ZIP",
        data=build_zip(st.session_state.csv_files),
        file_name=st.session_state.zip_file_name,
        mime="application/zip",
        type="primary",
    )

    st.subheader("Individual downloads")
    for file_name, csv_bytes in st.session_state.csv_files.items():
        st.download_button(
            label=f"Download {file_name}",
            data=csv_bytes,
            file_name=file_name,
            mime="text/csv",
        )

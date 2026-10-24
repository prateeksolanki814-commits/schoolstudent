"""Streamlit CSS theme."""
import streamlit as st


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
        html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
        .stApp { background: linear-gradient(135deg, #f7f8ff 0%, #f8faff 45%, #f5f3ff 100%); }
        h1, h2, h3 { font-family: 'Manrope', sans-serif !important; color: #17213e; letter-spacing: -0.025em; }
        h1 { font-size: 2rem !important; font-weight: 800 !important; }
        h2 { font-size: 1.45rem !important; font-weight: 750 !important; }
        [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #eef0f7; }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #222846; }
        [data-testid="stMetric"] { background: #fff; border: 1px solid #edf0fa; padding: 18px 18px 14px; border-radius: 17px; box-shadow: 0 7px 25px rgba(47, 57, 103, .045); }
        [data-testid="stMetricLabel"] { color: #727a91; font-weight: 600; }
        [data-testid="stMetricValue"] { color: #272c54; font-family: 'Manrope', sans-serif; font-weight: 800; }
        .hero { padding: 22px 24px; border-radius: 22px; color: white; background: linear-gradient(115deg, #7626e8 0%, #b62fe8 55%, #db4bd8 100%); margin-bottom: 20px; box-shadow: 0 12px 30px rgba(147, 45, 221, .18); }
        .hero h2 { color: white !important; margin: 0 0 5px 0; font-size: 1.55rem !important; }
        .hero p { margin: 0; opacity: .91; }
        .muted { color: #7c8499; font-size: .92rem; }
        .section-card { background: #fff; border: 1px solid #edf0fa; border-radius: 18px; padding: 18px; box-shadow: 0 7px 25px rgba(47, 57, 103, .04); }
        div.stButton > button, div.stFormSubmitButton > button { border-radius: 10px; font-weight: 650; border: 0; background: linear-gradient(100deg, #8e2ce8, #c12ee4); color: white; min-height: 2.55rem; }
        div.stButton > button:hover, div.stFormSubmitButton > button:hover { color: white; border: 0; filter: brightness(1.04); }
        div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, div[data-testid="stDateInput"] input, div[data-testid="stSelectbox"] div[data-baseweb="select"] { border-radius: 10px; }
        div[data-testid="stDataFrame"] { border: 1px solid #edf0fa; border-radius: 12px; overflow: hidden; }
        .small-note { font-size: .86rem; color: #7d8496; }
        hr { border-color: #e9ebf5; }
        </style>
        """,
        unsafe_allow_html=True,
    )

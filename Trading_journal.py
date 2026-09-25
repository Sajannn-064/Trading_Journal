import base64
import calendar
import datetime
import json
import uuid
from pathlib import Path

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="TRADE JOURNAL - Terminal", layout="wide", page_icon="⚡"
)

# --- REFINED PREMIUM INSTITUTIONAL FINTECH STYLING ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    .stApp {
        background-color: #07090e;
        color: #f1f5f9;
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    #MainMenu, footer {visibility: hidden;}

        /* Make action buttons in the execution log completely flat and transparent on hover */
    div[data-testid="column"] button {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0px !important;
    }
    div[data-testid="column"] button:hover {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        opacity: 0.8;
    }

    /* Sidebar Navigation Styling */
    [data-testid="stSidebar"] {
        background-color: #0d111a;
        border-right: 1px solid #1e293b;
    }
    
    .nav-item {
        padding: 9px 14px;
        color: #94a3b8;
        border-radius: 8px;
        margin-bottom: 4px;
        font-weight: 500;
        font-size: 0.9rem;
    }
    .nav-item-active {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(29, 78, 216, 0.15));
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.3);
        padding: 9px 14px;
        border-radius: 8px;
        margin-bottom: 4px;
        font-weight: 600;
        font-size: 0.9rem;
    }

    [data-testid="stMetric"] {
        background-color: #0d111a;
        border: 1px solid #1e293b;
        padding: 16px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    
    h3 {
        color: #f8fafc;
        font-weight: 600;
        font-size: 1.05rem;
        letter-spacing: -0.01em;
        margin-bottom: 0.5rem;
    }

    .stButton>button {
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        color: white;
        border-radius: 8px;
        font-weight: 600;
        border: none;
        padding: 0.5rem 1rem;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        opacity: 0.9;
        transform: translateY(-1px);
    }
    </style>
""",
    unsafe_allow_html=True,
)

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
  st.markdown("### 🔺 TRADE JOURNAL")
  st.markdown("---")
  st.markdown(
      '<div class="nav-item-active">📊 &nbsp; Dashboard</div>',
      unsafe_allow_html=True,
  )
  st.markdown('<div class="nav-item">📑 &nbsp; Trades</div>', unsafe_allow_html=True)
  st.markdown(
      '<div class="nav-item">📅 &nbsp; Calendar</div>', unsafe_allow_html=True
  )
  st.markdown(
      '<div class="nav-item">📈 &nbsp; Analytics</div>', unsafe_allow_html=True
  )
  st.markdown(
      '<div class="nav-item">⚡ &nbsp; Setups</div>', unsafe_allow_html=True
  )
  st.markdown(
      '<div class="nav-item">🧠 &nbsp; Psychology</div>', unsafe_allow_html=True
  )
  st.markdown(
      '<div class="nav-item">📋 &nbsp; Reports</div>', unsafe_allow_html=True
  )
  st.markdown(
      '<div class="nav-item">⚙️ &nbsp; Settings</div>', unsafe_allow_html=True
  )

  st.markdown("---")
  st.markdown("### 🔐 Gateway")
  account_id_str = st.text_input("Account ID", placeholder="e.g. 52542846")
  SERVER_NAME = st.text_input("Server Name", placeholder="e.g. ICMarketsSC-Demo")
  try:
      ACCOUNT_ID = int(account_id_str) if account_id_str else 0
  except ValueError:
      ACCOUNT_ID = 0
  password = st.text_input("Investor Password", type="password")

  tz_offset = st.number_input(
      "Local Timezone Offset (Hours)",
      value=0.0,
      step=0.5,
      format="%.1f",
      help="Hours to add/subtract from MT5 UTC time to match your local clock.",
  )

  fetch_btn = st.button("Sync Live MT5 Data", use_container_width=True)

  st.markdown("---")
  st.markdown(
      "<p style='color: #64748b; font-size: 0.75rem;'><i>Discipline turns a"
      " plan into results.</i></p>",
      unsafe_allow_html=True,
  )

# --- SCREENSHOT PERSISTENCE HELPERS ---
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_META = SCREENSHOT_DIR / "meta.json"
TRADE_META_FILE = SCREENSHOT_DIR / "trade_meta.json"


def _ensure_ss_dir():
  SCREENSHOT_DIR.mkdir(exist_ok=True)
  if not SCREENSHOT_META.exists():
    SCREENSHOT_META.write_text("[]")


def load_screenshot_meta():
  _ensure_ss_dir()
  try:
    return json.loads(SCREENSHOT_META.read_text())
  except Exception:
    return []


def save_screenshot_meta(records):
  _ensure_ss_dir()
  SCREENSHOT_META.write_text(json.dumps(records, indent=2))


def _save_ss_file(img_bytes):
  _ensure_ss_dir()
  fname = f"{uuid.uuid4().hex}.png"
  (SCREENSHOT_DIR / fname).write_bytes(img_bytes)
  return fname


def delete_screenshot_record(record_id):
  records = load_screenshot_meta()
  rec = next((r for r in records if r["id"] == record_id), None)
  if rec:
    p = SCREENSHOT_DIR / rec["filename"]
    if p.exists():
      p.unlink()
  save_screenshot_meta([r for r in records if r["id"] != record_id])


def add_screenshot_record(ticket, symbol, trade_type, profit, date,
                           img_bytes, category="Uncategorized",
                           tier="—", notes=""):
  fname = _save_ss_file(img_bytes)
  record = {
    "id": uuid.uuid4().hex,
    "ticket": int(ticket),
    "symbol": str(symbol),
    "trade_type": str(trade_type),
    "profit": round(float(profit), 2),
    "date": str(date),
    "category": str(category),
    "tier": str(tier),
    "notes": str(notes),
    "filename": fname,
    "upload_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
  }
  records = load_screenshot_meta()
  records.append(record)
  save_screenshot_meta(records)
  return record


# --- SESSION STATE INITIALIZATION ---
if "notes_dict" not in st.session_state:
  st.session_state["notes_dict"] = {}

if "screenshots_dict" not in st.session_state:
  st.session_state["screenshots_dict"] = {}
  # Restore screenshots saved to disk back into this session
  for _rec in load_screenshot_meta():
    _t = _rec["ticket"]
    _p = SCREENSHOT_DIR / _rec["filename"]
    if _p.exists():
      _b = _p.read_bytes()
      st.session_state["screenshots_dict"].setdefault(_t, [])
      if _b not in st.session_state["screenshots_dict"][_t]:
        st.session_state["screenshots_dict"][_t].append(_b)

if "df_trades" not in st.session_state:
  st.session_state["df_trades"] = pd.DataFrame()

if "ss_categories" not in st.session_state:
  st.session_state["ss_categories"] = [
    "Setup", "Mistake", "Best Trade", "Psychology", "Uncategorized"
  ]

if "trade_meta_dict" not in st.session_state:
  # Restore trade tiers & categories from disk
  try:
    _ensure_ss_dir()
    st.session_state["trade_meta_dict"] = (
        json.loads(TRADE_META_FILE.read_text()) if TRADE_META_FILE.exists() else {}
    )
  except Exception:
    st.session_state["trade_meta_dict"] = {}


# --- TIER SYSTEM ---
TIER_OPTIONS = ["—", "S", "A+", "A", "A-", "B+", "B", "B-", "C", "D"]
TIER_COLORS  = {
  "S":  "#a855f7", "A+": "#10b981", "A":  "#22c55e", "A-": "#84cc16",
  "B+": "#0ea5e9", "B":  "#3b82f6", "B-": "#64748b",
  "C":  "#f97316", "D":  "#ef4444", "—":  "#475569",
}


def load_trade_meta():
  _ensure_ss_dir()
  try:
    return json.loads(TRADE_META_FILE.read_text())
  except Exception:
    return {}


def save_trade_meta(data):
  _ensure_ss_dir()
  TRADE_META_FILE.write_text(json.dumps(data, indent=2))


# --- SESSION HELPER ---
def get_trading_session(utc_hour):
  if 0 <= utc_hour < 8:
    return "Asian"
  elif 8 <= utc_hour < 13:
    return "London"
  elif 13 <= utc_hour < 21:
    return "New York"
  else:
    return "Asian"


def format_duration(seconds):
  if pd.isna(seconds) or seconds <= 0:
    return "1m"
  hours = int(seconds // 3600)
  minutes = int((seconds % 3600) // 60)
  if hours > 0:
    return f"{hours}h {minutes}m"
  return f"{minutes}m" if minutes > 0 else "1m"


def color_pnl_cells(val):
  if isinstance(val, str):
    if "+" in val:
      return "color: #10b981; font-weight: 600;"
    elif "-" in val:
      return "color: #ef4444; font-weight: 600;"
  return ""

  # --- MASSIVE 16:9 CHART VIEWER MODAL (Pair | Buy/Sell | P&L) ---
@st.dialog(" ", width="large")
def show_image_popup(ticket, symbol, trade_type, pnl):
  pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
  pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
  trade_color = "#10b981" if "BUY" in trade_type else "#ef4444"

  st.markdown(
      f"""
      <style>
          /* Expand the outer modal size to nearly full screen */
          [data-baseweb="modal"] {{
              width: 95vw !important;
              max-width: 95vw !important;
          }}
          /* Remove default padding and set overall modal height */
          [data-baseweb="modal"] > div {{
              width: 95vw !important;
              max-width: 95vw !important;
              height: 72vh !important;
              padding: 0px !important;
          }}
          /* Eliminate gap between vertical elements inside the modal */
          [data-baseweb="modal"] [data-testid="stVerticalBlock"] {{
              gap: 0rem !important;
          }}
      </style>
      <div style="padding: 16px 20px 10px 20px;">
          <div style="font-size: 1.25rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.01em;">
              {symbol} &nbsp;|&nbsp; <span style="color: {trade_color};">{trade_type}</span> &nbsp;|&nbsp; PnL: <span style="color: {pnl_color};">{pnl_str}</span>
          </div>
      </div>
      """,
      unsafe_allow_html=True,
  )

  current_images = st.session_state["screenshots_dict"].get(ticket, [])
  if current_images:
    img_bytes = current_images[-1]
    encoded_img = base64.b64encode(img_bytes).decode()

    st.markdown(
        f"""
        <div style="width: 100%; height: 55vh; background: #000000; display: flex; justify-content: center; align-items: center; overflow: hidden; border-radius: 0px;">
            <img src="data:image/png;base64,{encoded_img}" style="width: 100%; height: 100%; object-fit: fill;" />
        </div>
        """,
        unsafe_allow_html=True,
    )
  else:
    st.warning("No screenshot found for this trade.")


# --- FETCH DATA & PERSIST IN SESSION STATE ---
if fetch_btn:
  if not MT5_AVAILABLE:
    st.sidebar.error("⚠️ MetaTrader5 is not available on this system (Mac/Linux).")
  elif not ACCOUNT_ID or not SERVER_NAME:
    st.sidebar.error("Enter a valid Account ID and Server Name.")
  elif not password:
    st.sidebar.error("Enter password.")
  else:
    with st.spinner("Syncing data and releasing terminal..."):
      if mt5.initialize(login=ACCOUNT_ID, password=password, server=SERVER_NAME):
        to_date = datetime.datetime.now() + datetime.timedelta(days=1)
        from_date = datetime.datetime(2026, 9, 21)
        deals = mt5.history_deals_get(from_date, to_date)
        orders = mt5.history_orders_get(from_date, to_date)
        mt5.shutdown()

        if deals:
          df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())

          if not df.empty:
            if "position_id" in df.columns:
              entry_deals = df[df["entry"] == 0][["position_id", "type"]]
              entry_deals.columns = ["position_id", "opening_type"]

              df = df[df["profit"] != 0].copy()
              df = df.merge(entry_deals, on="position_id", how="left")
              df["final_type"] = df["opening_type"].fillna(df["type"])
            else:
              df = df[df["profit"] != 0]
              df["final_type"] = df["type"]

            if not df.empty:
              if "position_id" in df.columns:
                pos_summary = df.groupby("position_id").agg(
                    entry_timestamp=("time", "min"),
                    exit_timestamp=("time", "max"),
                ).reset_index()

                if orders:
                  df_orders = pd.DataFrame(
                      list(orders), columns=orders[0]._asdict().keys()
                  )
                  if (
                      "position_id" in df_orders.columns
                      and not df_orders.empty
                  ):
                    order_times = (
                        df_orders.groupby("position_id")["time_setup"]
                        .min()
                        .reset_index()
                    )
                    order_times.columns = ["position_id", "order_setup_time"]
                    pos_summary = pos_summary.merge(
                        order_times, on="position_id", how="left"
                    )
                    pos_summary["entry_timestamp"] = pos_summary[
                        "order_setup_time"
                    ].fillna(pos_summary["entry_timestamp"])

                df = df.merge(pos_summary, on="position_id", how="left")
                df["duration_sec"] = (
                    df["exit_timestamp"] - df["entry_timestamp"]
                )
                df["Entry_Datetime"] = (
                    pd.to_datetime(df["entry_timestamp"], unit="s")
                    + datetime.timedelta(hours=tz_offset)
                )
              else:
                df["Entry_Datetime"] = (
                    pd.to_datetime(df["time"], unit="s")
                    + datetime.timedelta(hours=tz_offset)
                )
                df["duration_sec"] = 0

              df["Datetime"] = (
                  pd.to_datetime(df["time"], unit="s")
                  + datetime.timedelta(hours=tz_offset)
              )
              df["Date"] = df["Datetime"].dt.strftime("%Y-%m-%d")
              df["Entry time"] = df["Entry_Datetime"].dt.strftime(
                  "%I:%M:%S %p"
              )
              df["Duration"] = df["duration_sec"].apply(format_duration)

              df["Trade"] = df["final_type"].apply(
                  lambda x: "🟢 BUY" if x == 0 else "🔴 SELL"
              )
              df["Session"] = df["Datetime"].dt.hour.apply(get_trading_session)
              df["Win/Loss"] = df["profit"].apply(
                  lambda x: "🟢 WIN" if x > 0 else "🔴 LOSS"
              )

              avg_loss_val = abs(df[df["profit"] < 0]["profit"].mean())
              if pd.isna(avg_loss_val) or avg_loss_val == 0:
                avg_loss_val = 10.0
              df["Risk:Reward"] = (
                  (df["profit"] / avg_loss_val).round(2).astype(str) + "R"
              )

              st.session_state["df_trades"] = df
      else:
        st.sidebar.error(f"Failed: {mt5.last_error()}")

df_trades = st.session_state["df_trades"]

# --- MAIN LAYOUT WITH DEDICATED RIGHT SIDE PANEL ---
main_content_col, right_panel_col = st.columns([3.2, 1], gap="medium")

with main_content_col:
  if not df_trades.empty:
    total_trades = len(df_trades)
    winning_trades = df_trades[df_trades["Win/Loss"].str.contains("WIN")]
    losing_trades = df_trades[df_trades["Win/Loss"].str.contains("LOSS")]

    net_pnl = df_trades["profit"].sum()
    win_rate = (
        (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
    )
    loss_rate = 100.0 - win_rate

    gross_win = winning_trades["profit"].sum()
    gross_loss = abs(losing_trades["profit"].sum())
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0
    max_drawdown = df_trades["profit"].cumsum().min()

    r_numeric = df_trades["Risk:Reward"].str.replace("R", "").astype(float)
    avg_r = r_numeric.mean()

    # --- TOP 5 METRIC CARDS ---
    m1, m2, m3, m4, m5 = st.columns(5)

    with m1:
      pnl_delta = f"{net_pnl/100:+.2f}R"
      st.metric("Net P&L", f"${net_pnl:,.2f}", delta=pnl_delta)
    with m2:
      st.metric(
          "Win Rate",
          f"{win_rate:.1f}%",
          delta=f"{len(winning_trades)}/{total_trades} wins",
      )
    with m3:
      st.metric("Avg. R", f"{avg_r:+.2f}R", delta="Risk-Reward")
    with m4:
      st.metric("Profit Factor", f"{profit_factor:.2f}", delta="Win/Loss Ratio")
    with m5:
      st.metric("Max Drawdown", f"${max_drawdown:,.2f}", delta="Peak-to-valley")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- THREE-PANEL CHARTS ROW ---
    c_eq, c_donut, c_bar = st.columns([1.5, 1.2, 1.2], gap="medium")

    with c_eq:
      with st.container(border=True):
        st.markdown(
            "<h3 style='text-align: center;'>Equity Curve</h3>",
            unsafe_allow_html=True,
        )
        df_trades["Cumulative"] = df_trades["profit"].cumsum()
        df_trades["Index"] = range(1, len(df_trades) + 1)

        is_profitable = net_pnl >= 0
        curve_color = "#10b981" if is_profitable else "#ef4444"
        fill_color = (
            "rgba(16, 185, 129, 0.08)"
            if is_profitable
            else "rgba(239, 68, 68, 0.08)"
        )

        fig_eq = px.area(
            df_trades, x="Index", y="Cumulative", template="plotly_dark", height=240
        )
        fig_eq.update_traces(
            line=dict(color=curve_color, width=2.5), fillcolor=fill_color
        )
        fig_eq.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(gridcolor="#1e293b", zeroline=False),
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    with c_donut:
      with st.container(border=True):
        st.markdown(
            "<h3 style='text-align: center;'>Trade Distribution</h3>",
            unsafe_allow_html=True,
        )

        donut_col, legend_col = st.columns([1.3, 1], gap="small")

        with donut_col:
          fig_donut = go.Figure(
              data=[
                  go.Pie(
                      labels=["Win", "Loss"],
                      values=[len(winning_trades), len(losing_trades)],
                      hole=0.72,
                      marker_colors=["#10b981", "#ef4444"],
                      textinfo="none",
                      hoverinfo="label+value+percent",
                      sort=False,
                  )
              ]
          )
          fig_donut.update_layout(
              paper_bgcolor="rgba(0,0,0,0)",
              plot_bgcolor="rgba(0,0,0,0)",
              height=210,
              margin=dict(l=5, r=5, t=5, b=5),
              showlegend=False,
              annotations=[
                  dict(
                      text=str(total_trades),
                      x=0.5,
                      y=0.55,
                      showarrow=False,
                      font=dict(size=38, color="white"),
                  ),
                  dict(
                      text="Total Trades",
                      x=0.5,
                      y=0.41,
                      showarrow=False,
                      font=dict(size=15, color="#94a3b8"),
                  ),
              ],
          )
          st.plotly_chart(
              fig_donut, use_container_width=True, config={"displayModeBar": False}
          )

        with legend_col:
          st.markdown(
              f"""
              <div style="display: flex; flex-direction: column; justify-content: center; height: 210px; gap: 16px;">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                      <div style="display: flex; align-items: center; gap: 8px;">
                          <span style="width: 15px; height: 15px; background-color: #10b981; border-radius: 50%; display: inline-block;"></span>
                          <span style="color: #f1f5f9; font-weight: 600; font-size: 1.2rem;">Win</span>
                      </div>
                      <div style="display: flex; gap: 8px; font-size: 1.2rem;">
                          <span style="color: #f1f5f9; font-weight: 700;">{len(winning_trades)}</span>
                          <span style="color: #94a3b8;">{win_rate:.1f}%</span>
                      </div>
                  </div>
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                      <div style="display: flex; align-items: center; gap: 8px;">
                          <span style="width: 15px; height: 15px; background-color: #ef4444; border-radius: 50%; display: inline-block;"></span>
                          <span style="color: #f1f5f9; font-weight: 600; font-size: 1.2rem;">Loss</span>
                      </div>
                      <div style="display: flex; gap: 8px; font-size: 1.2rem;">
                          <span style="color: #f1f5f9; font-weight: 700;">{len(losing_trades)}</span>
                          <span style="color: #94a3b8;">{loss_rate:.1f}%</span>
                      </div>
                  </div>
              </div>
              """,
              unsafe_allow_html=True,
          )

    with c_bar:
     with st.container(border=True):
             st.markdown(
                 "<h3 style='text-align: center;'>R-Multiple Distribution</h3>",
                 unsafe_allow_html=True,
             )
             bins = [-999, -2, -1, 0, 1, 2, 999]
             labels = ["≤ -2R", "-2R:-1R", "-1R:0R", "0R:1R", "1R:2R", "> 2R"]
             df_trades["R_Bucket"] = pd.cut(r_numeric, bins=bins, labels=labels)
             r_counts = (
                 df_trades["R_Bucket"]
                 .value_counts()
                 .reindex(labels, fill_value=0)
                 .reset_index()
             )
             r_counts.columns = ["Bucket", "Count"]
     
             bar_colors = ["#ef4444", "#ef4444", "#ef4444", "#10b981", "#10b981", "#10b981"]
     
             fig_bar = px.bar(
                 r_counts, x="Bucket", y="Count", template="plotly_dark", height=240
             )
             fig_bar.update_traces(
                 marker_color=bar_colors,
                 marker_line_width=0,
                 hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
             )
             fig_bar.update_layout(
                 paper_bgcolor="rgba(0,0,0,0)",
                 plot_bgcolor="rgba(0,0,0,0)",
                 margin=dict(l=10, r=10, t=10, b=10),
                 bargap=0.35,
                 xaxis=dict(
                     showgrid=False, title="", tickfont=dict(size=10, color="#94a3b8")
                 ),
                 yaxis=dict(
                     showgrid=True,
                     gridcolor="#1e293b",
                     title="",
                     tickfont=dict(size=10, color="#94a3b8"),
                 ),
             )
             st.plotly_chart(
                 fig_bar, use_container_width=True, config={"displayModeBar": False}
             )

    # --- TABLES & SELECTOR ---
    with st.container(border=True):
      tab1, tab2, tab3, tab4 = st.tabs(
          ["Recent Trades (CISD)", "Pair Performance", "Session Analysis", "🏆 Tier Analysis"]
      )

      with tab1:
        st.markdown("### Execution Log")

        h_cols = st.columns(
            [0.9, 0.8, 0.9, 1.0, 0.8, 0.9, 0.8, 0.6, 0.8, 0.9, 0.9, 1.1]
        )
        headers = [
            "Date",
            "Pair",
            "Trade",
            "Entry Time",
            "Duration",
            "Session",
            "Risk:Reward",
            "Lot Size",
            "Win/Loss",
            "Profit/Loss",
            "Screenshot",
            "Tier",
        ]
        for hc, h in zip(h_cols, headers):
          hc.markdown(
              f"<div style='font-size: 0.85rem; font-weight: 700; color:"
              f" #94a3b8;'>{h}</div>",
              unsafe_allow_html=True,
          )

        st.markdown(
            "<hr style='margin: 4px 0 8px 0; border-color: #1e293b;'>",
            unsafe_allow_html=True,
        )

        # --- SCROLLABLE CONTAINER FOR ~10-15 TRADES ---
        with st.container(height=550):
          for idx, row in df_trades.iterrows():
            ticket = int(row["ticket"])
            pnl_val = row["profit"]
            pnl_str = (
                f"+${pnl_val:.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):.2f}"
            )
            pnl_color = "#10b981" if pnl_val >= 0 else "#ef4444"
            trade_str = row["Trade"]
            trade_color = "#10b981" if "BUY" in trade_str else "#ef4444"
            wl_str = row["Win/Loss"]
            wl_color = "#10b981" if "WIN" in wl_str else "#ef4444"

            r_cols = st.columns(
                [0.9, 0.8, 0.9, 1.0, 0.8, 0.9, 0.8, 0.6, 0.8, 0.9, 0.9, 1.1],
                vertical_alignment="center",
            )

            r_cols[0].markdown(
                f"<span style='font-size: 0.95rem; color:"
                f" #f1f5f9;'>{row['Date']}</span>",
                unsafe_allow_html=True,
            )
            r_cols[1].markdown(
                f"<span style='font-size: 0.95rem; font-weight: 600; color:"
                f" #f8fafc;'>{row['symbol']}</span>",
                unsafe_allow_html=True,
            )
            r_cols[2].markdown(
                f"<span style='font-size: 0.95rem; font-weight: 600; color:"
                f" {trade_color};'>{trade_str}</span>",
                unsafe_allow_html=True,
            )
            r_cols[3].markdown(
                f"<span style='font-size: 0.95rem; color:"
                f" #94a3b8;'>{row['Entry time']}</span>",
                unsafe_allow_html=True,
            )
            r_cols[4].markdown(
                f"<span style='font-size: 0.95rem; color:"
                f" #94a3b8;'>{row['Duration']}</span>",
                unsafe_allow_html=True,
            )
            r_cols[5].markdown(
                f"<span style='font-size: 0.95rem; color:"
                f" #94a3b8;'>{row['Session']}</span>",
                unsafe_allow_html=True,
            )
            r_cols[6].markdown(
                f"<span style='font-size: 0.95rem; color:"
                f" #94a3b8;'>{row['Risk:Reward']}</span>",
                unsafe_allow_html=True,
            )
            r_cols[7].markdown(
                f"<span style='font-size: 0.95rem; color:"
                f" #94a3b8;'>{row['volume']}</span>",
                unsafe_allow_html=True,
            )
            r_cols[8].markdown(
                f"<span style='font-size: 0.95rem; font-weight: 600; color:"
                f" {wl_color};'>{wl_str}</span>",
                unsafe_allow_html=True,
            )
            r_cols[9].markdown(
                f"<span style='font-size: 0.95rem; font-weight: 600; color:"
                f" {pnl_color};'>{pnl_str}</span>",
                unsafe_allow_html=True,
            )

            # Tier persisted per ticket in trade_meta.json
            _tm_key   = str(ticket)
            _tm_entry = st.session_state["trade_meta_dict"].get(_tm_key, {})

            with r_cols[10]:
              has_screenshot = (
                  ticket in st.session_state["screenshots_dict"]
                  and len(st.session_state["screenshots_dict"][ticket]) > 0
              )
              sc1, sc2 = st.columns(2)
              with sc1:
                with st.popover("📷"):
                  uploaded_file = st.file_uploader(
                      "Select Image",
                      type=["png", "jpg", "jpeg"],
                      key=f"file_pop_{ticket}",
                      label_visibility="collapsed",
                  )
                  _up_cats = st.session_state.get(
                      "ss_categories",
                      ["Setup", "Mistake", "Best Trade", "Psychology", "Uncategorized"],
                  )
                  _up_tier_ss = st.selectbox(
                      "Tier", TIER_OPTIONS[1:], key=f"up_tier_{ticket}"
                  )
                  _up_cat  = st.selectbox("Category", _up_cats, key=f"up_cat_{ticket}")
                  _up_note = st.text_input(
                      "Note", placeholder="e.g. FVG fill at OTE", key=f"up_note_{ticket}"
                  )
                  if uploaded_file:
                    img_bytes = uploaded_file.getvalue()
                    if ticket not in st.session_state["screenshots_dict"]:
                      st.session_state["screenshots_dict"][ticket] = []
                    if img_bytes not in st.session_state["screenshots_dict"][ticket]:
                      st.session_state["screenshots_dict"][ticket].append(img_bytes)
                      add_screenshot_record(
                          ticket=ticket,
                          symbol=row["symbol"],
                          trade_type=(
                              row["Trade"]
                              .replace("🟢 ", "")
                              .replace("🔴 ", "")
                          ),
                          profit=pnl_val,
                          date=row["Date"],
                          img_bytes=img_bytes,
                          category=_up_cat,
                          tier=_up_tier_ss,
                          notes=_up_note,
                      )
                      st.success("💾 Saved!")
                      st.rerun()
              with sc2:
                if has_screenshot:
                  if st.button("🖼️", key=f"view_{ticket}"):
                    show_image_popup(
                        ticket, row["symbol"], row["Trade"], pnl_val
                    )
                else:
                  st.markdown(
                      "<span style='color: #475569;'>—</span>",
                      unsafe_allow_html=True,
                  )

            with r_cols[11]:
              _cur_tier = _tm_entry.get("tier", "—")
              _tier_idx = TIER_OPTIONS.index(_cur_tier) if _cur_tier in TIER_OPTIONS else 0
              _new_tier = st.selectbox(
                  "Tier", TIER_OPTIONS, index=_tier_idx,
                  key=f"tier_{ticket}", label_visibility="collapsed",
              )
              if _new_tier != _cur_tier:
                st.session_state["trade_meta_dict"].setdefault(_tm_key, {})["tier"] = _new_tier
                save_trade_meta(st.session_state["trade_meta_dict"])

      with tab2:
        st.markdown("### Performance by Pair")
        pair_perf = (
            df_trades.groupby("symbol")["profit"]
            .agg(["sum", "count"])
            .reset_index()
        )
        pair_perf.columns = ["Pair", "Total PnL ($)", "Trades"]
        pair_perf["Total PnL ($)"] = pair_perf["Total PnL ($)"].apply(
            lambda x: f"+${x:.2f}" if x >= 0 else f"-${abs(x):.2f}"
        )

        styled_pair_perf = pair_perf.style.map(
            color_pnl_cells, subset=["Total PnL ($)"]
        )

        st.dataframe(
            styled_pair_perf,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Pair": st.column_config.TextColumn("Pair", alignment="center"),
                "Total PnL ($)": st.column_config.TextColumn(
                    "Total PnL ($)", alignment="center"
                ),
                "Trades": st.column_config.NumberColumn(
                    "Trades", alignment="center"
                ),
            },
        )

      with tab3:
        st.markdown("### Performance by Session")
        session_perf = (
            df_trades.groupby("Session")["profit"]
            .agg(["sum", "count"])
            .reset_index()
        )
        session_perf.columns = ["Session", "Total PnL ($)", "Trades"]
        session_perf["Total PnL ($)"] = session_perf["Total PnL ($)"].apply(
            lambda x: f"+${x:.2f}" if x >= 0 else f"-${abs(x):.2f}"
        )

        styled_session_perf = session_perf.style.map(
            color_pnl_cells, subset=["Total PnL ($)"]
        )

        st.dataframe(
            styled_session_perf,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Session": st.column_config.TextColumn(
                    "Session", alignment="center"
                ),
                "Total PnL ($)": st.column_config.TextColumn(
                    "Total PnL ($)", alignment="center"
                ),
                "Trades": st.column_config.NumberColumn(
                    "Trades", alignment="center"
                ),
            },
        )

      with tab4:
        st.markdown("### 🏆 Tier Analysis")
        _tier_order = [t for t in TIER_OPTIONS if t != "—"]

        # Build per-trade tier rows by joining trade_meta_dict with df_trades
        _tier_rows = []
        for _, _trow in df_trades.iterrows():
          _tkt = _trow.get("ticket", None)
          if _tkt is None:
            continue
          _tm  = st.session_state["trade_meta_dict"].get(str(int(_tkt)), {})
          _tg  = _tm.get("tier", "—")
          if _tg == "—":
            continue
          _tier_rows.append({
            "tier":   _tg,
            "profit": float(_trow["profit"]),
            "win":    1 if float(_trow["profit"]) > 0 else 0,
          })

        if not _tier_rows:
          st.info(
            "📊 No tier grades assigned yet.  "
            "Use the **Tier** dropdown in the Execution Log to grade your trades, "
            "then come back here for a full breakdown."
          )
        else:
          _tdf = pd.DataFrame(_tier_rows)
          _tsum = (
            _tdf.groupby("tier")
            .agg(count=("profit", "count"),
                 avg_pnl=("profit", "mean"),
                 total_pnl=("profit", "sum"),
                 wins=("win", "sum"))
            .reset_index()
          )
          _tsum["win_rate"]    = (_tsum["wins"] / _tsum["count"] * 100).round(1)
          _tsum["_sort_key"]   = _tsum["tier"].apply(
              lambda t: _tier_order.index(t) if t in _tier_order else 99
          )
          _tsum = _tsum.sort_values("_sort_key").reset_index(drop=True)
          _bar_colors = [TIER_COLORS.get(t, "#475569") for t in _tsum["tier"]]

          # ── Row 1: Trade Count  |  Win Rate ─────────────────────────────
          _ca, _cb = st.columns(2, gap="large")

          with _ca:
            with st.container(border=True):
              st.markdown(
                "<p style='color:#94a3b8;font-size:0.82rem;font-weight:700;"
                "text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>"
                "Trades Per Tier</p>",
                unsafe_allow_html=True,
              )
              _fig_cnt = go.Figure(go.Bar(
                x=_tsum["tier"],
                y=_tsum["count"],
                marker_color=_bar_colors,
                marker_line_width=0,
                text=_tsum["count"],
                textposition="outside",
                textfont=dict(color="#f1f5f9", size=13, family="Inter"),
              ))
              _fig_cnt.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=280,
                margin=dict(l=0, r=0, t=20, b=0),
                bargap=0.35,
                yaxis=dict(showgrid=True, gridcolor="#1e293b",
                           tickfont=dict(color="#64748b", size=10), title=""),
                xaxis=dict(showgrid=False, tickfont=dict(color="#f1f5f9", size=12,
                           family="Inter"), title=""),
              )
              st.plotly_chart(_fig_cnt, use_container_width=True,
                              config={"displayModeBar": False})

          with _cb:
            with st.container(border=True):
              st.markdown(
                "<p style='color:#94a3b8;font-size:0.82rem;font-weight:700;"
                "text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>"
                "Win Rate % Per Tier</p>",
                unsafe_allow_html=True,
              )
              _fig_wr = go.Figure(go.Bar(
                x=_tsum["tier"],
                y=_tsum["win_rate"],
                marker_color=_bar_colors,
                marker_line_width=0,
                text=[f"{v:.0f}%" for v in _tsum["win_rate"]],
                textposition="outside",
                textfont=dict(color="#f1f5f9", size=13, family="Inter"),
              ))
              _fig_wr.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=280,
                margin=dict(l=0, r=0, t=20, b=0),
                bargap=0.35,
                yaxis=dict(showgrid=True, gridcolor="#1e293b", range=[0, 115],
                           ticksuffix="%", tickfont=dict(color="#64748b", size=10),
                           title=""),
                xaxis=dict(showgrid=False, tickfont=dict(color="#f1f5f9", size=12,
                           family="Inter"), title=""),
              )
              st.plotly_chart(_fig_wr, use_container_width=True,
                              config={"displayModeBar": False})

          # ── Row 2: Avg P&L per tier (horizontal) ──────────────────────
          with st.container(border=True):
            st.markdown(
              "<p style='color:#94a3b8;font-size:0.82rem;font-weight:700;"
              "text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>"
              "Average P&amp;L per Tier ($)</p>",
              unsafe_allow_html=True,
            )
            _pnl_colors = [
              "#10b981" if v >= 0 else "#ef4444" for v in _tsum["avg_pnl"]
            ]
            _fig_pnl = go.Figure(go.Bar(
              y=_tsum["tier"],
              x=_tsum["avg_pnl"].round(2),
              orientation="h",
              marker_color=_pnl_colors,
              marker_line_width=0,
              text=[f"${v:+.2f}" for v in _tsum["avg_pnl"]],
              textposition="outside",
              textfont=dict(color="#f1f5f9", size=12, family="Inter"),
            ))
            _fig_pnl.update_layout(
              paper_bgcolor="rgba(0,0,0,0)",
              plot_bgcolor="rgba(0,0,0,0)",
              height=max(180, len(_tsum) * 48),
              margin=dict(l=0, r=60, t=10, b=0),
              bargap=0.4,
              xaxis=dict(showgrid=True, gridcolor="#1e293b", zeroline=True,
                         zerolinecolor="#334155", zerolinewidth=2,
                         tickprefix="$", tickfont=dict(color="#64748b", size=10),
                         title=""),
              yaxis=dict(showgrid=False, autorange="reversed",
                         tickfont=dict(color="#f1f5f9", size=13, family="Inter"),
                         title=""),
            )
            st.plotly_chart(_fig_pnl, use_container_width=True,
                            config={"displayModeBar": False})

          # ── Row 3: Summary stat cards per tier ─────────────────────
          st.markdown("<br>", unsafe_allow_html=True)
          st.markdown(
            "<p style='color:#94a3b8;font-size:0.82rem;font-weight:700;"
            "text-transform:uppercase;letter-spacing:1px;'>Grade Summary</p>",
            unsafe_allow_html=True,
          )
          _card_cols = st.columns(len(_tsum), gap="small")
          for _ci, (_cc, _crow) in enumerate(zip(_card_cols, _tsum.itertuples())):
            _tc   = TIER_COLORS.get(_crow.tier, "#475569")
            _sign = "+" if _crow.avg_pnl >= 0 else ""
            _pnl_c = "#10b981" if _crow.avg_pnl >= 0 else "#ef4444"
            with _cc:
              st.markdown(
                f"""
                <div style="background:rgba(15,23,42,0.7);border:1px solid {_tc}33;
                            border-top:3px solid {_tc};border-radius:10px;
                            padding:14px 10px;text-align:center;">
                  <div style="font-size:1.6rem;font-weight:900;color:{_tc};
                              letter-spacing:-1px;">{_crow.tier}</div>
                  <div style="font-size:1.3rem;font-weight:700;color:#f8fafc;
                              margin:4px 0;">{int(_crow.count)}</div>
                  <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;
                              letter-spacing:0.5px;">trades</div>
                  <hr style="border-color:{_tc}22;margin:8px 0;">
                  <div style="font-size:0.9rem;font-weight:700;color:{_pnl_c};"
                  >{_sign}${_crow.avg_pnl:.2f}</div>
                  <div style="font-size:0.65rem;color:#64748b;">avg P&amp;L</div>
                  <div style="font-size:0.9rem;font-weight:600;color:#f1f5f9;
                              margin-top:6px;">{_crow.win_rate:.0f}%</div>
                  <div style="font-size:0.65rem;color:#64748b;">win rate</div>
                </div>
                """,
                unsafe_allow_html=True,
              )

  else:
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Net P&L", "$0.00")
    m2.metric("Win Rate", "0.0%")
    m3.metric("Avg. R", "0.00R")
    m4.metric("Profit Factor", "0.00")
    m5.metric("Max Drawdown", "$0.00")

    st.markdown("<br>", unsafe_allow_html=True)
    st.info(
        "👈 Enter your investor password in the sidebar and click **'Sync Live"
        " MT5 Data'** to load your trades."
    )

# --- DEDICATED RIGHT SIDE PANEL (CALENDAR & NOTES) ---
with right_panel_col:
  with st.container(border=True):
    st.markdown("### 📅 Calendar & Notes")

    if not df_trades.empty and "Date" in df_trades.columns:
      daily_pnl = df_trades.groupby("Date")["profit"].sum().reset_index()
      daily_pnl["DateObj"] = pd.to_datetime(daily_pnl["Date"])

      min_date = daily_pnl["DateObj"].min()
      max_date = daily_pnl["DateObj"].max()

      # Generate month options in descending order
      month_options = (
          pd.date_range(
              min_date.replace(day=1), max_date.replace(day=1), freq="MS"
          )
          .strftime("%Y-%m")
          .tolist()[::-1]
      )

      # Automatically default to the current real-world month if available
      current_ym = datetime.date.today().strftime("%Y-%m")
      default_index = (
          month_options.index(current_ym) if current_ym in month_options else 0
      )

      selected_year_month = st.selectbox(
          "Select Month",
          options=month_options,
          index=default_index,
          label_visibility="collapsed",
      )

      yr, mo = map(int, selected_year_month.split("-"))

      st.markdown(
          f"<div style='text-align: center; font-weight: 600; color: #f8fafc;"
          f" margin-bottom: 8px;'>{calendar.month_name[mo]} {yr}</div>",
          unsafe_allow_html=True,
      )

      cal = calendar.Calendar(firstweekday=6)
      month_days = cal.monthdayscalendar(yr, mo)
      pnl_map = dict(zip(daily_pnl["Date"], daily_pnl["profit"]))

      for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
          with cols[i]:
            if day == 0:
              st.markdown(
                  "<div style='height: 42px;'></div>", unsafe_allow_html=True
              )
            else:
              date_str = f"{yr}-{mo:02d}-{day:02d}"
              pnl = pnl_map.get(date_str, None)

              bg_color = "#0d111a"
              text_color = "#94a3b8"
              border_style = "border: 1px solid #1e293b;"

              if pnl is not None:
                if pnl > 0:
                  bg_color = "rgba(16, 185, 129, 0.2)"
                  border_style = (
                      "border: 1px solid rgba(16, 185, 129, 0.5);"
                  )
                  text_color = "#34d399"
                elif pnl < 0:
                  bg_color = "rgba(239, 68, 68, 0.2)"
                  border_style = "border: 1px solid rgba(239, 68, 68, 0.5);"
                  text_color = "#f87171"

              pnl_display = f"${pnl:.0f}" if pnl is not None else ""
              st.markdown(
                  f"""
                  <div style="{border_style} background-color: {bg_color}; border-radius: 4px; height: 42px; padding: 2px; text-align: center;">
                      <div style="font-size: 0.6rem; color: #64748b; text-align: left;">{day}</div>
                      <div style="font-size: 0.65rem; font-weight: 600; color: {text_color};">{pnl_display}</div>
                  </div>
                  """,
                  unsafe_allow_html=True,
              )

      st.markdown(
          "<hr style='margin: 12px 0; border-color: #1e293b;'>",
          unsafe_allow_html=True,
      )
      st.markdown(
          "<p style='font-size: 0.8rem; font-weight: 600; color: #f8fafc;"
          " margin-bottom: 4px;'>Daily Session Notes</p>",
          unsafe_allow_html=True,
      )
      note_date = st.date_input(
          "Select Date for Note",
          value=datetime.date.today(),
          label_visibility="collapsed",
      )
      note_key = f"daily_note_{note_date.strftime('%Y-%m-%d')}"

      if note_key not in st.session_state:
        st.session_state[note_key] = ""

      daily_note_input = st.text_area(
          "Note input",
          value=st.session_state[note_key],
          placeholder="Jot down psychological state or market observations...",
          label_visibility="collapsed",
          height=100,
      )
      if daily_note_input != st.session_state[note_key]:
        st.session_state[note_key] = daily_note_input

    else:
      st.markdown(
          """
              <div style="height: 520px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;">
                  <p style="color: #94a3b8; font-size: 0.9rem; margin-bottom: 8px;"><b>Interactive Calendar Widget</b></p>
                  <p style="color: #64748b; font-size: 0.75rem;">Sync live MT5 data to populate your daily PnL calendar heatmap and session notes.</p>
              </div>
          """,
          unsafe_allow_html=True,
      )


# ═══════════════════════════════════════════════════════════════════
# 📸  SCREENSHOT GALLERY & MANAGER
# ═══════════════════════════════════════════════════════════════════
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("---")

with st.container(border=True):
  st.markdown(
    "<h2 style='margin-bottom:2px;'>📸 Screenshot Gallery & Manager</h2>",
    unsafe_allow_html=True,
  )
  st.markdown(
    "<p style='color:#64748b;font-size:0.85rem;margin-top:0;'>"
    "Screenshots are saved to disk and persist across sessions."
    " Use the execution log (📷 button) to attach directly to a trade, "
    "or upload manually below.</p>",
    unsafe_allow_html=True,
  )
  st.markdown("<br>", unsafe_allow_html=True)

  up_col, mgmt_col = st.columns([1, 1.1], gap="large")

  # ── Manual Upload Panel ───────────────────────────────────
  with up_col:
    with st.container(border=True):
      st.markdown("### ➕ Upload Screenshot")
      _man_sym  = st.text_input("Symbol", placeholder="e.g. EURUSD", key="man_sym")
      _man_type = st.selectbox("Trade Type", ["BUY", "SELL", "N/A"], key="man_type")
      _man_pnl  = st.number_input(
          "Profit / Loss ($)", value=0.0, step=0.01, format="%.2f", key="man_pnl"
      )
      _man_date = st.date_input(
          "Trade Date", value=datetime.date.today(), key="man_date"
      )
      _man_cats  = st.session_state.get(
          "ss_categories",
          ["Setup", "Mistake", "Best Trade", "Psychology", "Uncategorized"],
      )
      _man_cat  = st.selectbox("Category", _man_cats, key="man_cat")
      _man_tier = st.selectbox(
          "Trade Tier", TIER_OPTIONS[1:], key="man_tier"
      )
      _man_note = st.text_input(
          "Notes", placeholder="e.g. Clean FVG fill at 4H OTE", key="man_note"
      )
      _man_file = st.file_uploader(
          "Select Image", type=["png", "jpg", "jpeg"], key="man_ss_file"
      )

      if st.button("💾  Save Screenshot", use_container_width=True, key="man_save_btn"):
        if _man_file:
          _mb = _man_file.getvalue()
          add_screenshot_record(
            ticket=0,
            symbol=_man_sym or "Manual",
            trade_type=_man_type,
            profit=_man_pnl,
            date=_man_date.strftime("%Y-%m-%d"),
            img_bytes=_mb,
            category=_man_cat,
            tier=_man_tier,
            notes=_man_note,
          )
          st.session_state["screenshots_dict"].setdefault(0, []).append(_mb)
          st.success("✅ Saved to disk!")
          st.rerun()
        else:
          st.warning("Please select an image first.")

  # ── Category Manager ──────────────────────────────────────
  with mgmt_col:
    with st.container(border=True):
      st.markdown("### ⚙️ Category Manager")
      _cur_cats = list(st.session_state.get("ss_categories", []))
      nc1, nc2 = st.columns(2)
      with nc1:
        _new_nm = st.text_input("Add new category", key="new_cat_nm")
        if st.button("＋ Add", key="add_cat_btn", use_container_width=True):
          if _new_nm and _new_nm not in _cur_cats:
            _cur_cats.append(_new_nm)
            st.session_state["ss_categories"] = _cur_cats
            st.rerun()
      with nc2:
        _rm_sel = st.selectbox(
            "Remove category", ["— select —"] + _cur_cats, key="rm_cat"
        )
        if st.button("✕ Remove", key="rm_cat_btn", use_container_width=True):
          if _rm_sel != "— select —" and _rm_sel in _cur_cats:
            _cur_cats.remove(_rm_sel)
            st.session_state["ss_categories"] = _cur_cats
            st.rerun()

      st.markdown("<br><b>Active categories:</b>", unsafe_allow_html=True)
      _badge_html = " ".join(
        f"<span style='background:rgba(59,130,246,0.15);color:#60a5fa;"
        f"border-radius:4px;padding:2px 9px;font-size:0.78rem;"
        f"margin-right:4px;display:inline-block;margin-bottom:4px;'>{c}</span>"
        for c in _cur_cats
      )
      st.markdown(_badge_html, unsafe_allow_html=True)

  # ── Filter + Gallery ──────────────────────────────────────
  st.markdown("<br>", unsafe_allow_html=True)
  with st.container(border=True):
    st.markdown("### 🗂️ Browse & Manage")
    _all_recs = load_screenshot_meta()

    _uniq_syms = sorted(set(r["symbol"]   for r in _all_recs))
    _uniq_cats = sorted(set(r["category"] for r in _all_recs))

    _fa, _fb, _fc, _fd = st.columns(4)
    with _fa: _g_sym  = st.selectbox("Symbol",     ["All"] + _uniq_syms, key="g_sym")
    with _fb: _g_cat  = st.selectbox("Category",   ["All"] + _uniq_cats, key="g_cat")
    with _fc: _g_wl   = st.selectbox(
        "Result", ["All", "Win (profit > 0)", "Loss (profit < 0)"], key="g_wl"
    )
    with _fd: _g_type = st.selectbox(
        "Trade Type", ["All", "BUY", "SELL", "N/A"], key="g_type"
    )

    _filt = _all_recs
    if _g_sym  != "All": _filt = [r for r in _filt if r["symbol"] == _g_sym]
    if _g_cat  != "All": _filt = [r for r in _filt if r["category"] == _g_cat]
    if _g_wl   == "Win (profit > 0)":  _filt = [r for r in _filt if r["profit"] > 0]
    if _g_wl   == "Loss (profit < 0)": _filt = [r for r in _filt if r["profit"] < 0]
    if _g_type != "All": _filt = [r for r in _filt if r["trade_type"] == _g_type]
    _filt = sorted(_filt, key=lambda r: r["upload_time"], reverse=True)

    st.markdown(
      f"<p style='color:#64748b;font-size:0.82rem;'>"
      f"Showing <b style='color:#f1f5f9;'>{len(_filt)}</b> of "
      f"<b style='color:#f1f5f9;'>{len(_all_recs)}</b> screenshots</p>",
      unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    if not _filt:
      st.info("No screenshots match the current filters. Upload one using the panel above.")
    else:
      _N = 3
      for _row_i in range(0, len(_filt), _N):
        _chunk = _filt[_row_i : _row_i + _N]
        _gcols = st.columns(_N, gap="medium")

        for _gc, _rec in zip(_gcols, _chunk):
          with _gc:
            with st.container(border=True):
              _img_p = SCREENSHOT_DIR / _rec["filename"]
              if _img_p.exists():
                _enc = base64.b64encode(_img_p.read_bytes()).decode()
                _pv  = _rec["profit"]
                _pc  = "#10b981" if _pv >= 0 else "#ef4444"
                _ps  = f"+${_pv:.2f}" if _pv >= 0 else f"-${abs(_pv):.2f}"
                _tc  = (
                    "#10b981" if _rec["trade_type"] == "BUY"
                    else "#ef4444" if _rec["trade_type"] == "SELL"
                    else "#94a3b8"
                )

                # Thumbnail image
                st.markdown(
                  f"""<div style="border-radius:6px;overflow:hidden;
                                  height:160px;background:#000;">
                      <img src="data:image/png;base64,{_enc}"
                           style="width:100%;height:100%;object-fit:cover;"/>
                  </div>""",
                  unsafe_allow_html=True,
                )

                # Info strip
                st.markdown(
                  f"""<div style="margin-top:8px;line-height:1.75;">
                    <span style="font-weight:700;color:#f8fafc;
                                 font-size:0.95rem;">{_rec['symbol']}</span>
                    &nbsp;
                    <span style="color:{_tc};font-weight:600;
                                 font-size:0.8rem;">{_rec['trade_type']}</span>
                    &nbsp;|&nbsp;
                    <span style="color:{_pc};font-weight:700;">{_ps}</span>
                    <br>
                    <span style="color:#64748b;font-size:0.72rem;">
                      {_rec['date']} &nbsp;·&nbsp; uploaded {_rec['upload_time']}
                    </span>
                    <br>
                    <span style="background:rgba(59,130,246,0.15);color:#60a5fa;
                                 border-radius:4px;padding:1px 7px;
                                 font-size:0.72rem;">{_rec['category']}</span>
                  </div>""",
                  unsafe_allow_html=True,
                )

                if _rec.get("notes"):
                  st.caption(f"📝 {_rec['notes']}")

                # Edit / Delete actions
                _ea, _eb = st.columns(2)
                with _ea:
                  with st.popover("✏️ Edit", use_container_width=True):
                    _ec_list = st.session_state.get("ss_categories", ["Uncategorized"])
                    _di = (_ec_list.index(_rec["category"])
                           if _rec["category"] in _ec_list else 0)
                    _ncat  = st.selectbox(
                        "Category", _ec_list, index=_di, key=f"ec_{_rec['id']}"
                    )
                    _nnote = st.text_input(
                        "Notes", value=_rec.get("notes", ""), key=f"en_{_rec['id']}"
                    )
                    if st.button(
                        "Save Changes", key=f"es_{_rec['id']}",
                        use_container_width=True,
                    ):
                      _all2 = load_screenshot_meta()
                      for _r2 in _all2:
                        if _r2["id"] == _rec["id"]:
                          _r2["category"] = _ncat
                          _r2["notes"]    = _nnote
                      save_screenshot_meta(_all2)
                      st.rerun()
                with _eb:
                  if st.button(
                      "🗑️ Del", key=f"dl_{_rec['id']}",
                      use_container_width=True,
                  ):
                    delete_screenshot_record(_rec["id"])
                    st.rerun()
              else:
                st.warning(f"File missing:\n{_rec['filename']}")
"""
International Cost of Capital App
Compares a project's cost of equity, cost of debt and WACC in USD and in the
currency of a selected country.

Data sources (fetched live, with an embedded snapshot used only as fallback):
  * Unlevered industry betas  - Aswath Damodaran, betas.xls (US industries)
  * BBB (Baa2) default spread - Aswath Damodaran, ratings.html (large non-financial firms)
  * Statutory corporate tax   - OECD Corporate Tax Statistics (combined central + sub-central)
  * 10-year government yields - Trading Economics
"""

import io
import re
from datetime import datetime, timezone

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------
URL_BETAS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
URL_RATINGS = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html"
URL_OECD_PAGE = (
    "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/"
    "full-report/statutory-corporate-income-tax-rates_440f9286.html"
)
URL_OECD_SDMX = "https://sdmx.oecd.org/public/rest"
URL_TE_BONDS = "https://tradingeconomics.com/bonds"
URL_TE_TABLE = "https://tradingeconomics.com/country-list/government-bond-10y"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 25

DEFAULT_INDUSTRY = "Software (System & Application)"
DEFAULT_COUNTRY = "United States"
DEFAULT_ERP = 6.5
DEFAULT_DEBT = 30

# --------------------------------------------------------------------------------------
# Fallback snapshots (used only if a live fetch fails). Values are in % except betas.
# Betas / yields: captured from the live sources on 2026-11-16.
# Tax: OECD Corporate Tax Statistics 2024, combined statutory CIT rate, 2024.
# --------------------------------------------------------------------------------------
SNAPSHOT_DATE = "2026-11-16"
SPREAD_SNAPSHOT = (1.11, "January 2026")
BETA_SNAPSHOT_DATE = "2026-01-05"

BETA_SNAPSHOT = {"Advertising": 0.9301, "Aerospace/Defense": 0.8467, "Air Transport": 0.7041, "Apparel": 0.7580, "Auto & Truck": 1.2690, "Auto Parts": 1.0217, "Bank (Money Center)": 0.3411, "Banks (Regional)": 0.2865, "Beverage (Alcoholic)": 0.6132, "Beverage (Soft)": 0.5557, "Broadcasting": 0.2864, "Brokerage & Investment Banking": 0.5808, "Building Materials": 0.9302, "Business & Consumer Services": 0.7736, "Cable TV": 0.3524, "Chemical (Basic)": 0.5800, "Chemical (Diversified)": 0.3666, "Chemical (Specialty)": 0.7922, "Coal & Related Energy": 1.0165, "Computer Services": 0.9155, "Computers/Peripherals": 1.3051, "Construction Supplies": 1.0161, "Diversified": 0.7889, "Drugs (Biotechnology)": 1.0341, "Drugs (Pharmaceutical)": 0.8862, "Education": 0.6602, "Electrical Equipment": 1.1478, "Electronics (Consumer & Office)": 0.8299, "Electronics (General)": 0.8974, "Engineering/Construction": 1.0949, "Entertainment": 0.7372, "Environmental & Waste Services": 0.8145, "Farming/Agriculture": 0.8130, "Financial Svcs. (Non-bank & Insurance)": 0.3189, "Food Processing": 0.4574, "Food Wholesalers": 0.6409, "Furn/Home Furnishings": 0.6248, "Green & Renewable Energy": 0.4633, "Healthcare Products": 0.8291, "Healthcare Support Services": 0.6889, "Heathcare Information and Technology": 0.9913, "Homebuilding": 0.7850, "Hospitals/Healthcare Facilities": 0.5517, "Hotel/Gaming": 0.8323, "Household Products": 0.7178, "Information Services": 0.7372, "Insurance (General)": 0.5636, "Insurance (Life)": 0.4272, "Insurance (Prop/Cas.)": 0.4357, "Investments & Asset Management": 0.5297, "Machinery": 0.8680, "Metals & Mining": 0.9636, "Office Equipment & Services": 0.9806, "Oil/Gas (Integrated)": 0.2712, "Oil/Gas (Production and Exploration)": 0.5628, "Oil/Gas Distribution": 0.4651, "Oilfield Svcs/Equip.": 0.7430, "Packaging & Container": 0.7231, "Paper/Forest Products": 0.7216, "Power": 0.3100, "Precious Metals": 0.7932, "Publishing & Newspapers": 0.4773, "R.E.I.T.": 0.3929, "Real Estate (Development)": 0.4783, "Real Estate (General/Diversified)": 0.5779, "Real Estate (Operations & Services)": 0.8149, "Recreation": 0.6951, "Reinsurance": 0.4384, "Restaurant/Dining": 0.7674, "Retail (Automotive)": 0.6984, "Retail (Building Supply)": 1.3070, "Retail (Distributors)": 0.7827, "Retail (General)": 0.7600, "Retail (Grocery and Food)": 0.8048, "Retail (REITs)": 0.4362, "Retail (Special Lines)": 0.9488, "Rubber& Tires": 0.1435, "Semiconductor": 1.4893, "Semiconductor Equip": 1.3481, "Shipbuilding & Marine": 0.6440, "Shoe": 0.9337, "Software (Entertainment)": 1.0128, "Software (Internet)": 1.5461, "Software (System & Application)": 1.2254, "Steel": 0.9035, "Telecom (Wireless)": 0.3873, "Telecom. Equipment": 0.8635, "Telecom. Services": 0.3654, "Tobacco": 0.6776, "Transportation": 0.6753, "Transportation (Railroads)": 0.8069, "Trucking": 0.8504, "Utility (General)": 0.1486, "Utility (Water)": 0.2812, "Total Market": 0.7217, "Total Market (without financials)": 0.8775}

YIELD_SNAPSHOT = {"Australia": (5.14, "Nov/26"), "Austria": (3.61, "Nov/26"), "Belgium": (4.35, "Nov/26"), "Brazil": (15.34, "Nov/26"), "Bulgaria": (3.63, "Feb/25"), "Canada": (3.86, "Nov/26"), "Chile": (6.01, "Nov/26"), "China": (1.62, "Nov/26"), "Colombia": (12.7, "Nov/26"), "Croatia": (3.87, "Nov/26"), "Czech Republic": (5.22, "Nov/26"), "Denmark": (3.17, "Nov/26"), "Finland": (3.76, "Nov/26"), "France": (4.92, "Nov/26"), "Germany": (3.38, "Nov/26"), "Greece": (4.26, "Nov/26"), "Hong Kong": (3.99, "Nov/26"), "Hungary": (5.52, "Nov/26"), "Iceland": (6.81, "Nov/26"), "India": (7.31, "Nov/26"), "Indonesia": (7.61, "Nov/26"), "Ireland": (3.54, "Nov/26"), "Israel": (4.18, "Nov/26"), "Italy": (4.44, "Nov/26"), "Japan": (2.88, "Nov/26"), "Kenya": (12.5, "Nov/26"), "Lithuania": (4.33, "Nov/26"), "Malaysia": (3.86, "Nov/26"), "Mexico": (9.31, "Nov/26"), "Netherlands": (3.48, "Nov/26"), "New Zealand": (4.77, "Nov/26"), "Nigeria": (16.6, "Nov/26"), "Norway": (4.38, "Nov/26"), "Pakistan": (12.6, "Nov/26"), "Peru": (6.24, "Nov/26"), "Philippines": (7.77, "Nov/26"), "Poland": (6.34, "Nov/26"), "Portugal": (3.82, "Nov/26"), "Romania": (7.12, "Nov/26"), "Russia": (16.74, "Nov/26"), "Singapore": (2.33, "Nov/26"), "Slovakia": (4.31, "Nov/26"), "Slovenia": (3.91, "Nov/26"), "South Africa": (8.68, "Nov/26"), "South Korea": (4.01, "Nov/26"), "Spain": (3.94, "Nov/26"), "Sweden": (3.1, "Nov/26"), "Switzerland": (0.56, "Nov/26"), "Taiwan": (1.86, "Nov/26"), "Thailand": (2.0, "Nov/26"), "Turkey": (33.52, "Nov/26"), "United Kingdom": (5.34, "Nov/26"), "United States": (5.15, "Nov/26"), "Vietnam": (4.57, "Nov/26"), "Zambia": (14.74, "Nov/26")}

TAX_SNAPSHOT = {
    "Australia": 30.0, "Austria": 23.0, "Belgium": 25.0, "Brazil": 34.0, "Bulgaria": 10.0,
    "Canada": 26.1, "Chile": 27.0, "China": 25.0, "Colombia": 35.0, "Croatia": 18.0,
    "Czech Republic": 21.0, "Denmark": 22.0, "Finland": 20.0, "France": 25.8, "Germany": 29.9,
    "Greece": 22.0, "Hong Kong": 16.5, "Hungary": 9.0, "Iceland": 21.0, "India": 25.2,
    "Indonesia": 22.0, "Ireland": 12.5, "Israel": 23.0, "Italy": 27.8, "Japan": 29.7,
    "Kenya": 30.0, "Lithuania": 15.0, "Malaysia": 24.0, "Mexico": 30.0, "Netherlands": 25.8,
    "New Zealand": 28.0, "Nigeria": 30.0, "Norway": 22.0, "Pakistan": 29.0, "Peru": 29.5,
    "Philippines": 25.0, "Poland": 19.0, "Portugal": 31.5, "Romania": 16.0, "Russia": 20.0,
    "Singapore": 17.0, "Slovakia": 21.0, "Slovenia": 22.0, "South Africa": 27.0,
    "South Korea": 26.4, "Spain": 25.0, "Sweden": 20.6, "Switzerland": 19.6, "Taiwan": 20.0,
    "Thailand": 20.0, "Turkey": 25.0, "United Kingdom": 25.0, "United States": 25.8,
    "Vietnam": 20.0, "Zambia": 30.0,
}

# OECD / other naming -> Trading Economics naming
NAME_ALIASES = {
    "Korea": "South Korea", "Korea, Republic of": "South Korea", "Türkiye": "Turkey",
    "Turkiye": "Turkey", "Czechia": "Czech Republic", "China (People's Republic of)": "China",
    "Hong Kong, China": "Hong Kong", "Hong Kong (China)": "Hong Kong",
    "Chinese Taipei": "Taiwan", "Russian Federation": "Russia", "Viet Nam": "Vietnam",
    "Slovak Republic": "Slovakia", "United States of America": "United States",
}


def canon(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name)).strip()
    return NAME_ALIASES.get(name, name)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


# --------------------------------------------------------------------------------------
# Data fetchers (cached; the Refresh button clears the cache)
# --------------------------------------------------------------------------------------
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_betas():
    try:
        raw = pd.read_excel(io.BytesIO(get(URL_BETAS).content),
                            sheet_name="Industry Averages", header=None)
        col0 = raw[0].astype(str).str.strip()
        hdr = raw.index[col0 == "Industry Name"][0]
        header = [str(h).strip() for h in raw.iloc[hdr]]
        ucol = header.index("Unlevered beta")  # NOT the cash-corrected column
        df = raw.iloc[hdr + 1:, [0, ucol]].dropna()
        df.columns = ["Industry", "Unlevered beta"]
        df["Industry"] = df["Industry"].astype(str).str.strip()
        df["Unlevered beta"] = pd.to_numeric(df["Unlevered beta"], errors="coerce")
        df = df.dropna().reset_index(drop=True)
        date_row = raw.index[col0.str.startswith("Date updated")]
        date = pd.to_datetime(raw.iloc[date_row[0], 1]).strftime("%Y-%m-%d") if len(date_row) else "n/a"
        return df, {"status": "live", "date": date, "fetched": now_utc()}
    except Exception as e:  # noqa: BLE001
        df = pd.DataFrame(list(BETA_SNAPSHOT.items()), columns=["Industry", "Unlevered beta"])
        return df, {"status": f"snapshot (live fetch failed: {type(e).__name__})",
                    "date": BETA_SNAPSHOT_DATE, "fetched": SNAPSHOT_DATE}


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_spread():
    try:
        html = get(URL_RATINGS).text
        tables = pd.read_html(io.StringIO(html))
        t = tables[0].astype(str)
        # First block of columns = large non-financial service firms
        row = t[t.iloc[:, 2].str.replace(r"\s", "", regex=True) == "Baa2/BBB"]
        spread = float(row.iloc[0, 3].replace("%", "").strip())
        m = re.search(r"as of\s+([A-Za-z]+\s+\d{4})", html)
        return spread, {"status": "live", "date": m.group(1) if m else "n/a", "fetched": now_utc()}
    except Exception as e:  # noqa: BLE001
        return SPREAD_SNAPSHOT[0], {"status": f"snapshot (live fetch failed: {type(e).__name__})",
                                    "date": SPREAD_SNAPSHOT[1], "fetched": SNAPSHOT_DATE}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_yields():
    """10Y yields from Trading Economics. The /bonds page renders its table with
    JavaScript for some clients, so the same 10Y data is read from TE's static
    country-list table; /bonds is tried first."""
    for url in (URL_TE_BONDS, URL_TE_TABLE):
        try:
            tables = pd.read_html(io.StringIO(get(url).text))
            best = None
            for t in tables:
                if t.shape[0] < 20 or t.shape[1] < 3:
                    continue
                t = t.copy()
                t.columns = [str(c) for c in range(t.shape[1])]
                names = t["0"].astype(str).str.strip()
                if not names.str.contains("United States").any():
                    continue
                vals = pd.to_numeric(t["1"], errors="coerce")
                ref = t["3"].astype(str) if t.shape[1] > 3 else "n/a"
                out = pd.DataFrame({"Country": names.map(canon), "Yield": vals, "Reference": ref})
                out = out.dropna(subset=["Yield"])
                out = out[~out["Country"].isin(["Euro area", "Country List", "Report"])]
                if best is None or len(out) > len(best):
                    best = out
            if best is not None and len(best) > 20:
                best = best.drop_duplicates("Country").reset_index(drop=True)
                return best, {"status": "live", "source": url, "fetched": now_utc()}
        except Exception:  # noqa: BLE001
            continue
    df = pd.DataFrame([(k, v[0], v[1]) for k, v in YIELD_SNAPSHOT.items()],
                      columns=["Country", "Yield", "Reference"])
    return df, {"status": "snapshot (live fetch failed)", "source": URL_TE_TABLE,
                "fetched": SNAPSHOT_DATE}


def _oecd_sdmx():
    """Find the statutory CIT dataflow in OECD's SDMX catalogue and pull the
    latest combined rate per country."""
    flows = get(f"{URL_OECD_SDMX}/dataflow/all", params={"detail": "allstubs"}).text
    cand = re.findall(
        r'<structure:Dataflow[^>]*id="([^"]+)"[^>]*agencyID="([^"]+)"[^>]*version="([^"]+)"[^>]*>'
        r'.*?<common:Name xml:lang="en">([^<]*)</common:Name>', flows, flags=re.S)
    cand = [c for c in cand if re.search(r"statutory corporate", c[3], re.I)]
    if not cand:
        raise ValueError("CIT dataflow not found")
    fid, agency, ver, _ = cand[0]
    csv = get(f"{URL_OECD_SDMX}/data/{agency},{fid},{ver}/all",
              params={"format": "csvfilewithlabels", "lastNObservations": 1}).text
    d = pd.read_csv(io.StringIO(csv))
    area = "Reference area" if "Reference area" in d.columns else "REF_AREA"
    # Keep the combined (central + sub-central) rate when the flow splits them
    for c in d.columns:
        if d[c].dtype == object and d[c].astype(str).str.contains("ombined", na=False).any():
            d = d[d[c].astype(str).str.contains("ombined", na=False)]
            break
    d = d.sort_values("TIME_PERIOD").groupby(area).tail(1)
    out = {canon(r[area]): float(r["OBS_VALUE"]) for _, r in d.iterrows()}
    year = str(d["TIME_PERIOD"].max())
    if len(out) < 20:
        raise ValueError("too few rows")
    return out, year


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_tax():
    try:
        rates, year = _oecd_sdmx()
        merged = {**TAX_SNAPSHOT, **rates}  # live values win; snapshot fills non-OECD gaps
        return merged, {"status": "live (OECD SDMX API)", "date": year, "fetched": now_utc()}
    except Exception as e1:  # noqa: BLE001
        try:
            html = get(URL_OECD_PAGE).text
            if "Just a moment" in html[:2000]:
                raise ValueError("Cloudflare challenge")
            rates = {}
            for t in pd.read_html(io.StringIO(html)):
                t = t.astype(str)
                for _, r in t.iterrows():
                    nums = [float(x) for x in r.values[1:] if re.fullmatch(r"\d{1,2}(\.\d+)?", x)]
                    if nums:
                        rates[canon(r.values[0])] = nums[-1]
            if len(rates) < 20:
                raise ValueError("table not parsed")
            return {**TAX_SNAPSHOT, **rates}, {"status": "live (OECD page)", "date": "2024",
                                              "fetched": now_utc()}
        except Exception as e2:  # noqa: BLE001
            return dict(TAX_SNAPSHOT), {
                "status": f"snapshot (live fetch failed: {type(e1).__name__}/{type(e2).__name__})",
                "date": "2024 (OECD Corporate Tax Statistics 2024)", "fetched": "embedded"}


# --------------------------------------------------------------------------------------
# Core finance
# --------------------------------------------------------------------------------------
def cost_of_capital(beta_u, tax, wd, erp, y_us, y_fc, spread_usd,
                    spread_fc_override=None, method="Multiplicative"):
    """All rates as decimals. Returns a dict of results.

    USD:  beta_L = beta_U * [1 + (1 - t) * D/E]
          Ke_USD = y_US + beta_L * ERP
          Kd_USD = y_US + s_USD
          WACC   = E/V * Ke + D/V * Kd * (1 - t)
    FC (multiplicative / international Fisher):
          1 + K_FC = (1 + K_USD) * (1 + y_FC) / (1 + y_US)
    FC (additive approximation):
          K_FC = K_USD + (y_FC - y_US)
    FC spread:  auto = Kd_FC(converted) - y_FC ; or user override  -> Kd_FC = y_FC + s_FC
    """
    we = 1 - wd
    de = wd / we
    beta_l = beta_u * (1 + (1 - tax) * de)

    ke_usd = y_us + beta_l * erp
    kd_usd = y_us + spread_usd
    wacc_usd = we * ke_usd + wd * kd_usd * (1 - tax)

    if method == "Multiplicative":
        conv = lambda k: (1 + k) * (1 + y_fc) / (1 + y_us) - 1  # noqa: E731
    else:
        conv = lambda k: k + (y_fc - y_us)  # noqa: E731

    ke_fc = conv(ke_usd)
    spread_fc_auto = conv(kd_usd) - y_fc
    spread_fc = spread_fc_auto if spread_fc_override is None else spread_fc_override
    kd_fc = y_fc + spread_fc
    wacc_fc = we * ke_fc + wd * kd_fc * (1 - tax)

    return dict(beta_l=beta_l, de=de, we=we, wd=wd, tax=tax, erp=erp,
                y_us=y_us, y_fc=y_fc, spread_usd=spread_usd,
                spread_fc=spread_fc, spread_fc_auto=spread_fc_auto,
                ke_usd=ke_usd, kd_usd=kd_usd, kd_usd_at=kd_usd * (1 - tax), wacc_usd=wacc_usd,
                ke_fc=ke_fc, kd_fc=kd_fc, kd_fc_at=kd_fc * (1 - tax), wacc_fc=wacc_fc)


def pct(x, d=2):
    return f"{x * 100:.{d}f}%"


# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="International Cost of Capital", page_icon="🌍", layout="wide")
st.title("🌍 International Cost of Capital")
st.caption("Cost of equity, cost of debt and WACC for a project in USD and in a selected "
           "country's currency.")

top = st.columns([1, 5])
if top[0].button("🔄 Refresh data", help="Clear the cache and re-fetch all sources"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Fetching latest data…"):
    betas_df, beta_meta = fetch_betas()
    spread_live, spread_meta = fetch_spread()
    yields_df, yield_meta = fetch_yields()
    tax_map, tax_meta = fetch_tax()

countries = sorted(yields_df["Country"].tolist())
yield_map = dict(zip(yields_df["Country"], yields_df["Yield"]))
ref_map = dict(zip(yields_df["Country"], yields_df["Reference"]))
industries = betas_df["Industry"].tolist()
beta_map = dict(zip(betas_df["Industry"], betas_df["Unlevered beta"]))

# ---------------- Sidebar ----------------
sb = st.sidebar
sb.header("Project settings")
industry = sb.selectbox("Industry", industries,
                        index=industries.index(DEFAULT_INDUSTRY) if DEFAULT_INDUSTRY in industries else 0)
country = sb.selectbox("Target country", countries,
                       index=countries.index(DEFAULT_COUNTRY) if DEFAULT_COUNTRY in countries else 0)
erp_pct = sb.slider("Equity risk premium (%)", 0.0, 15.0, DEFAULT_ERP, 0.1)
debt_pct = sb.slider("Target debt share D/(D+E) (%)", 0, 90, DEFAULT_DEBT, 1)
tax_choice = sb.radio("Project tax rate", ["U.S. rate", "Selected-country rate"], index=0,
                      horizontal=True)
method = sb.radio("Currency conversion", ["Multiplicative", "Additive"], index=0,
                  help="Multiplicative: (1+K_FC) = (1+K_USD)(1+y_FC)/(1+y_US). "
                       "Additive: K_FC = K_USD + (y_FC − y_US).")

sb.header("Manual overrides")
sb.caption("Switch on to replace a fetched value.")


def override(label, key, default, fmt="%.2f", step=0.01, minv=None, maxv=None):
    on = sb.toggle(f"Override {label}", key=f"on_{key}")
    if on:
        return sb.number_input(label, value=float(default), step=step, format=fmt,
                               min_value=minv, max_value=maxv, key=f"v_{key}"), True
    return float(default), False


us_tax_fetched = tax_map.get("United States", np.nan)
fc_tax_fetched = tax_map.get(country, np.nan)
if np.isnan(fc_tax_fetched):
    sb.warning(f"No OECD tax rate found for {country}; switch on its override.")
    fc_tax_fetched = us_tax_fetched

beta_u, ov_beta = override("unlevered beta", "beta", beta_map[industry], "%.4f", 0.01, 0.0)
us_tax_pct, ov_ustax = override("U.S. tax rate (%)", "ustax", us_tax_fetched, "%.2f", 0.1, 0.0, 100.0)
if country == "United States":
    fc_tax_pct, ov_fctax = us_tax_pct, ov_ustax
else:
    fc_tax_pct, ov_fctax = override(f"{country} tax rate (%)", "fctax", fc_tax_fetched, "%.2f", 0.1, 0.0, 100.0)
spread_pct, ov_spread = override("USD BBB spread (%)", "spread", spread_live, "%.2f", 0.01)
y_us_pct, ov_yus = override("U.S. 10Y yield (%)", "yus", yield_map["United States"], "%.2f", 0.01)
if country == "United States":
    y_fc_pct, ov_yfc = y_us_pct, ov_yus
else:
    y_fc_pct, ov_yfc = override(f"{country} 10Y yield (%)", "yfc", yield_map[country], "%.2f", 0.01)

ov_fcs = sb.toggle(f"Override {country} BBB spread (local currency)", key="on_fcs")
fc_spread_override = None
if ov_fcs:
    fc_spread_override = sb.number_input(f"{country} BBB spread (%)", value=float(spread_pct),
                                         step=0.01, format="%.2f", key="v_fcs") / 100

tax_pct = us_tax_pct if tax_choice == "U.S. rate" else fc_tax_pct

R = cost_of_capital(beta_u, tax_pct / 100, debt_pct / 100, erp_pct / 100,
                    y_us_pct / 100, y_fc_pct / 100, spread_pct / 100,
                    fc_spread_override, method)

if not ov_fcs:
    sb.info(f"Auto {country} BBB spread: **{pct(R['spread_fc_auto'])}**")

# ---------------- Tabs ----------------
tab_res, tab_ind, tab_assume, tab_check, tab_data = st.tabs(
    ["📊 Results", "🏭 All industries", "📘 Assumptions", "✅ Checks", "🗂 Data & sources"])

with tab_res:
    st.subheader(f"{industry} · USD vs {country}")
    st.caption(f"Project tax rate: **{pct(R['tax'])}** ({tax_choice}) · ERP **{erp_pct:.1f}%** · "
               f"D/V **{debt_pct}%** · conversion **{method}**")

    c1, c2 = st.columns(2)
    for col, ccy, ke, kd, wacc, y, s in [
        (c1, "USD (United States)", R["ke_usd"], R["kd_usd"], R["wacc_usd"], R["y_us"], R["spread_usd"]),
        (c2, f"Local currency ({country})", R["ke_fc"], R["kd_fc"], R["wacc_fc"], R["y_fc"], R["spread_fc"]),
    ]:
        with col.container(border=True):
            st.markdown(f"#### {ccy}")
            m = st.columns(3)
            m[0].metric("Cost of equity", pct(ke))
            m[1].metric("Pre-tax cost of debt", pct(kd))
            m[2].metric("WACC", pct(wacc))
            st.caption(f"10Y yield {pct(y)} · BBB spread {pct(s)} · "
                       f"after-tax Kd {pct(kd * (1 - R['tax']))}")

    rows = [
        ("10Y government yield", R["y_us"], R["y_fc"]),
        ("Unlevered beta", beta_u, beta_u),
        ("Levered beta", R["beta_l"], R["beta_l"]),
        ("Equity risk premium", R["erp"], R["erp"]),
        ("Cost of equity", R["ke_usd"], R["ke_fc"]),
        ("BBB spread", R["spread_usd"], R["spread_fc"]),
        ("Pre-tax cost of debt", R["kd_usd"], R["kd_fc"]),
        ("Project tax rate", R["tax"], R["tax"]),
        ("After-tax cost of debt", R["kd_usd_at"], R["kd_fc_at"]),
        ("Equity weight E/V", R["we"], R["we"]),
        ("Debt weight D/V", R["wd"], R["wd"]),
        ("WACC", R["wacc_usd"], R["wacc_fc"]),
    ]
    res_df = pd.DataFrame(rows, columns=["Item", "USD", country])
    show = res_df.copy()
    for c in ["USD", country]:
        show[c] = [f"{v:.4f}" if "beta" in it.lower() else pct(v) for it, v in zip(show["Item"], show[c])]
    st.dataframe(show, hide_index=True, use_container_width=True)

    chart_df = pd.DataFrame({
        "Measure": ["Cost of equity", "Cost of debt (pre-tax)", "WACC"] * 2,
        "Currency": ["USD"] * 3 + [country] * 3,
        "Rate (%)": [R["ke_usd"] * 100, R["kd_usd"] * 100, R["wacc_usd"] * 100,
                     R["ke_fc"] * 100, R["kd_fc"] * 100, R["wacc_fc"] * 100],
    })
    st.altair_chart(
        alt.Chart(chart_df).mark_bar().encode(
            x=alt.X("Measure:N", title=None), xOffset="Currency:N",
            y=alt.Y("Rate (%):Q"), color=alt.Color("Currency:N"),
            tooltip=["Measure", "Currency", alt.Tooltip("Rate (%):Q", format=".2f")],
        ).properties(height=320), use_container_width=True)

    settings = pd.DataFrame([
        ("Industry", industry), ("Target country", country), ("Tax choice", tax_choice),
        ("Conversion", method), ("Unlevered beta overridden", ov_beta),
        ("US tax overridden", ov_ustax), ("FC tax overridden", ov_fctax),
        ("USD spread overridden", ov_spread), ("US yield overridden", ov_yus),
        ("FC yield overridden", ov_yfc), ("FC spread overridden", ov_fcs),
        ("Generated", now_utc()),
    ], columns=["Setting", "Value"])
    csv_out = (res_df.to_csv(index=False) + "\n" + settings.to_csv(index=False))
    st.download_button("⬇️ Download results (CSV)", csv_out,
                       file_name=f"cost_of_capital_{country.replace(' ', '_')}.csv", mime="text/csv")

with tab_ind:
    st.subheader(f"All industries · USD vs {country}")
    st.caption("Same tax rate, debt share, ERP, yields and spreads; only the unlevered beta changes.")
    out = []
    for ind, bu in beta_map.items():
        b = beta_u if (ind == industry and ov_beta) else bu
        r = cost_of_capital(b, R["tax"], R["wd"], R["erp"], R["y_us"], R["y_fc"],
                            R["spread_usd"], fc_spread_override, method)
        out.append({"Industry": ind, "Unlevered beta": b, "Levered beta": r["beta_l"],
                    "Ke USD (%)": r["ke_usd"] * 100, f"Ke {country} (%)": r["ke_fc"] * 100,
                    "WACC USD (%)": r["wacc_usd"] * 100, f"WACC {country} (%)": r["wacc_fc"] * 100})
    ind_df = pd.DataFrame(out).sort_values("WACC USD (%)", ascending=False).reset_index(drop=True)
    st.dataframe(ind_df.style.format({c: "{:.2f}" for c in ind_df.columns if "(%)" in c} |
                                     {"Unlevered beta": "{:.4f}", "Levered beta": "{:.4f}"}),
                 hide_index=True, use_container_width=True, height=420)
    long = ind_df.melt(id_vars="Industry", value_vars=["WACC USD (%)", f"WACC {country} (%)"],
                       var_name="Currency", value_name="WACC (%)")
    st.altair_chart(
        alt.Chart(long).mark_bar().encode(
            y=alt.Y("Industry:N", sort=ind_df["Industry"].tolist(), title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("WACC (%):Q"), yOffset="Currency:N", color="Currency:N",
            tooltip=["Industry", "Currency", alt.Tooltip("WACC (%):Q", format=".2f")],
        ).properties(height=max(600, 14 * len(ind_df) * 2)), use_container_width=True)
    st.download_button("⬇️ Download all-industry table (CSV)", ind_df.to_csv(index=False),
                       file_name=f"all_industries_{country.replace(' ', '_')}.csv", mime="text/csv")

with tab_assume:
    st.subheader("Formulas and main assumptions")
    st.markdown(r"""
**1. Levered beta (Hamada)** — the project is levered to the target debt share:
$$\beta_L = \beta_U\left[1 + (1-t)\tfrac{D}{E}\right],\qquad \tfrac{D}{E} = \tfrac{w_D}{1-w_D}$$

**2. USD cost of equity (CAPM)** with the U.S. 10Y Treasury as risk-free rate:
$$K_{e,USD} = y_{US} + \beta_L \times ERP$$

**3. USD cost of debt** = Treasury yield + BBB (Baa2) default spread:
$$K_{d,USD} = y_{US} + s_{USD}$$

**4. Translate to local currency** using the 10Y yield gap as the expected inflation /
currency-depreciation differential:
- Multiplicative (default): $1+K_{FC} = (1+K_{USD})\dfrac{1+y_{FC}}{1+y_{US}}$
- Additive: $K_{FC} = K_{USD} + (y_{FC}-y_{US})$

Applied to $K_e$ and to $K_d$. The auto local-currency spread is $s_{FC} = K_{d,FC} - y_{FC}$.
If you override $s_{FC}$, then $K_{d,FC} = y_{FC} + s_{FC}$; USD results don't change.

**5. WACC** (same tax rate, weights and ERP in both currencies):
$$WACC = (1-w_D)K_e + w_D K_d (1-t)$$

**Main assumptions**
- The unlevered beta is Damodaran's U.S. industry average (not cash-corrected) and is used for every country. It assumes the project's business risk doesn't depend on where it's located.
- The ERP is a single global (mature-market) premium. **No separate country risk premium** is added. Any country risk shows up only through the higher local government yield, which may contain default risk as well as inflation.
- The yield gap between the two 10Y government bonds stands in for expected inflation differences (international Fisher / relative PPP). So the local-currency result is the USD result restated in local currency, not a riskier project.
- The firm borrows at a BBB rating in both currencies. The tax rate is the statutory combined CIT rate from OECD.
- Debt share, ERP and tax rate are the same in both currencies, so any USD-vs-local difference comes only from the yields (and the local spread, if you override it).
""")

with tab_check:
    st.subheader("Built-in verification checks")
    st.caption("These run on your current settings.")
    tol = 1e-12
    base = dict(beta_u=beta_u, tax=R["tax"], wd=R["wd"], erp=R["erp"], y_us=R["y_us"],
                y_fc=R["y_fc"], spread_usd=R["spread_usd"], method=method)
    a = cost_of_capital(**{**base, "y_fc": base["y_us"]}, spread_fc_override=None)
    c1 = abs(a["ke_usd"] - a["ke_fc"]) < tol and abs(a["wacc_usd"] - a["wacc_fc"]) < tol \
        and abs(a["kd_usd"] - a["kd_fc"]) < tol
    b = cost_of_capital(**{**base, "wd": 0.0}, spread_fc_override=fc_spread_override)
    c2 = abs(b["wacc_usd"] - b["ke_usd"]) < tol and abs(b["wacc_fc"] - b["ke_fc"]) < tol
    x0 = cost_of_capital(**base, spread_fc_override=None)
    x1 = cost_of_capital(**base, spread_fc_override=0.05)
    c3 = all(abs(x0[k] - x1[k]) < tol for k in ["ke_usd", "kd_usd", "wacc_usd"])
    checks = pd.DataFrame([
        ("Equal yields (FC spread override off) → identical USD and local results", c1,
         f"Ke {pct(a['ke_usd'], 4)} vs {pct(a['ke_fc'], 4)}; WACC {pct(a['wacc_usd'], 4)} vs {pct(a['wacc_fc'], 4)}"),
        ("Zero debt → WACC = cost of equity (both currencies)", c2,
         f"USD {pct(b['wacc_usd'], 4)} = {pct(b['ke_usd'], 4)}; FC {pct(b['wacc_fc'], 4)} = {pct(b['ke_fc'], 4)}"),
        ("Overriding local spread (auto → 5.00%) leaves USD results unchanged", c3,
         f"USD WACC {pct(x0['wacc_usd'], 4)} vs {pct(x1['wacc_usd'], 4)}; FC WACC {pct(x0['wacc_fc'], 4)} → {pct(x1['wacc_fc'], 4)}"),
    ], columns=["Check", "Pass", "Detail"])
    checks["Pass"] = checks["Pass"].map({True: "✅ pass", False: "❌ fail"})
    st.dataframe(checks, hide_index=True, use_container_width=True)

    st.markdown("**Step-by-step for the current inputs**")
    st.code(
        f"D/E      = {R['wd']:.4f} / {R['we']:.4f} = {R['de']:.6f}\n"
        f"beta_L   = {beta_u:.4f} x [1 + (1 - {R['tax']:.4f}) x {R['de']:.6f}] = {R['beta_l']:.6f}\n"
        f"Ke_USD   = {R['y_us']:.4f} + {R['beta_l']:.6f} x {R['erp']:.4f} = {R['ke_usd']:.6f}\n"
        f"Kd_USD   = {R['y_us']:.4f} + {R['spread_usd']:.4f} = {R['kd_usd']:.6f}\n"
        f"WACC_USD = {R['we']:.2f} x {R['ke_usd']:.6f} + {R['wd']:.2f} x {R['kd_usd']:.6f} x (1 - {R['tax']:.4f}) = {R['wacc_usd']:.6f}\n"
        f"Ke_FC    = {R['ke_fc']:.6f}   Kd_FC = {R['kd_fc']:.6f}   WACC_FC = {R['wacc_fc']:.6f}",
        language="text")

with tab_data:
    st.subheader("Data, sources and dates")
    src = pd.DataFrame([
        ("Unlevered beta (U.S. industries)", f"{beta_map[industry]:.4f} ({industry})",
         "Aswath Damodaran — betas.xls", URL_BETAS, beta_meta["date"], beta_meta["status"], beta_meta["fetched"]),
        ("BBB (Baa2) USD spread, large non-financial firms", f"{spread_live:.2f}%",
         "Aswath Damodaran — ratings.html", URL_RATINGS, spread_meta["date"], spread_meta["status"], spread_meta["fetched"]),
        ("Statutory corporate tax rate", f"US {us_tax_fetched:.2f}% · {country} {tax_map.get(country, float('nan')):.2f}%",
         "OECD Corporate Tax Statistics", URL_OECD_PAGE, tax_meta["date"], tax_meta["status"], tax_meta["fetched"]),
        ("10Y government bond yields", f"US {yield_map['United States']:.2f}% ({ref_map['United States']}) · "
         f"{country} {yield_map[country]:.2f}% ({ref_map[country]})",
         "Trading Economics", yield_meta["source"], "latest quote", yield_meta["status"], yield_meta["fetched"]),
    ], columns=["Input", "Fetched value", "Source", "URL", "Data date", "Status", "Fetched at"])
    for _, r in src.iterrows():
        live = r["Status"].startswith("live")
        with st.container(border=True):
            st.markdown(f"**{r['Input']}** — {r['Fetched value']}  \n"
                        f"Source: [{r['Source']}]({r['URL']}) · Data date: **{r['Data date']}** · "
                        f"{'🟢' if live else '🟠'} {r['Status']} · Fetched: {r['Fetched at']}")
    st.download_button("⬇️ Download source log (CSV)", src.to_csv(index=False),
                       file_name="sources.csv", mime="text/csv")
    if any("snapshot" in m["status"] for m in [beta_meta, spread_meta, tax_meta, yield_meta]):
        st.warning("At least one source couldn't be fetched live, so its embedded snapshot is "
                   "shown (see Status). Use the overrides in the sidebar to enter current values.")

    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**10Y government yields (%)**")
        yt = yields_df.copy()
        yt["Tax rate (%)"] = yt["Country"].map(tax_map)
        st.dataframe(yt, hide_index=True, use_container_width=True, height=400)
    with cc2:
        st.markdown("**Unlevered industry betas**")
        st.dataframe(betas_df, hide_index=True, use_container_width=True, height=400)

st.caption("For teaching purposes. Check inputs before using for real decisions.")

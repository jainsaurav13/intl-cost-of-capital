# International Cost of Capital App

A Streamlit app that compares a project's **cost of equity, cost of debt and WACC in USD** and in the **currency of any selected country**.

## Features
- **Live data**, with source, data date and fetch time shown, plus a 🔄 **Refresh data** button:
  - U.S. industry **unlevered betas**: Aswath Damodaran, [`betas.xls`](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls) (the *Unlevered beta* column, not the cash-corrected one)
  - **BBB (Baa2) USD default spread**, large non-financial firms: Damodaran, [`ratings.html`](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html)
  - **Statutory corporate tax rates**: [OECD Corporate Tax Statistics 2024](https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html)
  - **10-year government bond yields**: [Trading Economics](https://tradingeconomics.com/bonds), scraped with no API key
- If a live fetch fails, the app uses an embedded snapshot, labels it 🟠 in *Data & sources*, and asks you to override it.
- **Inputs:** industry, target country, equity risk premium, target debt share, project tax rate (U.S. or selected country), and currency conversion method.
- **Manual overrides:** unlevered beta, both tax rates, USD BBB spread, both 10Y yields, and the local-currency BBB spread. With the local-spread override off, the auto spread is shown.
- **Outputs:** side-by-side USD vs local results, a table and chart, an all-industry comparison, built-in verification checks, and CSV downloads.

**Defaults:** Software (System & Application), United States, U.S. tax rate, 6.5% ERP, 30% debt.

## Formulas
| Step | Formula |
|---|---|
| Levered beta | βL = βU × [1 + (1 − t) × D/E], with D/E = w_D / (1 − w_D) |
| Cost of equity (USD) | Ke = y_US + βL × ERP |
| Cost of debt (USD) | Kd = y_US + s_BBB |
| Local currency (default) | 1 + K_FC = (1 + K_USD) × (1 + y_FC) / (1 + y_US) |
| Local currency (additive option) | K_FC = K_USD + (y_FC − y_US) |
| Local spread | auto: s_FC = Kd_FC − y_FC; or override: Kd_FC = y_FC + s_FC |
| WACC | (1 − w_D) × Ke + w_D × Kd × (1 − t) |

Both currencies use the same tax rate, debt share and ERP.

## Verification (also in the app's *Checks* tab)
1. Equal government yields with the local-spread override off give identical USD and local results.
2. Zero debt makes WACC equal to cost of equity.
3. Overriding the local-currency spread leaves USD results unchanged.
4. `verification.xlsx` recomputes one example (Software, India, defaults) with spreadsheet formulas.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy
Push `app.py`, `requirements.txt` and `README.md` to a public GitHub repo. Then at [share.streamlit.io](https://share.streamlit.io) choose **Create app**, pick the repo, set the main file to `app.py`, and deploy.

## Notes and limitations
- OECD's website sits behind a Cloudflare bot check. The app tries OECD's public SDMX data API and then the page. If both fail, it uses embedded 2024 combined statutory rates from the OECD report. Spot-check your target country and override if needed.
- Trading Economics' `/bonds` page builds its table with JavaScript for some clients. The app then reads TE's static 10Y table at `/country-list/government-bond-10y`, which has the same data.
- No country risk premium is added. Local default risk shows up only through the local government yield.

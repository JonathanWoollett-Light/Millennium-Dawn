#!/usr/bin/env python3
"""Render last_playtested.csv as a world choropleth of playtest recency.

Usage:
    python tools/playtest/generate_playtest_map.py [--csv PATH] [--out PATH]

Dates are YYYY-MM-DD; an empty date means never playtested. Viewing the
output HTML needs internet access (plotly.js and its world geometry load
from the plotly CDN).
"""

import argparse
import html
import sys
from csv import DictReader
from datetime import date, datetime
from pathlib import Path

try:
    import plotly.graph_objects as go
except ImportError:
    sys.exit("plotly is required: pip install plotly")

STALE_CAP_DAYS = 365

# Sequential blue ramp (light = recently playtested, dark = stale/never).
SEQ_RAMP = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
    "#0d366b",
]

SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
HAIRLINE = "#e1e0d9"
UNTRACKED_LAND = "#eceae4"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# TAG -> (ISO 3166-1 alpha-3 or None, display name). None = no paintable
# geometry in plotly's world map; those tags appear only in the table.
TAG_TO_ISO = {
    "ADO": ("AND", "Andorra"),
    "ADS": (None, "Aegis"),
    "AFG": ("AFG", "Afghanistan"),
    "AGL": ("AGO", "Angola"),
    "ALB": ("ALB", "Albania"),
    "ALG": ("DZA", "Algeria"),
    "ANJ": (None, "Anjouan"),
    "ANT": ("ATG", "Antigua and Barbuda"),
    "ARG": ("ARG", "Argentina"),
    "ARM": ("ARM", "Armenia"),
    "AST": ("AUS", "Australia"),
    "AUS": ("AUT", "Austria"),
    "AZE": ("AZE", "Azerbaijan"),
    "BAH": ("BHS", "Bahamas"),
    "BAN": ("BGD", "Bangladesh"),
    "BAR": ("BRB", "Barbados"),
    "BEL": ("BEL", "Belgium"),
    "BEN": ("BEN", "Benin"),
    "BFA": ("BFA", "Burkina Faso"),
    "BHR": ("BHR", "Bahrain"),
    "BHU": ("BTN", "Bhutan"),
    "BLR": ("BLR", "Belarus"),
    "BLZ": ("BLZ", "Belize"),
    "BOL": ("BOL", "Bolivia"),
    "BOS": ("BIH", "Bosnia and Herzegovina"),
    "BOT": ("BWA", "Botswana"),
    "BRA": ("BRA", "Brazil"),
    "BRM": ("MMR", "Myanmar"),
    "BRU": ("BRN", "Brunei"),
    "BUL": ("BGR", "Bulgaria"),
    "BUR": ("BDI", "Burundi"),
    "CAM": ("CMR", "Cameroon"),
    "CAN": ("CAN", "Canada"),
    "CAR": ("CAF", "Central African Republic"),
    "CBD": ("KHM", "Cambodia"),
    "CDI": ("CIV", "Ivory Coast"),
    "CHA": ("TCD", "Chad"),
    "CHI": ("CHN", "China"),
    "CHL": ("CHL", "Chile"),
    "CNG": ("COG", "Republic of the Congo"),
    "COL": ("COL", "Colombia"),
    "COM": ("COM", "Comoros"),
    "COS": ("CRI", "Costa Rica"),
    "CRO": ("HRV", "Croatia"),
    "CUB": ("CUB", "Cuba"),
    "CYP": ("CYP", "Cyprus"),
    "CZE": ("CZE", "Czechia"),
    "DEN": ("DNK", "Denmark"),
    "DJI": ("DJI", "Djibouti"),
    "DMI": ("DMA", "Dominica"),
    "DOM": ("DOM", "Dominican Republic"),
    "DRC": ("COD", "Democratic Republic of the Congo"),
    "ECU": ("ECU", "Ecuador"),
    "EGU": ("GNQ", "Equatorial Guinea"),
    "EGY": ("EGY", "Egypt"),
    "ELS": ("SLV", "El Salvador"),
    "ENG": ("GBR", "United Kingdom"),
    "ERI": ("ERI", "Eritrea"),
    "EST": ("EST", "Estonia"),
    "ETH": ("ETH", "Ethiopia"),
    "FAO": ("FRO", "Faroe Islands"),
    "FGU": (None, "French Guiana"),
    "FIJ": ("FJI", "Fiji"),
    "FIN": ("FIN", "Finland"),
    "FLN": (None, "Flanders"),
    "FRA": ("FRA", "France"),
    "FYR": ("MKD", "North Macedonia"),
    "GAB": ("GAB", "Gabon"),
    "GAH": ("GHA", "Ghana"),
    "GAM": ("GMB", "Gambia"),
    "GEO": ("GEO", "Georgia"),
    "GER": ("DEU", "Germany"),
    "GRA": ("GRD", "Grenada"),
    "GRE": ("GRC", "Greece"),
    "GRN": ("GRL", "Greenland"),
    "GUA": ("GTM", "Guatemala"),
    "GUB": ("GNB", "Guinea-Bissau"),
    "GUI": ("GIN", "Guinea"),
    "GUY": ("GUY", "Guyana"),
    "HAI": ("HTI", "Haiti"),
    "HAZ": (None, "Hazaristan"),
    "HKG": ("HKG", "Hong Kong"),
    "HLS": ("VAT", "Vatican City"),
    "HOL": ("NLD", "Netherlands"),
    "HON": ("HND", "Honduras"),
    "HUN": ("HUN", "Hungary"),
    "ICE": ("ISL", "Iceland"),
    "IEK": (None, "Islamic Emirate of Kurdistan"),
    "IND": ("IDN", "Indonesia"),
    "IOM": ("IMN", "Isle of Man"),
    "IRE": ("IRL", "Ireland"),
    "IRQ": ("IRQ", "Iraq"),
    "ISR": ("ISR", "Israel"),
    "ITA": ("ITA", "Italy"),
    "JAM": ("JAM", "Jamaica"),
    "JAP": ("JPN", "Japan"),
    "JOR": ("JOR", "Jordan"),
    "KAC": (None, "Kachin"),
    "KAR": (None, "Karen"),
    "KAZ": ("KAZ", "Kazakhstan"),
    "KBY": (None, "Kabylia"),
    "KEN": ("KEN", "Kenya"),
    "KIR": ("KIR", "Kiribati"),
    "KOR": ("KOR", "South Korea"),
    "KOS": (None, "Kosovo"),
    "KUW": ("KWT", "Kuwait"),
    "KYR": ("KGZ", "Kyrgyzstan"),
    "LAO": ("LAO", "Laos"),
    "LAT": ("LVA", "Latvia"),
    "LBA": ("LBY", "Libya"),
    "LEB": ("LBN", "Lebanon"),
    "LES": ("LSO", "Lesotho"),
    "LIB": ("LBR", "Liberia"),
    "LIC": ("LIE", "Liechtenstein"),
    "LIT": ("LTU", "Lithuania"),
    "LUX": ("LUX", "Luxembourg"),
    "MAC": ("MAC", "Macau"),
    "MAD": ("MDG", "Madagascar"),
    "MAL": ("MLI", "Mali"),
    "MAR": ("MHL", "Marshall Islands"),
    "MAU": ("MRT", "Mauritania"),
    "MAY": ("MYS", "Malaysia"),
    "MEX": ("MEX", "Mexico"),
    "MIC": ("FSM", "Micronesia"),
    "MLD": ("MDV", "Maldives"),
    "MLT": ("MLT", "Malta"),
    "MLV": ("MDA", "Moldova"),
    "MLW": ("MWI", "Malawi"),
    "MNC": ("MCO", "Monaco"),
    "MNT": ("MNE", "Montenegro"),
    "MON": ("MNG", "Mongolia"),
    "MOR": ("MAR", "Morocco"),
    "MOZ": ("MOZ", "Mozambique"),
    "MRT": ("MUS", "Mauritius"),
    "MTE": (None, "Mayotte"),
    "NAM": ("NAM", "Namibia"),
    "NAU": ("NRU", "Nauru"),
    "NEP": ("NPL", "Nepal"),
    "NGR": ("NER", "Niger"),
    "NHN": (None, "North Shan State"),
    "NIC": ("NIC", "Nicaragua"),
    "NIG": ("NGA", "Nigeria"),
    "NIR": (None, "Northern Ireland"),
    "NKO": ("PRK", "North Korea"),
    "NKR": (None, "Artsakh"),
    "NLA": (None, "Netherlands Antilles"),
    "NRY": ("NOR", "Norway"),
    "NZL": ("NZL", "New Zealand"),
    "OMA": ("OMN", "Oman"),
    "OMG": (None, "Inner Mongolia"),
    "PAK": ("PAK", "Pakistan"),
    "PAL": ("PSE", "Palestine"),
    "PAN": ("PAN", "Panama"),
    "PAP": ("PNG", "Papua New Guinea"),
    "PAR": ("PRY", "Paraguay"),
    "PAU": ("PLW", "Palau"),
    "PER": ("IRN", "Iran"),
    "PHI": ("PHL", "Philippines"),
    "POL": ("POL", "Poland"),
    "POR": ("PRT", "Portugal"),
    "PRU": ("PER", "Peru"),
    "PUK": (None, "Patriotic Union of Kurdistan"),
    "QAT": ("QAT", "Qatar"),
    "RAJ": ("IND", "India"),
    "ROM": ("ROU", "Romania"),
    "RWA": ("RWA", "Rwanda"),
    "SAF": ("ZAF", "South Africa"),
    "SAM": ("WSM", "Samoa"),
    "SAO": ("STP", "Sao Tome and Principe"),
    "SAU": ("SAU", "Saudi Arabia"),
    "SEN": ("SEN", "Senegal"),
    "SER": ("SRB", "Serbia"),
    "SEY": ("SYC", "Seychelles"),
    "SHA": ("ESH", "Western Sahara"),
    "SHN": (None, "South Shan State"),
    "SIA": ("THA", "Thailand"),
    "SIE": ("SLE", "Sierra Leone"),
    "SIN": ("SGP", "Singapore"),
    "SLO": ("SVK", "Slovakia"),
    "SLV": ("SVN", "Slovenia"),
    "SMA": ("SMR", "San Marino"),
    "SML": (None, "Somaliland"),
    "SOL": ("SLB", "Solomon Islands"),
    "SOM": ("SOM", "Somalia"),
    "SOV": ("RUS", "Russia"),
    "SPR": ("ESP", "Spain"),
    "SRI": ("LKA", "Sri Lanka"),
    "SSU": ("SSD", "South Sudan"),
    "STK": ("KNA", "Saint Kitts and Nevis"),
    "STL": ("LCA", "Saint Lucia"),
    "STV": ("VCT", "Saint Vincent and the Grenadines"),
    "SUD": ("SDN", "Sudan"),
    "SUR": ("SUR", "Suriname"),
    "SWA": ("SWZ", "Eswatini"),
    "SWE": ("SWE", "Sweden"),
    "SWI": ("CHE", "Switzerland"),
    "SYR": ("SYR", "Syria"),
    "TAB": (None, "Tabaristan"),
    "TAI": ("TWN", "Taiwan"),
    "TAJ": ("TJK", "Tajikistan"),
    "TIM": ("TLS", "Timor-Leste"),
    "TML": (None, "Tamil Eelam"),
    "TNZ": ("TZA", "Tanzania"),
    "TOG": ("TGO", "Togo"),
    "TON": ("TON", "Tonga"),
    "TRA": (None, "Transylvania"),
    "TRI": ("TTO", "Trinidad and Tobago"),
    "TRK": ("TKM", "Turkmenistan"),
    "TUL": (None, "Tuvalu"),  # atolls have no polygon in plotly's 50m geometry
    "TUN": ("TUN", "Tunisia"),
    "TUR": ("TUR", "Turkey"),
    "UAE": ("ARE", "United Arab Emirates"),
    "UGA": ("UGA", "Uganda"),
    "UKR": ("UKR", "Ukraine"),
    "URG": ("URY", "Uruguay"),
    "USA": ("USA", "United States"),
    "UZB": ("UZB", "Uzbekistan"),
    "VAN": ("VUT", "Vanuatu"),
    "VEN": ("VEN", "Venezuela"),
    "VER": ("CPV", "Cape Verde"),
    "VIE": ("VNM", "Vietnam"),
    "WAA": (None, "Wa State"),
    "WLC": (None, "Wallachia"),
    "YEM": ("YEM", "Yemen"),
    "ZAM": ("ZMB", "Zambia"),
    "ZAN": (None, "Zanzibar"),
    "ZIM": ("ZWE", "Zimbabwe"),
}


def parse_rows(csv_path: Path) -> tuple[dict[str, date | None], list[str]]:
    rows: dict[str, date | None] = {}
    warnings: list[str] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = DictReader(f)
        fields = [fn.strip() for fn in reader.fieldnames or []]
        if fields[:2] != ["tag", "last_playtested"]:
            sys.exit(f"{csv_path}: expected header 'tag,last_playtested', got {fields}")
        for lineno, row in enumerate(reader, start=2):
            tag = (row.get("tag") or "").strip()
            raw = (row.get("last_playtested") or "").strip()
            if not tag:
                continue
            if tag in rows:
                warnings.append(f"line {lineno}: duplicate tag {tag}, keeping the later entry")
            when = None
            if raw:
                try:
                    when = datetime.strptime(raw, "%Y-%m-%d").date()
                except ValueError:
                    sys.exit(f"{csv_path} line {lineno}: bad date '{raw}' for {tag} (expected YYYY-MM-DD)")
            rows[tag] = when
    return rows, warnings


def build_records(rows: dict[str, date | None], today: date) -> tuple[list[dict], list[str]]:
    records = []
    warnings = []
    for tag, when in rows.items():
        iso3, name = TAG_TO_ISO.get(tag, (None, tag))
        if tag not in TAG_TO_ISO:
            warnings.append(f"unknown tag {tag}: not in TAG_TO_ISO, shown only in the table")
        days = None
        if when is not None:
            days = (today - when).days
            if days < 0:
                warnings.append(f"{tag}: date {when} is in the future, treating as today")
                days = 0
        records.append({"tag": tag, "name": name, "iso3": iso3, "date": when, "days": days})

    iso_owners: dict[str, list[str]] = {}
    for r in records:
        if r["iso3"]:
            iso_owners.setdefault(r["iso3"], []).append(r["tag"])
    for iso3, tags in iso_owners.items():
        if len(tags) > 1:
            warnings.append(f"tags {', '.join(tags)} all paint {iso3}; only one will show")

    records.sort(key=lambda r: (0, r["tag"]) if r["days"] is None else (1, -r["days"], r["tag"]))
    return records, warnings


def build_figure(records: list[dict]) -> go.Figure:
    mapped = [r for r in records if r["iso3"]]
    z = [STALE_CAP_DAYS if r["days"] is None else min(r["days"], STALE_CAP_DAYS) for r in mapped]
    customdata = [
        [
            r["name"],
            r["tag"],
            "never" if r["date"] is None else r["date"].isoformat(),
            "Never playtested" if r["days"] is None else f"{r['days']} days ago",
        ]
        for r in mapped
    ]
    steps = len(SEQ_RAMP) - 1
    fig = go.Figure(
        go.Choropleth(
            locations=[r["iso3"] for r in mapped],
            z=z,
            zmin=0,
            zmax=STALE_CAP_DAYS,
            customdata=customdata,
            colorscale=[(i / steps, c) for i, c in enumerate(SEQ_RAMP)],
            marker_line_color=SURFACE,
            marker_line_width=0.4,
            colorbar=dict(
                title=dict(text="Days since<br>last playtest", font=dict(size=12, color=INK_SECONDARY)),
                tickvals=[0, 90, 180, 270, STALE_CAP_DAYS],
                ticktext=["0", "90", "180", "270", f"{STALE_CAP_DAYS}+ / never"],
                tickfont=dict(size=11, color=INK_MUTED),
                outlinewidth=0,
                thickness=12,
                len=0.55,
            ),
            hovertemplate=(
                "%{customdata[0]} (%{customdata[1]})<br>"
                "Last playtested: %{customdata[2]}<br>"
                "%{customdata[3]}<extra></extra>"
            ),
        )
    )
    fig.update_geos(
        projection_type="natural earth",
        resolution=50,
        showframe=False,
        showcoastlines=False,
        showcountries=True,
        countrycolor=HAIRLINE,
        countrywidth=0.4,
        showland=True,
        landcolor=UNTRACKED_LAND,
        showocean=True,
        oceancolor=PAGE,
        showlakes=False,
        bgcolor=SURFACE,
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=HAIRLINE, font=dict(family=FONT, color=INK)),
        height=560,
    )
    return fig


def build_page(fig: go.Figure, records: list[dict], today: date) -> str:
    total = len(records)
    never = sum(1 for r in records if r["days"] is None)
    off_map = sum(1 for r in records if not r["iso3"])
    fig_html = fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displaylogo": False})

    rows_html = []
    for r in records:
        tested = "never" if r["date"] is None else r["date"].isoformat()
        ago = "&mdash;" if r["days"] is None else f"{r['days']} days ago"
        badge = "" if r["iso3"] else ' <span class="off-map">not on map</span>'
        rows_html.append(
            f"<tr><td>{html.escape(r['tag'])}</td>"
            f"<td>{html.escape(r['name'])}{badge}</td>"
            f"<td class='num'>{tested}</td><td class='num'>{ago}</td></tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Millennium Dawn playtest recency</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; background: {PAGE}; color: {INK};
    font-family: {FONT}; font-size: 14px; line-height: 1.5;
  }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitle {{ color: {INK_SECONDARY}; margin: 0 0 16px; }}
  .card {{
    background: {SURFACE}; border: 1px solid rgba(11, 11, 11, 0.10);
    border-radius: 8px; overflow: hidden; margin-bottom: 24px;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    text-align: left; font-weight: 600; color: {INK_SECONDARY};
    border-bottom: 1px solid {HAIRLINE}; padding: 8px 12px;
  }}
  td {{ padding: 6px 12px; border-bottom: 1px solid {HAIRLINE}; }}
  tr:last-child td {{ border-bottom: none; }}
  td.num, th.num {{ font-variant-numeric: tabular-nums; }}
  .off-map {{ color: {INK_MUTED}; font-size: 12px; }}
</style>
</head>
<body>
<main>
  <h1>Playtest recency</h1>
  <p class="subtitle">
    Generated {today.isoformat()} &middot; {total} tracked countries &middot;
    {never} never playtested &middot; {off_map} without map geometry (table only)
  </p>
  <div class="card">{fig_html}</div>
  <div class="card">
    <table>
      <thead><tr><th>Tag</th><th>Country</th><th class="num">Last playtested</th><th class="num">Recency</th></tr></thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>
</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the playtest CSV into a world choropleth.")
    default_csv = Path(__file__).resolve().parent / "last_playtested.csv"
    parser.add_argument("--csv", type=Path, default=default_csv, help="input CSV (default: %(default)s)")
    parser.add_argument("--out", type=Path, default=None, help="output HTML (default: playtest_map.html next to the CSV)")
    args = parser.parse_args()
    out = args.out or args.csv.parent / "playtest_map.html"

    rows, warnings = parse_rows(args.csv)
    today = date.today()
    records, more_warnings = build_records(rows, today)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_page(build_figure(records), records, today), encoding="utf-8")

    for warning in warnings + more_warnings:
        print(f"warning: {warning}", file=sys.stderr)
    never = sum(1 for r in records if r["days"] is None)
    print(f"{out}: {len(records)} countries ({never} never playtested)")


if __name__ == "__main__":
    main()

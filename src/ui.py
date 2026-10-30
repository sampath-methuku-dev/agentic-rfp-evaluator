"""Infographic UI: hero, summary banner, KPI row, supplier cards, charts and result tabs."""
import html
import json

import altair as alt
import pandas as pd
import streamlit as st

# One colour per supplier, assigned by final rank so cards and charts always agree.
PALETTE = ["#0f9d8a", "#f2b705", "#f2800d", "#3b82c4", "#8e6bbf", "#7a8794"]
# Criteria get their own cool palette so they are never confused with supplier colours.
CRITERIA_PALETTE = ["#16425b", "#2e86ab", "#5fb49c", "#a3c9a8", "#c9d6df", "#e0a96d"]
HEAT_RAMP = ["#e8f6f3", "#0b6b5c"]
RING_TRACK = "#9aa5b1"
CARDS_PER_ROW = 3

_e = html.escape


def supplier_color(final_rank: int) -> str:
    return PALETTE[(final_rank - 1) % len(PALETTE)]


def _pct_of_max(row: dict) -> float:
    return row["score"] / row["max_score"] * 100


def _points(row: dict) -> float:
    """Weighted points this criterion adds to the absolute score."""
    return row["score"] / row["max_score"] * row["weight"]


# ------------------------------------------------------------------ header / summary
def hero() -> None:
    steps = ["Upload proposals", "AI scores each criterion", "Python validates and ranks",
             "Explainable leaderboard"]
    chips = "".join(
        f'<span style="background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.25);'
        f'padding:6px 12px;border-radius:999px;font-size:13px;">{i}. {s}</span>'
        for i, s in enumerate(steps, start=1))
    st.html(
        '<div style="background:linear-gradient(120deg,#0b2a3a 0%,#0b5a63 55%,#0f9d8a 100%);'
        'border-radius:18px;padding:30px 34px;color:#fff;">'
        '<div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;opacity:.75;">'
        'Agentic procurement workflow</div>'
        '<div style="font-size:34px;font-weight:700;margin:6px 0 8px;line-height:1.15;">'
        'RFP evaluation &amp; supplier ranking</div>'
        '<div style="opacity:.88;max-width:760px;line-height:1.5;">'
        'The AI judges each proposal against your criteria and cites evidence. Python does all '
        'the scoring, peer benchmarking and ranking, so every result is traceable.</div>'
        f'<div style="margin-top:18px;display:flex;flex-wrap:wrap;gap:8px;">{chips}</div></div>')


def winner_banner(run: dict) -> None:
    suppliers = run["suppliers"]
    top = suppliers[0]
    if len(suppliers) == 1:
        detail = "Only one supplier was evaluated."
    else:
        second = suppliers[1]
        lead = top["ppi"] - second["ppi"]
        detail = (f"Leads {_e(second['supplier_name'])} by {lead:.1f} PPI points."
                  if lead > 0 else
                  f"Tied with {_e(second['supplier_name'])} on PPI; decided by the tie-break rules.")
    st.html(
        '<div style="background:linear-gradient(120deg,#0f9d8a,#0b6b5c);border-radius:16px;'
        'padding:20px 26px;color:#fff;display:flex;align-items:center;gap:22px;flex-wrap:wrap;">'
        '<div style="font-size:44px;font-weight:800;line-height:1;opacity:.95;">#1</div>'
        '<div style="flex:1;min-width:220px;">'
        '<div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;opacity:.8;">'
        'Top ranked supplier</div>'
        f'<div style="font-size:26px;font-weight:700;">{_e(top["supplier_name"])}</div>'
        f'<div style="opacity:.9;">{detail}</div></div>'
        '<div style="text-align:right;">'
        f'<div style="font-size:30px;font-weight:700;">{top["ppi"]:.1f}</div>'
        '<div style="font-size:12px;opacity:.85;">Peer Performance Index</div></div>'
        '<div style="text-align:right;">'
        f'<div style="font-size:30px;font-weight:700;">{top["absolute_score"]:.1f}</div>'
        '<div style="font-size:12px;opacity:.85;">Absolute score / 100</div></div></div>')


def kpi_row(run: dict) -> None:
    suppliers = run["suppliers"]
    ppis = [s["ppi"] for s in suppliers]
    with st.container(horizontal=True):
        st.metric("Suppliers ranked", len(suppliers), border=True)
        st.metric("Top PPI", f"{max(ppis):.1f}", border=True, chart_data=ppis, chart_type="bar")
        st.metric("PPI spread, top to last", f"{max(ppis) - min(ppis):.1f} pts", border=True)
        st.metric("Risks flagged", sum(len(s["risks"]) for s in suppliers), border=True)
        st.metric("Validation notes", sum(len(s["warnings"]) for s in suppliers) + len(run.get("warnings", [])),
                  border=True, help="Changes the validation tool made to model output, plus run-level warnings.")


# ------------------------------------------------------------------ supplier cards
def score_ring(score: float, color: str) -> alt.LayerChart:
    """Donut showing an absolute score out of 100 with the number in the middle."""
    value = max(0.0, min(100.0, score))
    arcs = alt.Chart(pd.DataFrame({"part": ["score", "rest"], "value": [value, 100 - value],
                                   "order": [0, 1]})).mark_arc(
        innerRadius=50, outerRadius=68, cornerRadius=6).encode(
        theta=alt.Theta("value:Q", stack=True),
        color=alt.Color("part:N", legend=None,
                        scale=alt.Scale(domain=["score", "rest"], range=[color, RING_TRACK])),
        opacity=alt.Opacity("part:N", legend=None,
                            scale=alt.Scale(domain=["score", "rest"], range=[1, 0.25])),
        order=alt.Order("order:Q"))
    label = alt.Chart(pd.DataFrame({"text": [f"{score:.0f}"]})).mark_text(
        fontSize=30, fontWeight="bold").encode(text="text:N")
    return (arcs + label).properties(width=150, height=150)


def criterion_bars(rows: list[dict], color: str) -> alt.Chart:
    data = pd.DataFrame({"Criterion": [r["name"] for r in rows],
                         "Score (% of max)": [_pct_of_max(r) for r in rows]})
    return alt.Chart(data).mark_bar(color=color, cornerRadiusEnd=3).encode(
        y=alt.Y("Criterion:N", sort=None, title=None, axis=alt.Axis(labelLimit=120)),
        x=alt.X("Score (% of max):Q", scale=alt.Scale(domain=[0, 100]), title=None),
        tooltip=["Criterion", alt.Tooltip("Score (% of max):Q", format=".0f")],
    ).properties(height=26 * len(rows) + 10)


def supplier_card(s: dict) -> None:
    color = supplier_color(s["final_rank"])
    best = max(s["criteria"], key=_pct_of_max)
    worst = min(s["criteria"], key=_pct_of_max)
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(s["supplier_name"])
            st.badge(f"Rank #{s['final_rank']}", color="green" if s["final_rank"] == 1 else "gray")
        with st.container(horizontal=True, horizontal_alignment="center"):
            st.altair_chart(score_ring(s["absolute_score"], color), width="content")
        st.caption(f"Absolute weighted score: {s['absolute_score']:.1f} / 100", text_alignment="center")
        left, right = st.columns(2)
        left.metric("PPI", f"{s['ppi']:.1f}")
        right.metric("Experience", f"{s['experience_rating']:g} / 10")
        left.metric("Submitted", s["submission_date"])
        right.metric("Risks flagged", len(s["risks"]))
        st.caption(f":material/trending_up: Strongest: **{best['name']}** ({best['score']:g}/{best['max_score']:g})")
        st.caption(f":material/trending_down: Weakest: **{worst['name']}** ({worst['score']:g}/{worst['max_score']:g})")
        st.altair_chart(criterion_bars(s["criteria"], color), width="stretch")


def supplier_cards(suppliers: list[dict]) -> None:
    """Cards in rows of three, in the order given."""
    for start in range(0, len(suppliers), CARDS_PER_ROW):
        cols = st.columns(CARDS_PER_ROW)
        for col, s in zip(cols, suppliers[start:start + CARDS_PER_ROW]):
            with col:
                supplier_card(s)


# ------------------------------------------------------------------ comparison charts
def _long_frame(suppliers: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {"Criterion": r["name"], "Supplier": s["supplier_name"], "pct": _pct_of_max(r),
         "label": f"{r['score']:g}/{r['max_score']:g}", "Points": _points(r),
         "Weight": r["weight"]}
        for s in suppliers for r in s["criteria"]])


def comparison_chart(suppliers: list[dict]) -> None:
    """Grouped bars: each criterion, one bar per supplier."""
    by_rank = sorted(suppliers, key=lambda x: x["final_rank"])
    ordered = [s["supplier_name"] for s in by_rank]
    colors = [supplier_color(s["final_rank"]) for s in by_rank]
    chart = alt.Chart(_long_frame(suppliers)).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("Criterion:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelLimit=140)),
        xOffset=alt.XOffset("Supplier:N", sort=ordered),
        y=alt.Y("pct:Q", scale=alt.Scale(domain=[0, 100]), title="Score (% of max)"),
        color=alt.Color("Supplier:N", scale=alt.Scale(domain=ordered, range=colors),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Supplier", "Criterion", alt.Tooltip("pct:Q", title="% of max", format=".0f")],
    ).properties(height=320)
    st.altair_chart(chart, width="stretch")


def heatmap_chart(suppliers: list[dict]) -> None:
    """Supplier x criterion grid, darker = closer to the maximum score."""
    ordered = [s["supplier_name"] for s in sorted(suppliers, key=lambda x: x["final_rank"])]
    base = alt.Chart(_long_frame(suppliers)).encode(
        x=alt.X("Criterion:N", sort=None, title=None,
                axis=alt.Axis(orient="top", labelAngle=0, labelLimit=140)),
        y=alt.Y("Supplier:N", sort=ordered, title=None))
    rects = base.mark_rect(cornerRadius=5, stroke="white", strokeWidth=3).encode(
        color=alt.Color("pct:Q", scale=alt.Scale(domain=[0, 100], range=HEAT_RAMP),
                        legend=alt.Legend(title="% of max", orient="bottom")),
        tooltip=["Supplier", "Criterion", "label"])
    labels = base.mark_text(fontWeight="bold", fontSize=14).encode(
        text="label:N",
        color=alt.condition(alt.datum.pct > 55, alt.value("white"), alt.value("#16313a")))
    st.altair_chart((rects + labels).properties(height=60 * len(suppliers) + 40), width="stretch")


def contribution_chart(suppliers: list[dict]) -> None:
    """Stacked weighted points: how each criterion builds the absolute score."""
    by_rank = sorted(suppliers, key=lambda x: x["final_rank"])
    ordered = [s["supplier_name"] for s in by_rank]
    criteria_order = [r["name"] for r in by_rank[0]["criteria"]]
    data = _long_frame(suppliers)
    bars = alt.Chart(data).mark_bar().encode(
        y=alt.Y("Supplier:N", sort=ordered, title=None),
        x=alt.X("sum(Points):Q", scale=alt.Scale(domain=[0, 108]), title="Weighted points (absolute score)"),
        color=alt.Color("Criterion:N", sort=criteria_order,
                        scale=alt.Scale(domain=criteria_order, range=CRITERIA_PALETTE[:len(criteria_order)]),
                        legend=alt.Legend(orient="top", title=None)),
        order=alt.Order("Weight:Q", sort="descending"),
        tooltip=["Supplier", "Criterion", alt.Tooltip("sum(Points):Q", title="Points", format=".1f")])
    totals = alt.Chart(pd.DataFrame(
        {"Supplier": ordered, "Total": [s["absolute_score"] for s in by_rank]})).mark_text(
        align="left", dx=5, fontWeight="bold").encode(
        y=alt.Y("Supplier:N", sort=ordered), x="Total:Q", text=alt.Text("Total:Q", format=".1f"))
    st.altair_chart((bars + totals).properties(height=60 * len(suppliers) + 50), width="stretch")


# ------------------------------------------------------------------ tables
def leaderboard_table(suppliers: list[dict]) -> None:
    st.dataframe(
        pd.DataFrame([{
            "Rank": s["final_rank"], "Supplier": s["supplier_name"],
            "Absolute score": s["absolute_score"], "PPI": s["ppi"],
            "Submission date": s["submission_date"], "Experience rating": s["experience_rating"],
        } for s in suppliers]),
        hide_index=True, width="stretch",
        column_config={
            "Absolute score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
            "PPI": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
            "Experience rating": st.column_config.NumberColumn(format="%.1f / 10"),
        })


def scorecard_table(s: dict) -> None:
    st.dataframe(
        pd.DataFrame([{
            "Criterion": r["name"], "Weight (%)": r["weight"], "Score": r["score"],
            "Max": r["max_score"], "Score (% of max)": _pct_of_max(r),
            "Benchmark": r["benchmark"], "Gap": r["gap"],
            "Relative %": r["relative_pct"], "Points": _points(r),
        } for r in s["criteria"]]),
        hide_index=True, width="stretch",
        column_config={
            "Score (% of max)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
            "Relative %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
            "Gap": st.column_config.NumberColumn(format="%+.1f"),
            "Points": st.column_config.NumberColumn(format="%.1f",
                                                    help="Weighted points added to the absolute score"),
        })


# ------------------------------------------------------------------ results
def render_run(run: dict, prefix: str) -> None:
    suppliers = run["suppliers"]
    tab_overview, tab_compare, tab_cards, tab_details = st.tabs([
        ":material/dashboard: Overview", ":material/compare_arrows: Compare",
        ":material/fact_check: Scorecards", ":material/info: Run details"])

    with tab_overview:
        winner_banner(run)
        kpi_row(run)
        sort_by = st.segmented_control("Sort cards by", ["Rank", "Absolute score", "PPI"],
                                       default="Rank", key=f"{prefix}_sort") or "Rank"
        sort_key = {"Rank": lambda x: x["final_rank"],
                    "Absolute score": lambda x: -x["absolute_score"],
                    "PPI": lambda x: -x["ppi"]}[sort_by]
        supplier_cards(sorted(suppliers, key=sort_key))
        st.subheader("Leaderboard")
        leaderboard_table(suppliers)

    with tab_compare:
        with st.container(border=True):
            st.subheader("Peer comparison by criterion")
            comparison_chart(suppliers)
        with st.container(border=True):
            st.subheader("Strength heatmap")
            st.caption("Each cell is the supplier's score on that criterion; darker means closer to the maximum.")
            heatmap_chart(suppliers)
        with st.container(border=True):
            st.subheader("How each score is built")
            st.caption("Weighted points per criterion. The bar total is the absolute score out of 100.")
            contribution_chart(suppliers)

    with tab_cards:
        chosen = st.selectbox("Supplier", [s["supplier_name"] for s in suppliers],
                              key=f"{prefix}_supplier")
        s = next(x for x in suppliers if x["supplier_name"] == chosen)
        with st.container(horizontal=True):
            st.metric("Rank", f"#{s['final_rank']}", border=True)
            st.metric("Absolute score", f"{s['absolute_score']:.1f} / 100", border=True)
            st.metric("Peer Performance Index", f"{s['ppi']:.1f}", border=True)
            st.metric("Source file", s.get("source_file") or "-", border=True)
        scorecard_table(s)
        st.subheader("Justification and evidence")
        for r in s["criteria"]:
            with st.expander(f"{r['name']}: {r['score']:g} / {r['max_score']:g}", icon=":material/format_quote:"):
                st.markdown(f"**Justification:** {r['justification'] or '-'}")
                st.markdown(f"**Evidence:** {r['evidence'] or '-'}")
        if s["overall_summary"]:
            st.markdown(f"**Summary:** {s['overall_summary']}")
        if s["risks"]:
            st.markdown("**Risks flagged**\n" + "\n".join(f"- {r}" for r in s["risks"]))
        if s["warnings"]:
            st.warning("Validation notes for this supplier:\n" + "\n".join(f"- {w}" for w in s["warnings"]),
                       icon=":material/rule:")

    with tab_details:
        with st.container(horizontal=True):
            st.metric("RFP_RUN_ID", run["rfp_run_id"], border=True)
            st.metric("Status", run["status"], border=True)
            st.metric("Provider", run.get("provider") or "-", border=True)
            st.metric("Model", run.get("model") or "-", border=True)
            st.metric("Created (UTC)", run["created_at"], border=True)
        notes = run.get("tie_break_explanations", [])
        st.subheader("Tie-break explanation")
        if notes:
            st.markdown("\n".join(f"- {n}" for n in notes))
        else:
            st.caption("No PPI ties in this run; ranks follow PPI order.")
        checks = run.get("input_checks", [])
        if checks:
            st.subheader("Input checks")
            st.dataframe(pd.DataFrame([{
                "File": c["filename"], "Supplier": c["supplier_name"],
                "Result": {"ok": "Passed", "warning": "Passed with warnings", "rejected": "Excluded"}[c["status"]],
                "Notes": " ".join(c["messages"]) or "All expected sections found.",
            } for c in checks]), hide_index=True, width="stretch")
        for item in run.get("excluded_suppliers", []):
            st.error(f"Excluded {item['supplier_name']} ({item['filename']}): {item['reason']}")
        for w in run.get("warnings", []):
            st.warning(w)
        st.download_button("Download complete result (JSON)", data=json.dumps(run, indent=2),
                           file_name=f"{run['rfp_run_id']}.json", mime="application/json",
                           icon=":material/download:", key=f"{prefix}_download")

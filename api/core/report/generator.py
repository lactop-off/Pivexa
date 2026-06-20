"""レポート生成（HTML テンプレート → PDF）（詳細設計書 共通基盤編 5.4）。

AnalysisResult + Interpretation を HTML に流し込み、WeasyPrint で PDF 化する。
グラフ PNG は base64 で埋め込み、PDF を自己完結させる。
"""
from __future__ import annotations

import base64
import os
from datetime import datetime
from html import escape

REPORTS_DIR = os.environ.get("REPORTS_DIR", "/data/reports")

_LEVEL_COLOR = {
    "info": "#eff6ff",
    "highlight": "#dcfce7",
    "caution": "#fef3c7",
}


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}" if not v.is_integer() else str(int(v))
    return str(v)


def _chart_data_uri(path: str) -> str | None:
    name = os.path.basename(path)
    full = os.path.join(REPORTS_DIR, name)
    if not os.path.exists(full):
        return None
    with open(full, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def build_html(
    *,
    title: str,
    dataset_name: str,
    result: dict,
    interpretation: dict,
) -> str:
    metrics_rows = "".join(
        f"<tr><td>{escape(m['label'])}</td><td class='num'>{_fmt(m['value'])}</td>"
        f"<td>{'有意' if m.get('significant') else ''}</td></tr>"
        for m in result.get("summary_metrics", [])
    )

    coef_rows = ""
    for c in result.get("coefficients", []):
        sig = c.get("p_value") is not None and c["p_value"] < 0.05
        extra = []
        if "odds_ratio" in c.get("extra", {}):
            extra.append(f"オッズ比 {c['extra']['odds_ratio']}")
        if "vif" in c.get("extra", {}):
            extra.append(f"VIF {c['extra']['vif']}")
        ci = (
            f"{_fmt(c['ci_low'])}〜{_fmt(c['ci_high'])}"
            if c.get("ci_low") is not None
            else "—"
        )
        coef_rows += (
            f"<tr style=\"background:{'#dcfce7' if sig else 'transparent'}\">"
            f"<td>{escape(c['variable'])}</td>"
            f"<td class='num'>{_fmt(c['coef'])}</td>"
            f"<td class='num'>{_fmt(c.get('std_err'))}</td>"
            f"<td class='num'>{_fmt(c.get('p_value'))}</td>"
            f"<td class='num'>{ci}</td>"
            f"<td class='num'>{' / '.join(extra) or '—'}</td></tr>"
        )

    charts_html = ""
    for ch in result.get("charts", []):
        uri = _chart_data_uri(ch["path"])
        if uri:
            charts_html += (
                f"<div class='chart'><p>{escape(ch['label'])}</p>"
                f"<img src='{uri}' /></div>"
            )

    sentences_html = "".join(
        f"<div class='sentence' style=\"background:{_LEVEL_COLOR.get(s['level'], '#fff')}\">"
        f"{escape(s['text'])}</div>"
        for s in interpretation.get("sentences", [])
    )

    warnings_html = "".join(
        f"<div class='sentence' style='background:#fef3c7'>⚠ {escape(w)}</div>"
        for w in result.get("warnings", [])
    )

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font-family: "Noto Sans CJK JP", "Noto Sans JP", sans-serif; color: #111827; font-size: 12px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 14px; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px; margin: 18px 0 8px; }}
  .muted {{ color: #6b7280; font-size: 11px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 6px 0; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 5px 8px; text-align: left; }}
  th {{ background: #f9fafb; }}
  .num {{ text-align: right; }}
  .chart {{ margin: 8px 0; }}
  .chart img {{ max-width: 100%; border: 1px solid #e5e7eb; }}
  .chart p {{ margin: 0 0 2px; font-size: 11px; color: #6b7280; }}
  .sentence {{ padding: 6px 10px; border-radius: 6px; margin-bottom: 5px; }}
</style></head><body>
  <h1>{escape(title)}</h1>
  <p class="muted">データセット: {escape(dataset_name)} ／ 出力日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}
     ／ サンプル数: {result.get('sample_size', 0)}</p>

  {f'<h2>モデル全体の指標</h2><table><tr><th>指標</th><th class="num">値</th><th>有意</th></tr>{metrics_rows}</table>' if metrics_rows else ''}
  {f'<h2>説明変数ごとの結果</h2><table><tr><th>変数</th><th class="num">係数</th><th class="num">標準誤差</th><th class="num">P値</th><th class="num">95%CI</th><th class="num">補足</th></tr>{coef_rows}</table>' if coef_rows else ''}
  {f'<h2>グラフ</h2>{charts_html}' if charts_html else ''}
  {f'<h2>注意事項</h2>{warnings_html}' if warnings_html else ''}
  <h2>解釈サポート</h2>
  {sentences_html}
</body></html>"""


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html).write_pdf()

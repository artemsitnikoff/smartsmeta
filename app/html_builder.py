from __future__ import annotations

import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.models import EstimateResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class RoleInfo:
    rate: int
    hours: float
    cost: float


@dataclass
class Totals:
    hours_min: float
    hours_base: float
    hours_max: float
    cost_base: float


def _enrich(result: EstimateResult, rates: dict[str, int]) -> tuple:
    """Pre-compute per-phase/variant totals and role summary.

    Returns (variants, role_summary, totals) where variants have extra
    _hours_* / _cost_* attributes attached to phases and variants.
    """
    role_summary: dict[str, RoleInfo] = OrderedDict()
    grand_hours_min = grand_hours_base = grand_hours_max = grand_cost = 0.0

    variants = []
    for variant in result.variants:
        v_hmin = v_hbase = v_hmax = v_cost = 0.0
        enriched_phases = []

        for phase in variant.phases:
            p_hmin = p_hbase = p_hmax = p_cost = 0.0
            for t in phase.tasks:
                rate = rates.get(t.role, 0)
                p_hmin += t.hours_min
                p_hbase += t.hours_base
                p_hmax += t.hours_max
                p_cost += t.hours_base * rate

                if t.role not in role_summary:
                    role_summary[t.role] = RoleInfo(rate=rate, hours=0, cost=0)
                role_summary[t.role].hours += t.hours_base
                role_summary[t.role].cost += t.hours_base * rate

            phase._hours_min = p_hmin
            phase._hours_base = p_hbase
            phase._hours_max = p_hmax
            phase._cost_base = p_cost
            enriched_phases.append(phase)

            v_hmin += p_hmin
            v_hbase += p_hbase
            v_hmax += p_hmax
            v_cost += p_cost

        variant._hours_min = v_hmin
        variant._hours_base = v_hbase
        variant._hours_max = v_hmax
        variant._cost_base = v_cost
        variants.append(variant)

        grand_hours_min += v_hmin
        grand_hours_base += v_hbase
        grand_hours_max += v_hmax
        grand_cost += v_cost

    totals = Totals(
        hours_min=grand_hours_min,
        hours_base=grand_hours_base,
        hours_max=grand_hours_max,
        cost_base=grand_cost,
    )

    return variants, role_summary, totals


def render_estimate(result: EstimateResult, rates: dict[str, int]) -> str:
    """Render estimate to a temporary HTML file. Returns the file path."""
    variants, role_summary, totals = _enrich(result, rates)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("estimate.html")

    html = template.render(
        result=result,
        variants=variants,
        rates=rates,
        role_summary=role_summary,
        totals=totals,
        date=date.today().strftime("%d.%m.%Y"),
    )

    tmp = tempfile.NamedTemporaryFile(
        suffix=".html", prefix="smeta_", delete=False, mode="w", encoding="utf-8"
    )
    tmp.write(html)
    tmp.close()
    return tmp.name


def render_estimate_pdf(result: EstimateResult, rates: dict[str, int]) -> str:
    """Render estimate to a temporary PDF file. Returns the file path."""
    from weasyprint import HTML

    variants, role_summary, totals = _enrich(result, rates)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("estimate_pdf.html")

    html_str = template.render(
        result=result,
        variants=variants,
        rates=rates,
        role_summary=role_summary,
        totals=totals,
        date=date.today().strftime("%d.%m.%Y"),
    )

    tmp = tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix="smeta_", delete=False,
    )
    tmp.close()
    HTML(string=html_str).write_pdf(tmp.name)
    return tmp.name

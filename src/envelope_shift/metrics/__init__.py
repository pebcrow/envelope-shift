from .coverage import coverage
from .experience import experience
from .navigability import navigability
from .overlap import overlap_clearance

__all__ = ["coverage", "navigability", "overlap_clearance", "experience"]


def score_all(env, entities, params=None) -> dict:
    """The three published metrics plus the exploratory fourth, as one flat dict."""
    from ..params import DEFAULT

    p = params or DEFAULT
    out: dict = {}
    out.update(coverage(env, entities, p).as_dict())
    out.update(navigability(env, entities, p).as_dict())
    out.update(overlap_clearance(env, entities, p).as_dict())
    out.update(experience(env, entities, p).as_dict())
    return out

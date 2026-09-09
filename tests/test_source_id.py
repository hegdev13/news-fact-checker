from newsfact.tools.bias_table import BiasTable
from newsfact.tools.source_id import identify_source

TABLE = BiasTable({
    "thehindu.com": {"name": "The Hindu", "bias": "center-left", "factuality": "high", "country": "IN"},
    "foxnews.com": {"name": "Fox News", "bias": "right", "factuality": "mixed", "country": "US"},
    "reuters.com": {"name": "Reuters", "bias": "center", "factuality": "very-high", "country": "UK"},
})


def test_explicit_url_wins():
    g = identify_source("Some article body with no other clues.", "https://www.thehindu.com/news/story", TABLE)
    assert g.method == "url"
    assert g.domain == "thehindu.com"
    assert g.rating.name == "The Hindu"
    assert g.identified


def test_first_url_in_body_is_used_when_no_explicit_url():
    text = "Report\n\nRead more at https://foxnews.com/politics/item-1 today.\n"
    g = identify_source(text, None, TABLE)
    assert g.domain == "foxnews.com"
    assert g.method == "url"


def test_named_outlet_in_text_matches_without_a_url():
    text = "NEW DELHI — The following report appeared in The Hindu on Friday. By Priya Nair\n\nBody text."
    g = identify_source(text, None, TABLE)
    assert g.method == "byline"
    assert g.domain == "thehindu.com"
    assert g.byline == "Priya Nair"


def test_credit_style_wire_attribution_matches():
    g = identify_source("BENGALURU (Reuters) - Shares fell on Monday as investors...", None, TABLE)
    assert g.domain == "reuters.com"
    assert g.identified


def test_unidentifiable_source_returns_method_none():
    g = identify_source("A plain paragraph with no outlet name, no url, no byline.", None, TABLE)
    assert g.method == "none"
    assert not g.identified
    assert g.rating.bias == "unknown"


def test_www_and_subdomain_are_normalised():
    g = identify_source("x", "https://edition.thehindu.com/a/b", TABLE)
    # falls back to registrable parent
    assert g.domain == "edition.thehindu.com"
    assert g.rating.name == "The Hindu"

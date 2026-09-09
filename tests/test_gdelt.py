import httpx
import pytest

from newsfact.tools.gdelt import GdeltClient, GdeltError


def make_response(json_data, status_code=200):
    request = httpx.Request("GET", "https://example.com")
    return httpx.Response(status_code, json=json_data, request=request)


def test_search_parses_articles(monkeypatch):
    fake_json = {
        "articles": [
            {
                "title": "Outlet A reports X",
                "url": "https://a.example.com/1",
                "domain": "a.example.com",
                "seendate": "20260101T000000Z",
                "tone": "-2.5",
                "language": "English",
            },
            {
                "title": "Outlet B reports X too",
                "url": "https://b.example.com/1",
                "domain": "b.example.com",
                "seendate": "20260101T010000Z",
                "tone": "1.2",
                "language": "English",
            },
        ]
    }

    def fake_get(url, params=None, timeout=None):
        return make_response(fake_json)

    monkeypatch.setattr(httpx, "get", fake_get)

    client = GdeltClient(api_base="https://api.gdeltproject.org/api/v2/doc/doc")
    articles = client.search("some claim")

    assert len(articles) == 2
    assert articles[0].source_domain == "a.example.com"
    assert articles[0].tone == -2.5
    assert articles[1].tone == 1.2


def test_search_handles_empty_articles(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, params=None, timeout=None: make_response({"articles": []}))
    client = GdeltClient(api_base="https://api.gdeltproject.org/api/v2/doc/doc")
    assert client.search("no coverage claim") == []


def test_search_raises_gdelt_error_on_http_failure(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = GdeltClient(api_base="https://api.gdeltproject.org/api/v2/doc/doc")

    with pytest.raises(GdeltError):
        client.search("some claim")


def test_search_skips_malformed_article_entries(monkeypatch):
    fake_json = {"articles": [{"title": "Fine"}, None]}
    monkeypatch.setattr(httpx, "get", lambda url, params=None, timeout=None: make_response(fake_json))
    client = GdeltClient(api_base="https://api.gdeltproject.org/api/v2/doc/doc")
    articles = client.search("claim")
    # The malformed (None) entry is skipped; the dict entry parses with defaults.
    assert len(articles) == 1
    assert articles[0].title == "Fine"

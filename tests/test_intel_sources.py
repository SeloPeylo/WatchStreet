import httpx
import pytest

from watchstreet.intel import documents
from watchstreet.intel.connectors import gdelt, usgs
from watchstreet.intel.connectors.edgar import EdgarClient, extract_facts
from watchstreet.intel.connectors.rss import parse_feed
from watchstreet.intel.demo import DEMO_CIKS, DemoTransport, demo_resolver
from watchstreet.intel.fetch import Fetcher, FetchError, assert_public, html_to_text, pdf_to_text

HOSTS = {
    "public.example": ["93.184.216.34"],
    "internal.example": ["10.0.0.5"],
    "meta.example": ["169.254.169.254"],
    "loop.example": ["127.0.0.1"],
}


def fetcher(handler):
    return Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)), lambda h: HOSTS[h], min_interval_s=0
    )


def make_pdf(text):
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objs) + 1,
        xref,
    )


# ------------------------------------------------------------------ fetch guards
@pytest.mark.parametrize(
    "url",
    [
        "http://internal.example/x",
        "https://meta.example/latest",
        "http://loop.example/",
        "file:///etc/passwd",
        "ftp://public.example/x",
    ],
)
def test_ssrf_guard_blocks_non_public_and_non_http(url):
    with pytest.raises(FetchError):
        assert_public(url, lambda h: HOSTS.get(h, ["93.184.216.34"]))


def test_redirect_to_private_address_is_blocked():
    def handler(request):
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://meta.example/secret"})
        return httpx.Response(200, text="secret", headers={"content-type": "text/plain"})

    with pytest.raises(FetchError, match="non-public"):
        fetcher(handler).fetch("https://public.example/start")


def test_fetch_html_text_limits_and_content_types():
    html = "<html><head><style>x{}</style></head><body><h1>Titel</h1><p>Hallo  <b>Welt</b></p><script>evil()</script></body></html>"
    got = fetcher(
        lambda r: httpx.Response(
            200, text=html, headers={"content-type": "text/html; charset=utf-8"}
        )
    ).fetch("https://public.example/a")
    assert got.text == "Titel\nHallo Welt"
    with pytest.raises(FetchError, match="content type"):
        fetcher(
            lambda r: httpx.Response(
                200, content=b"\x00", headers={"content-type": "application/zip"}
            )
        ).fetch("https://public.example/a")
    with pytest.raises(FetchError, match="HTTP 404"):
        fetcher(lambda r: httpx.Response(404)).fetch("https://public.example/a")
    loop = fetcher(lambda r: httpx.Response(302, headers={"location": "https://public.example/b"}))
    with pytest.raises(FetchError, match="redirects"):
        loop.fetch("https://public.example/a")
    big = fetcher(
        lambda r: httpx.Response(
            200, content=b"x" * 9_000_000, headers={"content-type": "text/plain"}
        )
    )
    with pytest.raises(FetchError, match="too large"):
        big.fetch("https://public.example/a")


def test_pdf_extraction_and_broken_pdf():
    assert "Reserves 12 million" in pdf_to_text(make_pdf("Reserves 12 million ounces"))
    with pytest.raises(FetchError):
        pdf_to_text(b"not a pdf")
    got = fetcher(
        lambda r: httpx.Response(
            200, content=make_pdf("Annual report"), headers={"content-type": "application/pdf"}
        )
    ).fetch("https://public.example/r.pdf")
    assert "Annual report" in got.text
    assert html_to_text("<p>a</p><p>b</p>") == "a\nb"


# ------------------------------------------------------------------ documents
def test_document_store_dedupes_and_verifies_quotes(session):
    text = "Item 1A. Risk Factors\nWe rely on  “Orica Limited” to supply explosives.\nItem 2. Properties\nCarlin produced 900,000 ounces."
    doc, created = documents.store_document(
        session, url="https://x.example/10k", text=text, kind="filing"
    )
    again, created_again = documents.store_document(
        session, url="https://x.example/10k", text=text, kind="filing"
    )
    assert created and not created_again and again.id == doc.id
    changed, created_changed = documents.store_document(
        session, url="https://x.example/10k", text=text + "!", kind="filing"
    )
    assert created_changed and changed.id != doc.id
    assert documents.verify_quote(doc, 'we rely on "orica limited" to   supply explosives')
    assert not documents.verify_quote(doc, "Orica supplies all explosives we need")
    assert not documents.verify_quote(doc, "Carlin")  # too short to prove anything
    assert [s.text for s in documents.outline(doc)] == [
        "Item 1A. Risk Factors",
        "Item 2. Properties",
    ]
    hit = documents.search(doc, "carlin ounces")
    assert hit and "900,000" in hit[0].text
    assert documents.search(doc, "") == [] and documents.search(doc, "zzz") == []
    assert documents.read_chunk(doc, 5, 10) == doc.text[5:15]


# ------------------------------------------------------------------ connectors
def test_rss_and_atom_parsing_and_xml_bomb_rejected():
    rss = (
        "<rss><channel><item><title>A</title><link>https://a.example/1</link><description>d</description>"
        "<pubDate>Thu, 30 Oct 2025 12:00:00 GMT</pubDate></item><item><title>no link</title></item></channel></rss>"
    )
    items = parse_feed(rss, "Pub", "news")
    assert [(i.title, i.url, i.publisher) for i in items] == [("A", "https://a.example/1", "Pub")]
    assert items[0].published_at.year == 2025
    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>E</title><link href="https://e.example/1"/>'
        "<updated>2025-10-30T12:00:00Z</updated><summary>s</summary></entry></feed>"
    )
    assert parse_feed(atom, "P", "gov")[0].url == "https://e.example/1"
    bomb = '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss><channel><item><title>&b;</title><link>https://x</link></item></channel></rss>'
    assert parse_feed(bomb, "P", "news") == []
    assert parse_feed("<<<garbage", "P", "news") == []


def demo_fetcher():
    return Fetcher(httpx.Client(transport=DemoTransport()), demo_resolver, min_interval_s=0)


def test_gdelt_usgs_and_edgar_via_demo_transport():
    articles = gdelt.search(demo_fetcher(), '"Carlin"')
    assert (
        len(articles) == 2
        and "Carlin" in articles[0].title
        and articles[0].published_at.year == 2025
    )
    quakes = usgs.recent_quakes(demo_fetcher())
    assert {q.event_id for q in quakes} == {"demo-q1", "demo-q2"} and quakes[
        0
    ].lat == pytest.approx(41.6)
    edgar = EdgarClient(demo_fetcher())
    assert edgar.cik_for("NEM") == DEMO_CIKS["NEM"] and edgar.cik_for("nem.to") == DEMO_CIKS["NEM"]
    assert edgar.cik_for("UNKNOWN") is None
    filings = edgar.recent_filings(DEMO_CIKS["NEM"])
    assert [f.form for f in filings] == ["10-K", "8-K"]
    assert (
        filings[0].url.endswith("/900000125000001/demo-10k.htm") or "demo-10k.htm" in filings[0].url
    )
    facts = {f.key: f for f in extract_facts(edgar.facts(DEMO_CIKS["NEM"]))}
    assert facts["shares_outstanding"].value == 55_000_000
    assert facts["net_debt"].value == 6_000_000_000 and "Cash" in facts["net_debt"].concept
    assert extract_facts({}) == []


def test_bad_json_from_connector_is_a_fetch_error():
    bad = Fetcher(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, text="<html>", headers={"content-type": "application/json"}
                )
            )
        ),
        lambda h: ["93.184.216.34"],
        min_interval_s=0,
    )
    for call in (
        lambda: gdelt.search(bad, "x"),
        lambda: usgs.recent_quakes(bad),
        lambda: EdgarClient(bad).cik_for("A"),
    ):
        with pytest.raises(FetchError):
            call()

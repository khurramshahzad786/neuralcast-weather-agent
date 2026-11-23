from reportlab.lib.styles import getSampleStyleSheet

from weather_agent import reports, service


def test_slugify():
    assert reports.slugify("Karachi Storm Watch!") == "karachi-storm-watch"
    assert reports.slugify("   ") == "weather-analysis"


def test_latin1_strips_emoji_keeps_degree():
    assert reports._latin1("Storm ⛈️ 30°C – risk") == "Storm  30°C - risk"


def test_markdown_flowables():
    md = "# Title\n\nSome **bold** text.\n- item 1\n- item 2\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    flows = reports.markdown_to_flowables(md, getSampleStyleSheet())
    assert len(flows) == 6  # heading, paragraph, 2 bullets, 2 table rows (separator dropped)


def test_build_pdf_named_after_analysis(snapshot, tmp_path):
    text = service.auto_summary(snapshot)
    path = reports.build_pdf(snapshot, "Lahore Storm Watch", text, model_name="test", out_dir=tmp_path)
    assert path.parent == tmp_path
    assert path.name.startswith("lahore-storm-watch_") and path.suffix == ".pdf"
    data = path.read_bytes()
    assert data[:5] == b"%PDF-" and len(data) > 10_000
    assert reports.list_reports(tmp_path) == [path]


def test_report_index_search_and_filters(snapshot, tmp_path):
    reports.build_pdf(snapshot, "Lahore Storm Watch", "Severe thunderstorm with hail expected", out_dir=tmp_path)
    entries = reports.load_index(tmp_path)
    assert len(entries) == 1 and entries[0]["city"] == "Lahore" and entries[0]["storm_risk"] == "Severe"
    assert reports.search_reports(entries, "hail")
    assert reports.search_reports(entries, "lahore storm")
    assert not reports.search_reports(entries, "karachi")
    assert reports.search_reports(entries, "", risks=["Severe"])
    assert not reports.search_reports(entries, "", risks=["Low"])
    assert not reports.search_reports(entries, "", city="Quetta")


def test_load_index_includes_pdfs_without_entry(tmp_path):
    (tmp_path / "old-report_20260101-000000.pdf").write_bytes(b"%PDF-1.4")
    entries = reports.load_index(tmp_path)
    assert entries[0]["analysis_name"] == "Old Report" and entries[0]["storm_risk"] == "Unknown"


def test_auto_summary_mentions_key_facts(snapshot):
    text = service.auto_summary(snapshot)
    assert "Severe storm risk" in text
    assert "US AQI 162" in text
    assert "SW" in text

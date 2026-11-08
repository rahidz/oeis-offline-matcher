from html.parser import HTMLParser
from importlib import resources

from oeis_matcher.web import COMMANDS, JSON_COMMANDS


class SearchFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_search = False
        self.flags = {}
        self.rank_options = []
        self.rank_select = False
        self.positional = False
        self.samples = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.in_search = attrs.get("data-command") == "search"
        if not self.in_search:
            return
        if "data-positional" in attrs:
            self.positional = "required" in attrs
        if "data-sample" in attrs:
            self.samples.append(attrs["data-sample"])
        if "data-flag" in attrs:
            self.flags[attrs["data-flag"]] = attrs
        if tag == "select":
            self.rank_select = attrs.get("data-flag") == "--rank"
        if tag == "option" and self.rank_select:
            self.rank_options.append(attrs.get("value"))

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_search = False
        if tag == "select":
            self.rank_select = False


def test_search_form_cli_contract():
    parser = SearchFormParser()
    parser.feed(resources.files("oeis_matcher").joinpath("web_assets/index.html").read_text())
    assert "search" in COMMANDS & JSON_COMMANDS
    assert parser.positional
    assert parser.rank_options == ["balanced", "discovery", "notability"]
    assert set(parser.flags) == {"--rank", "--limit", "--offset", "--db"}
    assert parser.flags["--offset"]["value"] == "0"
    assert {"polyomino", "keyword: more", "1,1,2,3", "*"} <= set(parser.samples)

"""
Web scraping helpers for the offline data-preparation pipeline.

Backend does not import this module. Use it from data_preparation jobs only.
"""

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


def can_fetch(url: str, user_agent: str = "DrKasetBot") -> bool:
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        return True
    return parser.can_fetch(user_agent, url)


def fetch_page_text(url: str, timeout: int = 20) -> str:
    if not can_fetch(url):
        raise PermissionError(f"robots.txt disallows scraping: {url}")
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "DrKasetBot"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)

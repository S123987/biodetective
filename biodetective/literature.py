"""Europe PMC literature retrieval; retrieved records remain unverified candidates."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _clean_article(record: dict[str, Any]) -> dict[str, Any]:
    source = str(record.get("source", "MED"))
    identifier = str(record.get("id", ""))
    pmid = str(record.get("pmid", "")) or (identifier if source == "MED" else "")
    doi = str(record.get("doi", ""))
    if doi:
        url = "https://doi.org/" + doi
    elif pmid:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    else:
        url = f"https://europepmc.org/article/{source}/{identifier}"
    return {
        "source": source,
        "id": identifier,
        "pmid": pmid,
        "doi": doi,
        "title": str(record.get("title", "Untitled record")).strip(),
        "year": str(record.get("firstPublicationDate", ""))[:4] or str(record.get("pubYear", "")),
        "journal": str(record.get("journalTitle", "")),
        "authors": str(record.get("authorString", "")),
        "abstract": str(record.get("abstractText", "")),
        "publication_types": record.get("pubTypeList", {}).get("pubType", []),
        "url": url,
        "retrieved_from": "Europe PMC",
        "access_level": "abstract" if record.get("abstractText") else "metadata only",
    }


def search(query: str, page_size: int = 8, timeout: float = 30) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"query": query, "format": "json", "resultType": "core", "pageSize": min(page_size, 25)}
    )
    request = urllib.request.Request(
        f"{BASE_URL}?{params}",
        headers={"User-Agent": "BioDetective/0.1.0 (local scientific evidence assistant)", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Europe PMC could not be reached: {exc}") from exc
    return [_clean_article(row) for row in payload.get("resultList", {}).get("result", [])]


def search_many(queries: list[str], limit: int = 10) -> tuple[list[dict[str, Any]], list[str]]:
    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    warnings: list[str] = []
    for query in queries[:4]:
        if not query.strip():
            continue
        try:
            for article in search(query, page_size=min(limit, 8)):
                key = article["doi"].lower() or article["pmid"] or f"{article['source']}:{article['id']}"
                if key not in seen:
                    seen.add(key)
                    articles.append(article)
                if len(articles) >= limit:
                    return articles, warnings
        except RuntimeError as exc:
            warnings.append(str(exc))
    return articles, warnings


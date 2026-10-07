"""Public biomedical literature retrieval. Search records are candidates, not verified evidence."""

from __future__ import annotations

import concurrent.futures
import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any


USER_AGENT = "BioDetectiveAI/0.2 (biomedical claim evidence research tool)"


def _get_json(url: str, timeout: float = 22) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _doi(value: Any) -> str:
    result = str(value or "").strip()
    result = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", result, flags=re.I)
    return result.lower()


def _year(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else ""


def _article_key(article: dict[str, Any]) -> str:
    if article.get("doi"):
        return "doi:" + _doi(article["doi"])
    if article.get("pmid"):
        return "pmid:" + str(article["pmid"])
    title = re.sub(r"\W+", "", str(article.get("title", "")).lower())
    return "title:" + title


def _article(
    *,
    title: str,
    year: Any = "",
    journal: str = "",
    authors: str = "",
    doi: Any = "",
    pmid: Any = "",
    abstract: str = "",
    url: str = "",
    source: str = "",
    publication_types: list[str] | None = None,
    citations: Any = None,
) -> dict[str, Any]:
    doi_value = _doi(doi)
    pmid_value = str(pmid or "").strip()
    clean_title = re.sub(r"<[^>]+>", " ", html.unescape(str(title or "Untitled record")))
    clean_title = re.sub(r"\s+", " ", clean_title).strip()
    clean_journal = re.sub(r"<[^>]+>", " ", html.unescape(str(journal or "")))
    clean_authors = re.sub(r"<[^>]+>", " ", html.unescape(str(authors or "")))
    if doi_value:
        canonical_url = "https://doi.org/" + doi_value
    elif pmid_value:
        canonical_url = "https://pubmed.ncbi.nlm.nih.gov/" + pmid_value + "/"
    else:
        canonical_url = url
    return {
        "title": clean_title,
        "year": _year(year),
        "journal": clean_journal.strip(),
        "authors": clean_authors.strip(),
        "doi": doi_value,
        "pmid": pmid_value,
        "abstract": re.sub(r"\s+", " ", html.unescape(str(abstract or ""))).strip(),
        "url": canonical_url,
        "source_catalogs": [source] if source else [],
        "publication_types": publication_types or [],
        "citation_count": citations,
        "access_level": "abstract" if abstract else "metadata only",
    }


def _europe_pmc(query: str, count: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": query, "format": "json", "resultType": "core", "pageSize": count})
    payload = _get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + params)
    records = payload.get("resultList", {}).get("result", [])
    articles: list[dict[str, Any]] = []
    for row in records:
        source = str(row.get("source", "MED"))
        identifier = str(row.get("id", ""))
        pmid = str(row.get("pmid", "")) or (identifier if source == "MED" else "")
        url = f"https://europepmc.org/article/{source}/{identifier}" if identifier else ""
        pub_types = row.get("pubTypeList", {}).get("pubType", [])
        articles.append(
            _article(
                title=row.get("title"),
                year=row.get("firstPublicationDate") or row.get("pubYear"),
                journal=row.get("journalTitle", ""),
                authors=row.get("authorString", ""),
                doi=row.get("doi", ""),
                pmid=pmid,
                abstract=row.get("abstractText", ""),
                url=url,
                source="Europe PMC / PubMed",
                publication_types=pub_types if isinstance(pub_types, list) else [],
            )
        )
    return articles


def _abstract_from_inverted_index(index: Any) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    positioned: list[str] = []
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and 0 <= position < 12000:
                if position >= len(positioned):
                    positioned.extend([""] * (position + 1 - len(positioned)))
                positioned[position] = str(word)
    return " ".join(word for word in positioned if word)


def _openalex(query: str, count: int) -> list[dict[str, Any]]:
    fields = "id,doi,title,publication_year,primary_location,authorships,abstract_inverted_index,type,cited_by_count,open_access"
    params = urllib.parse.urlencode({"search": query, "per-page": count, "select": fields})
    payload = _get_json("https://api.openalex.org/works?" + params)
    articles: list[dict[str, Any]] = []
    for row in payload.get("results", []):
        source = (row.get("primary_location") or {}).get("source") or {}
        authorships = row.get("authorships") or []
        authors = ", ".join(
            str((item.get("author") or {}).get("display_name", ""))
            for item in authorships[:8]
            if (item.get("author") or {}).get("display_name")
        )
        openalex_id = str(row.get("id", ""))
        articles.append(
            _article(
                title=row.get("title"),
                year=row.get("publication_year"),
                journal=source.get("display_name", ""),
                authors=authors,
                doi=row.get("doi", ""),
                abstract=_abstract_from_inverted_index(row.get("abstract_inverted_index")),
                url=openalex_id,
                source="OpenAlex",
                publication_types=[str(row.get("type"))] if row.get("type") else [],
                citations=row.get("cited_by_count"),
            )
        )
    return articles


def _crossref(query: str, count: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query.bibliographic": query, "rows": count})
    payload = _get_json("https://api.crossref.org/works?" + params)
    articles: list[dict[str, Any]] = []
    for row in payload.get("message", {}).get("items", []):
        titles = row.get("title") or []
        authors = ", ".join(
            " ".join(part for part in (item.get("given"), item.get("family")) if part)
            for item in (row.get("author") or [])[:8]
        )
        dates = row.get("published-print") or row.get("published-online") or row.get("created") or {}
        date_parts = dates.get("date-parts") or [[]]
        year = date_parts[0][0] if date_parts and date_parts[0] else ""
        abstract = re.sub(r"<[^>]+>", " ", str(row.get("abstract", "")))
        articles.append(
            _article(
                title=titles[0] if titles else "Untitled record",
                year=year,
                journal=(row.get("container-title") or [""])[0],
                authors=authors,
                doi=row.get("DOI", ""),
                abstract=abstract,
                url=str(row.get("URL", "")),
                source="Crossref",
                publication_types=[str(row.get("type"))] if row.get("type") else [],
            )
        )
    return articles


def _relevance_score(article: dict[str, Any], query_text: str) -> float:
    stop = {
        "does", "do", "did", "what", "how", "why", "when", "where", "which", "the", "and", "with", "from", "into",
        "that", "this", "these", "those", "are", "was", "were", "has", "have", "had", "increase", "increases",
        "decrease", "decreases", "cause", "causes", "effect", "effects", "cells", "cell", "human", "study", "studies",
        "evidence", "claim", "role", "response", "mechanism", "mechanisms", "associated", "association", "among", "using",
    }
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query_text)
    terms = {word.lower() for word in words if word.lower() not in stop}
    title = str(article.get("title", "")).lower()
    abstract = str(article.get("abstract", "")).lower()
    title_tokens = set(re.findall(r"[a-z0-9]+", title))
    abstract_tokens = re.findall(r"[a-z0-9]+", abstract)
    score = sum(4.0 for term in terms if term in title_tokens)
    score += sum(min(2, abstract_tokens.count(term)) * 0.35 for term in terms)
    for raw in words:
        if len(raw) >= 3 and (raw.isupper() or any(char.isdigit() for char in raw)):
            gene = raw.lower()
            aliases = {gene}
            if gene == "tp53":
                aliases.add("p53")
            if gene == "erbb2":
                aliases.add("her2")
            if aliases.intersection(title_tokens):
                score += 4.0
        if raw.lower() == "tp53" and "p53" in title_tokens:
            score += 4.0
    if not article.get("abstract"):
        score -= 2.0
    if any("review" in str(value).lower() for value in article.get("publication_types", [])):
        score -= 2.0
    score += min(0.8, max(0, len(article.get("source_catalogs", [])) - 1) * 0.25)
    year = int(article.get("year") or 0)
    score += min(0.4, max(0, year - 2010) * 0.025)
    return score


def search_literature(queries: list[str], claim: str, limit: int = 18) -> tuple[list[dict[str, Any]], list[str]]:
    clean_queries = [str(query).strip() for query in queries if str(query).strip()][:2]
    if not clean_queries:
        clean_queries = [claim.strip()]
    jobs: list[tuple[str, str]] = []
    for query in clean_queries:
        jobs.extend([(query, "Europe PMC / PubMed"), (query, "OpenAlex"), (query, "Crossref")])

    def run(job: tuple[str, str]) -> tuple[str, list[dict[str, Any]]]:
        query, source = job
        count = 6
        if source == "Europe PMC / PubMed":
            result = _europe_pmc(query, count)
        elif source == "OpenAlex":
            result = _openalex(query, count)
        else:
            result = _crossref(query, count)
        return source, result

    warnings: list[str] = []
    results: list[tuple[str, list[dict[str, Any]]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future, (_, source) in zip(futures, jobs):
            try:
                results.append(future.result())
            except Exception:
                warnings.append(source + " search could not be completed.")

    merged: dict[str, dict[str, Any]] = {}
    for source, articles in results:
        for article in articles:
            key = _article_key(article)
            if key == "title:":
                continue
            previous = merged.get(key)
            if previous is None:
                merged[key] = article
                continue
            catalogs = list(dict.fromkeys(previous["source_catalogs"] + article["source_catalogs"]))
            if len(article.get("abstract", "")) > len(previous.get("abstract", "")):
                for field in ("abstract", "title", "year", "journal", "authors", "publication_types"):
                    if article.get(field):
                        previous[field] = article[field]
            if not previous.get("doi") and article.get("doi"):
                previous["doi"] = article["doi"]
            if not previous.get("pmid") and article.get("pmid"):
                previous["pmid"] = article["pmid"]
            if article.get("citation_count") is not None:
                previous["citation_count"] = article["citation_count"]
            previous["source_catalogs"] = catalogs
            previous["access_level"] = "abstract" if previous.get("abstract") else "metadata only"
            if previous.get("doi"):
                previous["url"] = "https://doi.org/" + previous["doi"]
            elif previous.get("pmid"):
                previous["url"] = "https://pubmed.ncbi.nlm.nih.gov/" + previous["pmid"] + "/"

    articles = list(merged.values())
    query_text = " ".join([claim, *clean_queries])
    articles.sort(
        key=lambda item: (
            -_relevance_score(item, query_text),
            not bool(item.get("abstract")),
            not bool(item.get("doi") or item.get("pmid")),
            -(int(item.get("year") or 0)),
        )
    )
    return articles[:limit], list(dict.fromkeys(warnings))


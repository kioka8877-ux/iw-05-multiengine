"""
IW-05 MultiEngine — Google + Bing + DuckDuckGo en parallèle
Iron Warrior #5 — Couverture maximale, 1 appel.
Attaque : SerpApi (généraliste $20+/10K)
"""
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import sys
sys.path.insert(0, '/home/user/iron_warriors/shared')
from base import (
    create_app, fetch_html, SearchResult, SERPResponse,
    clean_text, get_timestamp, measure_latency
)
import time
import asyncio

app = create_app("IW-05 MultiEngine", "Google + Bing + DuckDuckGo en parallèle — couverture maximale")

class MultiResult(BaseModel):
    query: str
    engines: List[str]
    results: dict  # {engine: [SearchResult]}
    total_unique: int
    timestamp: str
    latency_ms: int

async def _google(q: str, num: int, gl: str, hl: str) -> List[SearchResult]:
    url = f"https://www.google.com/search?q={quote_plus(q)}&num={num}&gl={gl}&hl={hl}"
    try:
        html = await fetch_html(url)
    except:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    seen = set()
    for div in soup.find_all('div', class_='g'):
        h3 = div.find('h3')
        link = div.find('a', href=True)
        snippet_tag = div.find('div', class_='VwiC3b')
        if h3 and link:
            href = link['href']
            if href.startswith('/url?q='):
                href = href.split('/url?q=')[1].split('&')[0]
            if href in seen or not href.startswith('http'):
                continue
            seen.add(href)
            results.append(SearchResult(
                title=clean_text(h3.get_text()), url=href,
                snippet=clean_text(snippet_tag.get_text()) if snippet_tag else "",
                position=len(results) + 1,
            ))
            if len(results) >= num:
                break
    return results

async def _bing(q: str, num: int, cc: str, lang: str) -> List[SearchResult]:
    url = f"https://www.bing.com/search?q={quote_plus(q)}&count={num}&cc={cc}&setlang={lang}"
    try:
        html = await fetch_html(url)
    except:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    seen = set()
    for li in soup.find_all('li', class_='b_algo'):
        h2 = li.find('h2')
        link = h2.find('a', href=True) if h2 else None
        snippet_tag = li.find('p')
        if h2 and link:
            href = link['href']
            if href in seen or not href.startswith('http'):
                continue
            seen.add(href)
            results.append(SearchResult(
                title=clean_text(h2.get_text()), url=href,
                snippet=clean_text(snippet_tag.get_text()) if snippet_tag else "",
                position=len(results) + 1,
            ))
            if len(results) >= num:
                break
    return results

async def _ddg(q: str, num: int, region: str) -> List[SearchResult]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}&kl={region}"
    try:
        html = await fetch_html(url)
    except:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    seen = set()
    for div in soup.find_all('div', class_='result'):
        title_tag = div.find('a', class_='result__a')
        snippet_tag = div.find('a', class_='result__snippet')
        if title_tag and title_tag.get('href'):
            href = title_tag['href']
            if 'uddg=' in href:
                from urllib.parse import parse_qs, urlparse
                params = parse_qs(urlparse(href).query)
                href = params.get('uddg', [href])[0]
            if href in seen:
                continue
            seen.add(href)
            results.append(SearchResult(
                title=clean_text(title_tag.get_text()), url=href,
                snippet=clean_text(snippet_tag.get_text()) if snippet_tag else "",
                position=len(results) + 1,
            ))
            if len(results) >= num:
                break
    return results

@app.get("/search", response_model=MultiResult)
async def multi_search(
    q: str = Query(..., description="Search query"),
    num: int = Query(10, ge=1, le=30),
    engines: str = Query("google,bing,duckduckgo", description="Comma-separated engines"),
    gl: str = Query("us"),
    hl: str = Query("en"),
):
    start = time.time()
    engine_list = [e.strip() for e in engines.split(",")]
    tasks = {}
    if "google" in engine_list:
        tasks["google"] = _google(q, num, gl, hl)
    if "bing" in engine_list:
        tasks["bing"] = _bing(q, num, gl, hl)
    if "duckduckgo" in engine_list:
        tasks["duckduckgo"] = _ddg(q, num, "wt-wt")

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    engine_results = {}
    all_urls = set()
    for engine, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            engine_results[engine] = []
        else:
            engine_results[engine] = [r.dict() for r in result]
            for r in result:
                all_urls.add(r.url)

    return MultiResult(
        query=q, engines=list(tasks.keys()),
        results=engine_results, total_unique=len(all_urls),
        timestamp=get_timestamp(), latency_ms=measure_latency(start),
    )

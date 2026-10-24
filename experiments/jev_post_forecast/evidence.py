"""Yahoo/CVM collection and leakage-safe historical case selection."""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

from src.candles import YahooB3CandleClient
from src.database import normalize_ticker, parse_iso

from .storage import JsonCache, stable_hash


CVM_IPE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
RELEVANT_TERMS = (
    "fato relevante",
    "comunicado ao mercado",
    "informacoes trimestrais",
    "demonstracoes financeiras",
    "dados economico-financeiros",
)
MAX_DOCUMENTS = 12
MAX_TOTAL_CHARS = 24_000
MAX_DOCUMENT_CHARS = 8_000


def parse_datetime(value: Any) -> datetime | None:
    parsed = parse_iso(str(value)) if value not in (None, "") else None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).lower().split())


def is_relevant_disclosure(record: dict[str, Any]) -> bool:
    haystack = normalize_text(" ".join(str(record.get(key, "")) for key in ("Categoria", "Tipo", "Especie", "Assunto")))
    return any(term in haystack for term in RELEVANT_TERMS)


def disclosure_time(record: dict[str, Any]) -> datetime | None:
    return parse_datetime(record.get("Data_Entrega"))


def select_historical_cases(
    candles: list[dict[str, Any]],
    disclosures: list[dict[str, Any]],
    *,
    horizon: int,
    count: int = 2,
    minimum_context: int = 90,
) -> list[dict[str, Any]]:
    """Choose recent disclosures with a cutoff strictly after delivery and enough future candles."""
    ordered_candles = sorted(candles, key=lambda row: str(row["timestamp"]))
    candle_times = [parse_datetime(row["timestamp"]) for row in ordered_candles]
    selected: list[dict[str, Any]] = []
    candidates = sorted(
        (record for record in disclosures if is_relevant_disclosure(record) and disclosure_time(record)),
        key=lambda record: (disclosure_time(record) or datetime.min.replace(tzinfo=UTC), str(record.get("Protocolo_Entrega", ""))),
        reverse=True,
    )
    seen_disclosures: set[str] = set()
    for record in candidates:
        delivered = disclosure_time(record)
        assert delivered is not None
        # A daily candle represents that trading day's close. Use the first close on a later date.
        cutoff_index = next(
            (
                index
                for index, timestamp in enumerate(candle_times)
                if timestamp is not None and timestamp.date() > delivered.date()
            ),
            None,
        )
        if cutoff_index is None or cutoff_index + horizon >= len(ordered_candles):
            continue
        disclosure_identity = normalize_text(
            record.get("Link_Download")
            or "|".join(
                str(record.get(key, ""))
                for key in ("Data_Entrega", "Categoria", "Tipo", "Especie", "Assunto")
            )
        )
        if cutoff_index + 1 < minimum_context or disclosure_identity in seen_disclosures:
            continue
        future = ordered_candles[cutoff_index + 1 : cutoff_index + 1 + horizon]
        if len(future) != horizon:
            continue
        selected.append(
            {
                "disclosure": record,
                "delivered_at": delivered.isoformat(),
                "cutoff_index": cutoff_index,
                "cutoff": ordered_candles[cutoff_index]["timestamp"],
                "context": ordered_candles[: cutoff_index + 1],
                "realized": future,
            }
        )
        seen_disclosures.add(disclosure_identity)
        if len(selected) == count:
            break
    return selected


def enforce_evidence_limits(documents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    remaining = MAX_TOTAL_CHARS
    for document in documents:
        identity = normalize_text(document.get("url") or document.get("title") or document.get("subject"))
        if not identity or identity in seen or remaining <= 0 or len(result) >= MAX_DOCUMENTS:
            continue
        seen.add(identity)
        copy = dict(document)
        content = str(copy.get("content") or copy.get("excerpt") or "")[:MAX_DOCUMENT_CHARS]
        content = content[:remaining]
        copy["content"] = content
        copy["character_count"] = len(content)
        remaining -= len(content)
        result.append(copy)
    return result


def evidence_state(
    documents: list[dict[str, Any]],
    ticker: str,
    as_of: str,
    case_kind: str,
    horizon: int = 10,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "analysis_cutoff": as_of,
        "case_kind": case_kind,
        "forecast_horizon_candles": horizon,
        "language_note": "Evidence may be in Portuguese; interpret it without translating or inventing facts.",
        "documents": [
            {
                "source": item.get("source"),
                "published_at": item.get("published_at"),
                "title": item.get("title"),
                "publisher": item.get("publisher"),
                "category": item.get("category"),
                "subject": item.get("subject"),
                "url": item.get("url"),
                "content_mode": item.get("content_mode"),
                "content": item.get("content"),
            }
            for item in documents
        ],
    }


class EvidenceCollector:
    def __init__(self, cache: JsonCache, issuer_map_path: Path | None = None):
        self.cache = cache
        path = issuer_map_path or Path(__file__).with_name("issuer_map.json")
        self.issuers = json.loads(path.read_text(encoding="utf-8"))
        self.candle_client = YahooB3CandleClient()

    def candles(self, ticker: str) -> list[dict[str, Any]]:
        ticker = normalize_ticker(ticker)
        key = {"ticker": ticker, "interval": "1d", "range": "5y"}
        cached = self.cache.get("yahoo-candles", key)
        if cached:
            return list(cached["candles"])
        if self.cache.offline:
            return list(self.cache.require("yahoo-candles", key)["candles"])
        candles = self.candle_client.fetch(ticker, interval="1d", range_name="5y")
        self.cache.put("yahoo-candles", key, {"fetched_at": _now(), "candles": candles})
        return candles

    def yahoo_news(self, ticker: str, limit: int = 6) -> list[dict[str, Any]]:
        ticker = normalize_ticker(ticker)
        key = {"ticker": ticker, "limit": limit, "source": "yahoo-search-v1"}
        cached = self.cache.get("yahoo-news", key)
        if cached:
            return list(cached["documents"])
        if self.cache.offline:
            return list(self.cache.require("yahoo-news", key)["documents"])
        response = requests.get(
            YAHOO_SEARCH_URL,
            params={"q": f"{ticker}.SA", "quotesCount": 0, "newsCount": limit, "listsCount": 0},
            headers={"User-Agent": "trade-alert-jev-experiment/1.0"},
            timeout=15,
        )
        response.raise_for_status()
        documents: list[dict[str, Any]] = []
        for item in response.json().get("news", [])[:limit]:
            timestamp = item.get("providerPublishTime")
            published = datetime.fromtimestamp(timestamp, tz=UTC).isoformat() if timestamp else None
            title = str(item.get("title") or "")
            click_through = item.get("clickThroughUrl") or {}
            documents.append(
                {
                    "source": "Yahoo",
                    "published_at": published,
                    "title": title,
                    "publisher": item.get("publisher"),
                    "url": item.get("link") or click_through.get("url"),
                    "content": title,
                    "excerpt": title,
                    "content_mode": "metadata",
                }
            )
        self.cache.put("yahoo-news", key, {"fetched_at": _now(), "documents": documents})
        return documents

    def cvm_records(self, ticker: str, years: Iterable[int]) -> list[dict[str, Any]]:
        ticker = normalize_ticker(ticker)
        issuer = self.issuers.get(ticker)
        if not issuer:
            raise ValueError(f"No experimental CVM issuer mapping for {ticker}")
        cnpj = normalize_text(issuer["cnpj"]).replace(".", "").replace("/", "").replace("-", "")
        records: list[dict[str, Any]] = []
        for year in sorted(set(int(value) for value in years), reverse=True):
            key = {"year": year, "ticker": ticker, "cnpj": issuer["cnpj"]}
            cached = self.cache.get("cvm-index", key)
            if cached:
                records.extend(cached["records"])
                continue
            archive_path = self.cache.root / "cvm-archives" / f"ipe_cia_aberta_{year}.zip"
            if self.cache.offline and not archive_path.exists():
                raise FileNotFoundError(f"Offline CVM archive cache miss for {year}")
            if self.cache.refresh or not archive_path.exists():
                if self.cache.offline:
                    raise FileNotFoundError(f"Offline CVM archive cache miss for {year}")
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                response = requests.get(CVM_IPE_URL.format(year=year), timeout=45)
                response.raise_for_status()
                temporary = archive_path.with_suffix(".zip.tmp")
                temporary.write_bytes(response.content)
                temporary.replace(archive_path)
            matches = _read_cvm_archive(archive_path, cnpj)
            self.cache.put("cvm-index", key, {"fetched_at": _now(), "records": matches})
            records.extend(matches)
        return records

    def cvm_documents(self, records: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for record in sorted(records, key=lambda item: str(item.get("Data_Entrega", "")), reverse=True)[:limit]:
            url = str(record.get("Link_Download") or "")
            metadata = " | ".join(
                str(record.get(key) or "") for key in ("Categoria", "Tipo", "Especie", "Assunto")
            ).strip(" |")
            content, mode = metadata, "metadata"
            if url:
                try:
                    content = self._document_text(url) or metadata
                    mode = "full_text" if content != metadata else "metadata"
                except Exception:
                    content, mode = metadata, "metadata"
            documents.append(
                {
                    "source": "CVM",
                    "published_at": record.get("Data_Entrega"),
                    "title": record.get("Especie") or record.get("Categoria") or "CVM disclosure",
                    "publisher": record.get("Nome_Companhia"),
                    "category": record.get("Categoria"),
                    "subject": record.get("Assunto"),
                    "url": url or None,
                    "content": content,
                    "excerpt": content[:500],
                    "content_mode": mode,
                    "protocol": record.get("Protocolo_Entrega"),
                }
            )
        return documents

    def _document_text(self, url: str) -> str:
        key = {"url": url}
        cached = self.cache.get("cvm-document-text", key)
        if cached:
            return str(cached.get("text") or "")
        if self.cache.offline:
            return str(self.cache.require("cvm-document-text", key).get("text") or "")
        response = requests.get(url, headers={"User-Agent": "trade-alert-jev-experiment/1.0"}, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "pdf" in content_type or response.content.startswith(b"%PDF"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(response.content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            response.encoding = response.encoding or "utf-8"
            text = BeautifulSoup(response.text, "html5lib").get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()[:MAX_DOCUMENT_CHARS]
        self.cache.put("cvm-document-text", key, {"fetched_at": _now(), "url_hash": stable_hash(url), "text": text})
        return text


def _read_cvm_archive(path: Path, normalized_cnpj: str) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        csv_name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        raw = archive.read(csv_name)
    text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    matches: list[dict[str, Any]] = []
    for row in reader:
        row_cnpj = normalize_text(row.get("CNPJ_Companhia")).replace(".", "").replace("/", "").replace("-", "")
        if row_cnpj == normalized_cnpj:
            matches.append({str(key): value for key, value in row.items()})
    return matches


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()

#!/usr/bin/env python3
"""
etsy_research.py — Standalone Etsy Scraper and Market Intelligence Engine
Part of badem-rank Agensi Skill.

Fetches public search listings for a keyword, extracts prices, tags, reviews,
calculates market statistics, and computes deltas against previous snapshots.
"""

import argparse
import json
import logging
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

try:
    from fake_useragent import UserAgent
    ua = UserAgent()
    def get_user_agent() -> str:
        return ua.random
except Exception:
    def get_user_agent() -> str:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etsy_research")

BASE_URL = "https://www.etsy.com/search"

def extract_price(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", text).strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None

def extract_number(text: str) -> int:
    if not text:
        return 0
    clean = re.sub(r"[^\d]", "", text)
    return int(clean) if clean else 0

def fetch_page(keyword: str, page: int = 1) -> str:
    headers = {
        "User-Agent": get_user_agent(),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.etsy.com/",
    }
    params = {"q": keyword, "page": page, "ref": "pagination"}
    logger.info(f"Fetching Etsy page {page} for '{keyword}'...")
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        res = client.get(BASE_URL, headers=headers, params=params)
        res.raise_for_status()
        return res.text

def parse_listings(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    cards = soup.select(".wt-grid__item-xs-6, .v2-listing-card, [data-listing-id]")
    
    for card in cards:
        listing_id = card.get("data-listing-id") or card.get("data-palette-listing-id")
        
        # Link & Title
        title_tag = card.select_one("h3, h2, .v2-listing-card__title, .wt-text-caption")
        title = title_tag.get_text(strip=True) if title_tag else ""
        link_tag = card.select_one("a.listing-link, a[href*='/listing/']")
        link = link_tag.get("href", "") if link_tag else ""
        
        if not listing_id and link:
            match = re.search(r"/listing/(\d+)", link)
            if match:
                listing_id = match.group(1)
                
        if not listing_id or not title:
            continue

        # Price
        price_tag = card.select_one(".currency-value, .wt-text-title-01, .n-e5x3k")
        price_val = extract_price(price_tag.get_text()) if price_tag else None

        # Reviews
        review_tag = card.select_one(".wt-text-body-01, .wt-text-caption, span[aria-label*='reviews']")
        review_text = review_tag.get_text() if review_tag else ""
        reviews = extract_number(review_text) if ("(" in review_text or "review" in review_text.lower()) else 0

        # Star Seller
        star_seller = bool(card.select_one("[aria-label*='Star Seller'], .wt-badge--star-seller"))

        # Shop Name
        shop_tag = card.select_one(".wt-text-caption-title, .v2-listing-card__shop")
        shop_name = shop_tag.get_text(strip=True) if shop_tag else "Unknown Shop"

        # Image
        img_tag = card.select_one("img")
        img_url = img_tag.get("src") or img_tag.get("data-src") if img_tag else ""

        items.append({
            "listing_id": str(listing_id),
            "title": title,
            "price": price_val,
            "reviews": reviews,
            "star_seller": star_seller,
            "shop_name": shop_name,
            "url": link.split("?")[0] if link else f"https://www.etsy.com/listing/{listing_id}",
            "img_url": img_url,
        })
        
    return items

def analyze_market(listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    prices = [item["price"] for item in listings if item.get("price")]
    if not prices:
        return {"error": "No priced listings found"}

    prices.sort()
    avg_price = sum(prices) / len(prices)
    median_price = prices[len(prices) // 2]
    min_price = min(prices)
    max_price = max(prices)
    
    star_sellers = sum(1 for item in listings if item.get("star_seller"))
    total_reviews = sum(item.get("reviews", 0) for item in listings)

    # Word / Tag Frequency Analysis from Titles
    stopwords = {"and", "for", "the", "with", "in", "a", "of", "to", "&", "-", "|", "gift", "gifts"}
    word_freq = {}
    for item in listings:
        words = re.findall(r"\b[a-zA-ZğüşıöçĞÜŞİÖÇ]{3,}\b", item["title"].lower())
        for w in words:
            if w not in stopwords:
                word_freq[w] = word_freq.get(w, 0) + 1

    top_tags = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        "total_listings_analyzed": len(listings),
        "price_stats": {
            "average": round(avg_price, 2),
            "median": round(median_price, 2),
            "min": round(min_price, 2),
            "max": round(max_price, 2),
        },
        "competition": {
            "star_seller_count": star_sellers,
            "star_seller_ratio_pct": round((star_sellers / len(listings)) * 100, 1) if listings else 0,
            "avg_reviews_per_listing": round(total_reviews / len(listings), 1) if listings else 0,
        },
        "top_keywords_and_tags": [{"tag": tag, "frequency": count} for tag, count in top_tags],
    }

def compute_delta(current_listings: List[Dict[str, Any]], prev_listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    prev_map = {item["listing_id"]: item for item in prev_listings}
    deltas = []
    
    for curr in current_listings:
        lid = curr["listing_id"]
        if lid in prev_map:
            prev = prev_map[lid]
            rev_diff = curr.get("reviews", 0) - prev.get("reviews", 0)
            if rev_diff > 0:
                deltas.append({
                    "listing_id": lid,
                    "title": curr["title"],
                    "shop_name": curr["shop_name"],
                    "price": curr["price"],
                    "new_reviews": rev_diff,
                    "estimated_daily_sales": rev_diff * 15, # Industry heuristic: 1 review ~ 15 sales
                    "url": curr["url"],
                })

    deltas.sort(key=lambda x: x["new_reviews"], reverse=True)
    return {
        "matched_listings_count": len(prev_map),
        "growing_listings": deltas[:10],
        "top_velocity_listing": deltas[0] if deltas else None,
    }

def main():
    parser = argparse.ArgumentParser(description="Etsy Market Research & Delta Engine")
    parser.add_argument("--keyword", required=True, help="Keyword to search on Etsy")
    parser.add_argument("--pages", type=int, default=2, help="Number of search pages (default: 2)")
    parser.add_argument("--output", type=str, default="", help="Output JSON path")
    args = parser.parse_args()

    slug = re.sub(r"[^\w]", "_", args.keyword.lower())
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    output_path = Path(args.output) if args.output else data_dir / f"snapshot_{slug}.json"
    
    # Load previous snapshot if exists
    prev_snapshot = None
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                prev_snapshot = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read previous snapshot: {e}")

    # Scrape pages
    all_listings = []
    seen_ids = set()
    for page in range(1, args.pages + 1):
        try:
            html = fetch_page(args.keyword, page=page)
            page_listings = parse_listings(html)
            for item in page_listings:
                if item["listing_id"] not in seen_ids:
                    seen_ids.add(item["listing_id"])
                    all_listings.append(item)
            if page < args.pages:
                time.sleep(random.uniform(2.0, 4.0))
        except Exception as e:
            logger.error(f"Error scraping page {page}: {e}")
            break

    if not all_listings:
        print(json.dumps({"error": f"No listings scraped for keyword '{args.keyword}'"}))
        sys.exit(1)

    analysis = analyze_market(all_listings)
    
    delta_data = None
    if prev_snapshot and "listings" in prev_snapshot:
        delta_data = compute_delta(all_listings, prev_snapshot["listings"])

    final_payload = {
        "keyword": args.keyword,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "market_analysis": analysis,
        "sales_delta": delta_data,
        "top_listings": sorted(all_listings, key=lambda x: x.get("reviews", 0), reverse=True)[:15],
        "listings": all_listings,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)

    logger.info(f"Snapshot saved to {output_path}")

    # Print summary to stdout for agent consumption
    print(json.dumps({
        "status": "success",
        "keyword": args.keyword,
        "total_analyzed": len(all_listings),
        "price_stats": analysis["price_stats"],
        "competition": analysis["competition"],
        "top_tags": analysis["top_keywords_and_tags"][:8],
        "delta_velocity": delta_data["growing_listings"][:3] if delta_data else "No previous baseline snapshot found. Run again tomorrow for delta analysis.",
        "saved_to": str(output_path)
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

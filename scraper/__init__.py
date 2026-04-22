"""
链家租房数据爬虫 - 模块化包

使用: python -m scraper.pipeline --areas all
"""

from scraper.config import REGIONS, ALL_REGIONS, OUTPUT_DIR
from scraper.utils import setup_logging
from scraper.retry import error_log
from scraper.scraper_core import scrape_with_browser, scrape_with_agent
from scraper.storage import save_results, enrich_with_geo
from scraper.analyzer import analyze_listings
from scraper.map_generator import (
    build_community_stats,
    generate_static_map,
    generate_html_map,
    print_distance_report,
)
from scraper.geo import get_geocoder, geocode_community
from scraper.captcha import wait_for_captcha_or_login

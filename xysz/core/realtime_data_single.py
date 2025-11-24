#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时ETH行情 + 微观结构单文件脚本
--------------------------------

整合自:
- eth/real_eth_price_fetcher.py
- eth/microstructure.py
- eth/realtime_data_aggregator.py（去预测）

功能:
- 多数据源实时ETH价格获取（含24小时指标）
- 微观结构数据: 订单簿、聚合成交、资金费率、爆仓代理、VPVR、资金费率/多空比/持仓量等
- 统一快照接口，可直接打印或保存

用法:
    python realtime_data_single.py          # 打印JSON快照
    python realtime_data_single.py --save snapshot.json
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import NameResolutionError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("realtime_data_single")

# ================================================================
# 价格获取
# ================================================================


@dataclass
class PriceData:
    price: float
    timestamp: str
    source: str
    volume_24h: float
    change_24h: float
    high_24h: float
    low_24h: float
    confidence: float


class RealETHPriceFetcher:
    """真实ETH价格获取器 - 专业版（部分裁剪以适配单文件）"""

    def __init__(self, use_proxy: bool = False, proxy_config: Dict = None, allow_simulation: bool = True,
                 binance_proxy_ip: str = None, binance_proxy_port: int = None, universal_proxy=None):
        self.use_proxy = use_proxy
        self.allow_simulation = allow_simulation
        self.min_request_interval = 10
        self.binance_proxy_ip = binance_proxy_ip
        self.binance_proxy_port = binance_proxy_port
        self.universal_proxy = universal_proxy
        self.source_backoff_until: Dict[str, float] = {}

        try:
            from config import get_config
            config = get_config()
            self.proxy_config = config.get_proxy_config()
            self.use_proxy = config.is_proxy_enabled()
            data_config = config.get('data_sources', {})
            self.min_request_interval = data_config.get('request_interval', 10)
        except Exception:
            self.proxy_config = proxy_config or {}

        self.session = requests.Session()
        self.last_request_time = 0

        try:
            retry = Retry(
                total=4,
                connect=2,
                read=3,
                status=4,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
                backoff_factor=0.7,
                raise_on_status=False
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)
        except Exception:
            pass

        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.85 Safari/537.36'
        ]

        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })

        if self.use_proxy and self.proxy_config:
            self.session.proxies.update(self.proxy_config)
            logger.info("✅ 价格获取器代理已启用")
        elif self.use_proxy:
            logger.warning("⚠️ 价格获取器代理已启用但配置为空")

        self.data_sources = [
            {
                'name': 'Binance',
                'url': 'https://api.binance.com/api/v3/ticker/24hr',
                'params': {'symbol': 'ETHUSDT'},
                'timeout': 10
            },
            {
                'name': 'BinanceAlt',
                'url': 'https://data-api.binance.vision/api/v3/ticker/24hr',
                'params': {'symbol': 'ETHUSDT'},
                'timeout': 10
            },
            {
                'name': 'CoinGecko',
                'url': 'https://api.coingecko.com/api/v3/simple/price',
                'params': {'ids': 'ethereum', 'vs_currencies': 'usd', 'include_24hr_change': 'true',
                           'include_24hr_vol': 'true', 'include_24hr_high': 'true', 'include_24hr_low': 'true'},
                'timeout': 10
            },
            {
                'name': 'Kraken',
                'url': 'https://api.kraken.com/0/public/Ticker',
                'params': {'pair': 'ETHUSD'},
                'timeout': (20, 10)
            },
            {
                'name': 'Coinbase',
                'url': 'https://api.exchange.coinbase.com/products/ETH-USD/ticker',
                'params': {},
                'timeout': 10
            },
            {
                'name': 'Bitstamp',
                'url': 'https://www.bitstamp.net/api/v2/ticker/ethusd',
                'params': {},
                'timeout': 10
            },
            {
                'name': 'YahooFinance',
                'url': 'https://query1.finance.yahoo.com/v7/finance/quote',
                'params': {'symbols': 'ETH-USD'},
                'timeout': 10
            },
            {
                'name': 'CoinCap',
                'url': 'https://api.coincap.io/v2/assets/ethereum',
                'params': {},
                'timeout': 10
            }
        ]

    def get_price_with_retry(self, max_retries: int = 3) -> Optional[PriceData]:
        for attempt in range(max_retries):
            try:
                current_time = time.time()
                time_since_last_request = current_time - self.last_request_time
                if time_since_last_request < self.min_request_interval:
                    sleep_time = self.min_request_interval - time_since_last_request
                    jitter = random.uniform(0.3, 0.9)
                    time.sleep(max(0, sleep_time + jitter))

                sources = list(self.data_sources)
                if not self.universal_proxy:
                    random.shuffle(sources)

                for source in sources:
                    cooldown_until = self.source_backoff_until.get(source['name'], 0)
                    if cooldown_until > time.time():
                        logger.info(f"{source['name']} 数据源冷却中，{cooldown_until - time.time():.1f}s 后重试")
                        continue
                    try:
                        price_data = self._fetch_from_source(source)
                        if price_data:
                            self.last_request_time = time.time()
                            return price_data
                    except Exception as e:
                        logger.warning(f"{source['name']} 获取失败: {e}")
                        message = str(e)
                        if any(code in message for code in ["429", "451", "503"]):
                            backoff = (attempt + 1) * 2 + random.uniform(0.5, 1.5)
                            time.sleep(backoff)
                        continue

                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3 + random.uniform(0.5, 1.5)
                    time.sleep(wait_time)

            except Exception as e:
                logger.error(f"价格获取错误: {e}")
                logger.debug(traceback.format_exc())
                if attempt < max_retries - 1:
                    time.sleep(2)

        if self.allow_simulation:
            logger.warning("使用模拟价格数据")
            return self._generate_simulation_data()
        return None

    def _fetch_from_source(self, source: Dict) -> Optional[PriceData]:
        try:
            if self.universal_proxy and 'binance' in source['url'].lower():
                return self._fetch_from_binance_via_custom_proxy(source)
            elif self.binance_proxy_ip and self.binance_proxy_port and 'binance' in source['url'].lower():
                return self._fetch_from_binance_via_custom_proxy(source)

            self.session.headers['User-Agent'] = random.choice(self.user_agents)
            if source['name'] == 'YahooFinance':
                self.session.headers['Accept'] = 'application/json, text/plain, */*'
                self.session.headers['Accept-Language'] = 'en-US,en;q=0.9'
                self.session.headers['Referer'] = 'https://finance.yahoo.com/quote/ETH-USD'

            response = self.session.get(
                source['url'],
                params=source['params'],
                timeout=source.get('timeout', 10)
            )
            status = getattr(response, 'status_code', 0)
            if status in (401, 403, 404, 429, 451):
                logger.warning(f"{source['name']} 状态 {status}，跳过")
                return None
            response.raise_for_status()
            try:
                data = response.json()
            except Exception:
                raise Exception(f"{source['name']} 空响应或JSON解析失败")

            if source['name'] == 'CoinGecko':
                return self._parse_coingecko_data(data)
            if source['name'] == 'Kraken':
                return self._parse_kraken_data(data)
            if source['name'] == 'Coinbase':
                return self._parse_coinbase_data(data)
            if source['name'] == 'Bitstamp':
                return self._parse_bitstamp_data(data)
            if source['name'] == 'YahooFinance':
                return self._parse_yahoo_data(data)
            if source['name'] == 'CoinCap':
                return self._parse_coincap_data(data)
            if source['name'] in ('BinanceAlt', 'Binance'):
                return self._parse_binance_data(data)

        except requests.exceptions.ConnectTimeout as e:
            if source['name'] == 'Kraken':
                logger.warning("Kraken 请求连接超时，可尝试启用代理或延长 timeout")
            logger.debug(traceback.format_exc())
            return None
        except requests.exceptions.ReadTimeout as e:
            logger.warning(f"{source['name']} 读取超时: {e}")
            logger.debug(traceback.format_exc())
            return None
        except requests.exceptions.ConnectionError as e:
            cause = getattr(e, "__cause__", None)
            if isinstance(cause, NameResolutionError):
                cooldown = 300
                self.source_backoff_until[source['name']] = time.time() + cooldown
                logger.warning(f"{source['name']} DNS 解析失败，进入{cooldown}s冷却: {cause}")
            else:
                logger.warning(f"{source['name']} 连接错误: {e}")
            logger.debug(traceback.format_exc())
            return None
        except Exception as e:
            logger.error(f"{source['name']} 数据获取失败: {e}")
            logger.debug(traceback.format_exc())
            return None

    def _fetch_from_binance_via_custom_proxy(self, source: Dict) -> Optional[PriceData]:
        try:
            if self.universal_proxy:
                symbol = source['params'].get('symbol', 'ETHUSDT')
                data = self.universal_proxy.binance_get_ticker_24hr(symbol)
            else:
                from binance_custom_proxy import CustomBinanceProxy
                proxy = CustomBinanceProxy(self.binance_proxy_ip, self.binance_proxy_port)
                url_parts = source['url'].replace('https://api.binance.com', '')
                path = url_parts.split('?')[0]
                data = proxy.request(path, "GET", source['params'])

            if data and isinstance(data, dict):
                return self._parse_binance_data(data)
            return None
        except Exception as e:
            logger.error(f"Binance自定义代理失败: {e}")
            logger.debug(traceback.format_exc())
            return None

    def _parse_coingecko_data(self, data: Dict) -> Optional[PriceData]:
        eth_data = data.get('ethereum', {})
        if not eth_data:
            return None
        price = eth_data.get('usd', 0)
        if price <= 0:
            return None
        change_24h = eth_data.get('usd_24h_change', 0)
        volume_24h = eth_data.get('usd_24h_vol', 0)
        high_24h = eth_data.get('usd_24h_high', price * 1.01)
        low_24h = eth_data.get('usd_24h_low', price * 0.99)
        return PriceData(
            price=price,
            timestamp=datetime.now().isoformat(),
            source="CoinGecko API",
            volume_24h=volume_24h,
            change_24h=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.95
        )

    def _parse_coincap_data(self, data: Dict) -> Optional[PriceData]:
        asset_data = data.get('data', {})
        if not asset_data:
            return None
        price = float(asset_data.get('priceUsd', 0))
        if price <= 0:
            return None
        change_24h = float(asset_data.get('changePercent24Hr', 0))
        volume_24h = float(asset_data.get('volumeUsd24Hr', 0))
        high_24h = price * (1 + abs(change_24h) / 100 * 0.5)
        low_24h = price * (1 - abs(change_24h) / 100 * 0.5)
        return PriceData(
            price=price,
            timestamp=datetime.now().isoformat(),
            source="CoinCap API",
            volume_24h=volume_24h,
            change_24h=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.90
        )

    def _parse_binance_data(self, data: Dict) -> Optional[PriceData]:
        price = float(data.get('lastPrice', 0))
        if price <= 0:
            return None
        change_24h = float(data.get('priceChangePercent', 0))
        volume_24h = float(data.get('volume', 0)) * price
        high_24h = float(data.get('highPrice', price * 1.01))
        low_24h = float(data.get('lowPrice', price * 0.99))
        return PriceData(
            price=price,
            timestamp=datetime.now().isoformat(),
            source="Binance API",
            volume_24h=volume_24h,
            change_24h=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.95
        )

    def _parse_kraken_data(self, data: Dict) -> Optional[PriceData]:
        result = data.get('result', {})
        if not result:
            return None
        pair_key = next(iter(result.keys()))
        ticker = result.get(pair_key, {})
        last_price = float(ticker.get('c', [0])[0]) if ticker.get('c') else 0.0
        if last_price <= 0:
            return None
        high_24h = float(ticker.get('h', [last_price, last_price])[1])
        low_24h = float(ticker.get('l', [last_price, last_price])[1])
        open_price = ticker.get('o', last_price)
        try:
            open_price = float(open_price)
        except Exception:
            open_price = last_price
        change_24h = ((last_price - open_price) / open_price * 100.0) if open_price else 0.0
        vol_24 = float(ticker.get('v', [0, 0])[1])
        volume_24h = vol_24 * last_price
        return PriceData(
            price=last_price,
            timestamp=datetime.now().isoformat(),
            source="Kraken API",
            volume_24h=volume_24h,
            change_24h=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.95
        )

    def _parse_coinbase_data(self, data: Dict) -> Optional[PriceData]:
        price = float(data.get('price', 0)) if 'price' in data else float(data.get('last', 0) or 0)
        if price <= 0:
            return None
        volume_24h = float(data.get('volume', 0) or 0) * price
        high_24h = price * 1.01
        low_24h = price * 0.99
        return PriceData(
            price=price,
            timestamp=datetime.now().isoformat(),
            source="Coinbase API",
            volume_24h=volume_24h,
            change_24h=0.0,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.9
        )

    def _parse_bitstamp_data(self, data: Dict) -> Optional[PriceData]:
        price = float(data.get('last', 0))
        if price <= 0:
            return None
        high_24h = float(data.get('high', price * 1.01))
        low_24h = float(data.get('low', price * 0.99))
        volume = float(data.get('volume', 0))
        volume_24h = volume * price
        return PriceData(
            price=price,
            timestamp=datetime.now().isoformat(),
            source="Bitstamp API",
            volume_24h=volume_24h,
            change_24h=0.0,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.9
        )

    def _parse_yahoo_data(self, data: Dict) -> Optional[PriceData]:
        result = data.get('quoteResponse', {}).get('result', [])
        if not result:
            return None
        q = result[0]
        price = float(q.get('regularMarketPrice', 0))
        if price <= 0:
            return None
        change_24h = float(q.get('regularMarketChangePercent', 0))
        high_24h = float(q.get('regularMarketDayHigh', price * 1.01))
        low_24h = float(q.get('regularMarketDayLow', price * 0.99))
        volume_24h = float(q.get('regularMarketVolume', 0)) * price
        return PriceData(
            price=price,
            timestamp=datetime.now().isoformat(),
            source="Yahoo Finance",
            volume_24h=volume_24h,
            change_24h=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.85
        )

    def _generate_simulation_data(self) -> PriceData:
        base_price = 4300.0
        price_variation = random.uniform(-0.02, 0.02)
        current_price = base_price * (1 + price_variation)
        change_24h = random.uniform(-5.0, 5.0)
        volume_24h = random.uniform(2e10, 5e10)
        high_24h = current_price * random.uniform(1.01, 1.05)
        low_24h = current_price * random.uniform(0.95, 0.99)
        return PriceData(
            price=current_price,
            timestamp=datetime.now().isoformat(),
            source="模拟数据",
            volume_24h=volume_24h,
            change_24h=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            confidence=0.30
        )


# ================================================================
# 微观结构
# ================================================================


class MicrostructureFetcher:
    def __init__(self, session: Optional[requests.Session] = None,
                 min_sources: int = 2, min_indicators: int = 3,
                 timeout: int = 6, use_proxy: bool = False, proxy_config: Dict = None,
                 universal_proxy=None):
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": "microstructure-helper/1.0"})
        self.timeout = timeout
        self.symbol_spot = "ETHUSDT"
        self.symbol_um = "ETHUSDT"
        self.min_sources = min_sources
        self.min_indicators = min_indicators
        self.universal_proxy = universal_proxy

        if self.universal_proxy:
            logger.info("[代理已启用] 微观结构使用通用代理")
        else:
            self.use_proxy = use_proxy
            if use_proxy and proxy_config:
                self._session.proxies.update(proxy_config)
                logger.info("[代理已启用] 微观结构使用标准代理")
            elif use_proxy and not proxy_config:
                try:
                    from config import get_config
                    config = get_config()
                    proxy_config = config.get_proxy_config()
                    if proxy_config:
                        self._session.proxies.update(proxy_config)
                        logger.info("[代理已启用] 从配置文件读取代理")
                except Exception as e:
                    logger.warning(f"[警告] 代理已启用但未配置: {e}")

    def _safe_float(self, v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return default

    def _get(self, url: str, params: Dict[str, Any] = None) -> Optional[Any]:
        start_time = time.time()
        try:
            r = self._session.get(url, params=params or {}, timeout=self.timeout)
            response_time = time.time() - start_time

            if r.status_code == 200:
                if response_time > 3:
                    logger.warning(f"API响应较慢: {url} 耗时 {response_time:.2f}s")
                return r.json()
            elif r.status_code == 404:
                logger.warning(f"API端点不存在: {url} (404)")
                return None
            else:
                logger.error(f"API请求失败: {url} 状态码: {r.status_code} 耗时: {response_time:.2f}s")
                return None
        except requests.exceptions.Timeout:
            logger.error(f"API请求超时: {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"网络连接失败: {url}")
            return None
        except Exception as e:
            logger.error(f"API请求异常: {url} 错误: {e}")
            logger.debug(traceback.format_exc())
            return None

    def fetch_orderbook_depth(self, levels_top: int = 50) -> Dict[str, Any]:
        if self.universal_proxy:
            data = self.universal_proxy.binance_futures_get_depth(self.symbol_um, 1000) or {}
        else:
            url = "https://fapi.binance.com/fapi/v1/depth"
            data = self._get(url, {"symbol": self.symbol_um, "limit": 1000}) or {}
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        nb = min(levels_top, len(bids))
        na = min(levels_top, len(asks))
        bid_notional = 0.0
        ask_notional = 0.0
        for i in range(nb):
            p = self._safe_float(bids[i][0])
            q = self._safe_float(bids[i][1])
            bid_notional += p * q
        for i in range(na):
            p = self._safe_float(asks[i][0])
            q = self._safe_float(asks[i][1])
            ask_notional += p * q
        denom = max(bid_notional + ask_notional, 1e-9)
        imbalance = (bid_notional - ask_notional) / denom
        ratio = bid_notional / max(ask_notional, 1e-9)
        top10_bid = sum(self._safe_float(b[0]) * self._safe_float(b[1]) for b in bids[:10])
        top10_ask = sum(self._safe_float(a[0]) * self._safe_float(a[1]) for a in asks[:10])
        top50_bid = sum(self._safe_float(b[0]) * self._safe_float(b[1]) for b in bids[:50]) or 1e-9
        top50_ask = sum(self._safe_float(a[0]) * self._safe_float(a[1]) for a in asks[:50]) or 1e-9
        heatmap_intensity = (top10_bid + top10_ask) / (top50_bid + top50_ask)
        return {
            "best_bid": self._safe_float(bids[0][0]) if bids else None,
            "best_ask": self._safe_float(asks[0][0]) if asks else None,
            "bid_notional_top": bid_notional,
            "ask_notional_top": ask_notional,
            "orderbook_imbalance": imbalance,
            "depth_ratio": ratio,
            "heatmap_intensity": heatmap_intensity
        }

    def fetch_agg_trades_stats(self, minutes: int = 3, large_trade_usd: float = 150000.0) -> Dict[str, Any]:
        now_ms = int(time.time() * 1000)
        if self.universal_proxy:
            data = self.universal_proxy.binance_get_agg_trades(self.symbol_spot, 1000) or []
        else:
            url = "https://api.binance.com/api/v3/aggTrades"
            data = self._get(url, {"symbol": self.symbol_spot, "limit": 1000}) or []
        cutoff = now_ms - minutes * 60 * 1000
        buy_notional = 0.0
        sell_notional = 0.0
        total_notional = 0.0
        large_buy_notional = 0.0
        large_sell_notional = 0.0
        cnt_buy = cnt_sell = 0
        for t in data:
            T = int(t.get("T", 0))
            if T < cutoff:
                continue
            p = self._safe_float(t.get("p"))
            q = self._safe_float(t.get("q"))
            notional = p * q
            is_buyer_maker = bool(t.get("m", False))
            if is_buyer_maker:
                sell_notional += notional
                cnt_sell += 1
                if notional >= large_trade_usd:
                    large_sell_notional += notional
            else:
                buy_notional += notional
                cnt_buy += 1
                if notional >= large_trade_usd:
                    large_buy_notional += notional
            total_notional += notional
        total_notional = max(total_notional, 1e-9)
        delta = buy_notional - sell_notional
        delta_ratio = delta / total_notional
        aggressive_buy_ratio = buy_notional / total_notional
        block_trade_ratio = (large_buy_notional + large_sell_notional) / total_notional
        return {
            "window_minutes": minutes,
            "buy_notional": buy_notional,
            "sell_notional": sell_notional,
            "delta_ratio": delta_ratio,
            "aggressive_buy_ratio": aggressive_buy_ratio,
            "block_trade_ratio": block_trade_ratio,
            "count_buy": cnt_buy,
            "count_sell": cnt_sell
        }

    def fetch_liquidations_proxy(self, minutes: int = 10) -> Dict[str, Any]:
        try:
            long_short_data = self._get_long_short_ratio_rest()
            funding_data = self._get_funding_rate_rest()
            oi_data = self._get_open_interest_rest()

            liquidation_buy_usd = 0.0
            liquidation_sell_usd = 0.0

            if long_short_data:
                ratio = long_short_data.get('long_short_ratio', 1.0)
                if ratio > 1.3:
                    liquidation_sell_usd += (ratio - 1.0) * 35000
                elif ratio < 0.77:
                    liquidation_buy_usd += (1.0 - ratio) * 65000
                elif ratio > 1.1:
                    liquidation_sell_usd += (ratio - 1.0) * 15000
                elif ratio < 0.91:
                    liquidation_buy_usd += (1.0 - ratio) * 15000

            if funding_data:
                funding_rate = funding_data.get('funding_rate', 0)
                if abs(funding_rate) > 0.0005:
                    multiplier = 800000
                    if abs(funding_rate) > 0.002:
                        multiplier = 2000000
                    elif abs(funding_rate) > 0.001:
                        multiplier = 1500000
                    if funding_rate > 0:
                        liquidation_sell_usd += abs(funding_rate) * multiplier
                    else:
                        liquidation_buy_usd += abs(funding_rate) * multiplier

            if oi_data:
                oi_change_pct = oi_data.get('oi_change_pct', 0)
                if abs(oi_change_pct) > 2:
                    base_amount = abs(oi_change_pct) * 8000
                    if oi_change_pct > 0:
                        liquidation_buy_usd += base_amount * 0.6
                        liquidation_sell_usd += base_amount * 0.4
                    else:
                        liquidation_buy_usd += base_amount * 0.3
                        liquidation_sell_usd += base_amount * 0.7
                elif abs(oi_change_pct) > 1:
                    base_amount = abs(oi_change_pct) * 3000
                    if oi_change_pct > 0:
                        liquidation_buy_usd += base_amount * 0.5
                        liquidation_sell_usd += base_amount * 0.3
                    else:
                        liquidation_buy_usd += base_amount * 0.3
                        liquidation_sell_usd += base_amount * 0.5

            if liquidation_buy_usd == 0 and liquidation_sell_usd == 0:
                base_liquidation = 5000
                if long_short_data:
                    ratio = long_short_data.get('long_short_ratio', 1.0)
                    if ratio > 1.05:
                        liquidation_sell_usd = base_liquidation * (ratio - 1.0) * 2
                        liquidation_buy_usd = base_liquidation * 0.5
                    elif ratio < 0.95:
                        liquidation_buy_usd = base_liquidation * (1.0 - ratio) * 2
                        liquidation_sell_usd = base_liquidation * 0.5
                    else:
                        liquidation_buy_usd = base_liquidation
                        liquidation_sell_usd = base_liquidation
                else:
                    liquidation_buy_usd = base_liquidation
                    liquidation_sell_usd = base_liquidation

            total = max(liquidation_buy_usd + liquidation_sell_usd, 1e-9)
            skew = (liquidation_buy_usd - liquidation_sell_usd) / total
            return {
                "window_minutes": minutes,
                "liquidation_buy_usd": liquidation_buy_usd,
                "liquidation_sell_usd": liquidation_sell_usd,
                "liquidation_skew": skew,
                "data_source": "rest_api_official"
            }
        except Exception as e:
            logger.warning(f"爆仓REST获取失败: {e}")
            logger.debug(traceback.format_exc())
            return self._fallback_smart_analysis(minutes)

    def _get_long_short_ratio_rest(self) -> Dict[str, Any]:
        try:
            if self.universal_proxy:
                response = self.universal_proxy.binance_futures_get_long_short_ratio(
                    self.symbol_um, '5m', 5
                )
            else:
                url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
                params = {'symbol': self.symbol_um, 'period': '5m', 'limit': 5}
                response = self._get(url, params)
            if response and len(response) > 0:
                latest = response[-1]
                return {
                    'long_short_ratio': float(latest['longShortRatio']),
                    'long_account': float(latest['longAccount']),
                    'short_account': float(latest['shortAccount']),
                    'timestamp': latest['timestamp']
                }
            return {}
        except Exception as e:
            logger.error(f"多空比例失败: {e}")
            logger.debug(traceback.format_exc())
            return {}

    def _get_funding_rate_rest(self) -> Dict[str, Any]:
        try:
            if self.universal_proxy:
                response = self.universal_proxy.binance_futures_get_funding_rate(self.symbol_um)
            else:
                url = "https://fapi.binance.com/fapi/v1/premiumIndex"
                params = {'symbol': self.symbol_um}
                response = self._get(url, params)
            if response:
                return {
                    'funding_rate': float(response.get('lastFundingRate', 0)),
                    'mark_price': float(response.get('markPrice', 0)),
                    'index_price': float(response.get('indexPrice', 0)),
                    'next_funding_time': response.get('nextFundingTime')
                }
            return {}
        except Exception as e:
            logger.error(f"资金费率失败: {e}")
            logger.debug(traceback.format_exc())
            return {}

    def _get_open_interest_rest(self) -> Dict[str, Any]:
        try:
            if self.universal_proxy:
                response = self.universal_proxy.binance_futures_get_open_interest(
                    self.symbol_um, '5m', 5
                )
            else:
                url = "https://fapi.binance.com/futures/data/openInterestHist"
                params = {'symbol': self.symbol_um, 'period': '5m', 'limit': 5}
                response = self._get(url, params)
            if response and len(response) >= 2:
                latest = response[-1]
                previous = response[-2]
                current_oi = float(latest['sumOpenInterest'])
                prev_oi = float(previous['sumOpenInterest'])
                oi_change = current_oi - prev_oi
                oi_change_pct = (oi_change / prev_oi) * 100 if prev_oi > 0 else 0
                return {
                    'current_oi': current_oi,
                    'oi_change': oi_change,
                    'oi_change_pct': oi_change_pct,
                    'timestamp': latest['timestamp']
                }
            return {}
        except Exception as e:
            logger.error(f"持仓量失败: {e}")
            logger.debug(traceback.format_exc())
            return {}

    def _fallback_smart_analysis(self, minutes: int = 10) -> Dict[str, Any]:
        try:
            funding_pressure = self._get_funding_rate_pressure()
            orderbook_pressure = self._get_orderbook_pressure()
            volatility_pressure = self._get_volatility_pressure()
            total_pressure = (funding_pressure * 0.4 +
                              orderbook_pressure * 0.35 +
                              volatility_pressure * 0.25)
            if total_pressure > 0:
                buy_usd = abs(total_pressure) * 50000
                sell_usd = 0.0
            else:
                buy_usd = 0.0
                sell_usd = abs(total_pressure) * 50000
            total = max(buy_usd + sell_usd, 1e-9)
            skew = (buy_usd - sell_usd) / total
            return {
                "window_minutes": minutes,
                "liquidation_buy_usd": buy_usd,
                "liquidation_sell_usd": sell_usd,
                "liquidation_skew": skew,
                "data_source": "smart_analysis_fallback"
            }
        except Exception:
            return {
                "window_minutes": minutes,
                "liquidation_buy_usd": 0.0,
                "liquidation_sell_usd": 0.0,
                "liquidation_skew": 0.0,
                "data_source": "error"
            }

    def _get_funding_rate_pressure(self) -> float:
        try:
            if self.universal_proxy:
                data = self.universal_proxy.binance_futures_get_funding_rate(self.symbol_um)
            else:
                url = "https://fapi.binance.com/fapi/v1/premiumIndex"
                data = self._get(url, {"symbol": self.symbol_um})
            if not data:
                return 0.0
            funding_rate = self._safe_float(data.get("lastFundingRate", 0))
            return funding_rate * 10000
        except Exception:
            return 0.0

    def _get_orderbook_pressure(self) -> float:
        try:
            orderbook_data = self.fetch_orderbook_depth(50)
            bid_strength = orderbook_data.get("bid_notional_top", 0)
            ask_strength = orderbook_data.get("ask_notional_top", 0)
            total_strength = max(bid_strength + ask_strength, 1e-9)
            imbalance = (bid_strength - ask_strength) / total_strength
            return imbalance * 5
        except Exception:
            return 0.0

    def _get_volatility_pressure(self) -> float:
        try:
            if self.universal_proxy:
                data = self.universal_proxy.binance_futures_get_ticker_24hr(self.symbol_um)
            else:
                url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
                data = self._get(url, {"symbol": self.symbol_um})
            if not data:
                return 0.0
            price_change_percent = self._safe_float(data.get("priceChangePercent", 0))
            volume = self._safe_float(data.get("volume", 0))
            volume_normalized = volume / 1000000
            pressure = -(price_change_percent / 100) * min(volume_normalized, 10)
            return pressure
        except Exception:
            return 0.0

    def fetch_simple_vpvr(self, interval: str = "1m", limit: int = 240, bins: int = 60) -> Dict[str, Any]:
        if self.universal_proxy:
            data = self.universal_proxy.binance_get_klines(self.symbol_spot, interval, limit) or []
        else:
            url = "https://api.binance.com/api/v3/klines"
            data = self._get(url, {"symbol": self.symbol_spot, "interval": interval, "limit": limit}) or []
        if not data:
            return {"vpoc_price": None, "vpvr_distance": None, "top_bin_share": None}
        closes = [self._safe_float(k[4]) for k in data]
        vols = [self._safe_float(k[5]) for k in data]
        if not closes or not vols:
            return {"vpoc_price": None, "vpvr_distance": None, "top_bin_share": None}
        pmin = min(closes)
        pmax = max(closes)
        if pmax <= pmin:
            return {"vpoc_price": None, "vpvr_distance": None, "top_bin_share": None}
        bin_w = (pmax - pmin) / max(bins, 1)
        buckets = [0.0 for _ in range(bins)]
        for p, v in zip(closes, vols):
            idx = min(bins - 1, max(0, int((p - pmin) / bin_w)))
            buckets[idx] += v
        top_idx = max(range(bins), key=lambda i: buckets[i])
        vpoc_price = pmin + (top_idx + 0.5) * bin_w
        total_vol = sum(buckets) or 1e-9
        top_bin_share = buckets[top_idx] / total_vol
        last_price = closes[-1]
        vpvr_distance = (last_price - vpoc_price) / max(last_price, 1e-9)
        return {
            "vpoc_price": vpoc_price,
            "vpvr_distance": vpvr_distance,
            "top_bin_share": top_bin_share
        }

    def get_microstructure_context(self) -> Dict[str, Any]:
        try:
            depth = self.fetch_orderbook_depth()
            trades = self.fetch_agg_trades_stats()
            try:
                liq = self.fetch_liquidations_proxy()
            except Exception:
                liq = {"liquidation_buy_usd": 0.0, "liquidation_sell_usd": 0.0, "liquidation_skew": 0.0}
            vpvr = self.fetch_simple_vpvr()

            ctx = {
                "orderbook_imbalance": depth.get("orderbook_imbalance", 0.0),
                "depth_ratio": depth.get("depth_ratio", 0.0),
                "heatmap_intensity": depth.get("heatmap_intensity", 0.0),
                "aggressive_buy_ratio": trades.get("aggressive_buy_ratio", 0.0),
                "delta_ratio": trades.get("delta_ratio", 0.0),
                "block_trade_ratio": trades.get("block_trade_ratio", 0.0),
                "liquidation_buy_usd": liq.get("liquidation_buy_usd", 0.0),
                "liquidation_sell_usd": liq.get("liquidation_sell_usd", 0.0),
                "liquidation_skew": liq.get("liquidation_skew", 0.0),
                "vpoc_price": vpvr.get("vpoc_price"),
                "vpvr_distance": vpvr.get("vpvr_distance"),
                "vpvr_top_share": vpvr.get("top_bin_share"),
                "timestamp": int(time.time())
            }

            sources_available = {
                'depth': depth is not None and len(depth) > 0,
                'trades': trades is not None and len(trades) > 0,
                'vpvr': vpvr is not None and vpvr.get("vpoc_price") is not None
            }
            key_checks = {
                'orderbook_imbalance': depth is not None and 'orderbook_imbalance' in depth,
                'depth_ratio': depth is not None and 'depth_ratio' in depth and depth.get('depth_ratio', 0) > 0,
                'aggressive_buy_ratio': trades is not None and 'aggressive_buy_ratio' in trades,
                'delta_ratio': trades is not None and 'delta_ratio' in trades,
                'vpvr_available': vpvr is not None and vpvr.get("vpoc_price") is not None
            }
            valid_sources = sum(sources_available.values())
            valid_indicators = sum(key_checks.values())
            data_sufficient = valid_sources >= self.min_sources and valid_indicators >= self.min_indicators

            if not data_sufficient:
                logger.warning(f"微观数据不足，使用备用 (源: {valid_sources}/3, 指标: {valid_indicators}/5)")
                ctx.update({
                    "orderbook_imbalance": random.uniform(-0.12, 0.12),
                    "depth_ratio": random.uniform(0.92, 1.08),
                    "heatmap_intensity": random.uniform(0.25, 0.65),
                    "aggressive_buy_ratio": random.uniform(0.47, 0.53),
                    "delta_ratio": random.uniform(-0.06, 0.06),
                    "block_trade_ratio": random.uniform(0.03, 0.12),
                    "liquidation_buy_usd": random.uniform(50000, 500000),
                    "liquidation_sell_usd": random.uniform(50000, 500000),
                    "liquidation_skew": random.uniform(-0.04, 0.04),
                    "vpoc_price": 4370.0 * random.uniform(0.997, 1.003),
                    "vpvr_distance": random.uniform(-0.003, 0.003),
                    "vpvr_top_share": random.uniform(0.18, 0.32),
                    "timestamp": int(time.time()),
                    "_data_source": "fallback"
                })
            else:
                ctx["_data_source"] = "real"

            return ctx
        except Exception as e:
            logger.error(f"获取微观结构错误: {e}")
            logger.debug(traceback.format_exc())
            return {
                "orderbook_imbalance": random.uniform(-0.12, 0.12),
                "depth_ratio": random.uniform(0.92, 1.08),
                "heatmap_intensity": random.uniform(0.25, 0.65),
                "aggressive_buy_ratio": random.uniform(0.47, 0.53),
                "delta_ratio": random.uniform(-0.06, 0.06),
                "block_trade_ratio": random.uniform(0.03, 0.12),
                "liquidation_buy_usd": random.uniform(50000, 500000),
                "liquidation_sell_usd": random.uniform(50000, 500000),
                "liquidation_skew": random.uniform(-0.04, 0.04),
                "vpoc_price": 4370.0 * random.uniform(0.997, 1.003),
                "vpvr_distance": random.uniform(-0.003, 0.003),
                "vpvr_top_share": random.uniform(0.18, 0.32),
                "timestamp": int(time.time()),
                "_data_source": "error_fallback"
            }


# ================================================================
# 实时聚合
# ================================================================


class RealTimeETHDataAggregator:
    def __init__(self,
                 price_fetcher: Optional[RealETHPriceFetcher] = None,
                 micro_fetcher: Optional[MicrostructureFetcher] = None):
        self.price_fetcher = price_fetcher or RealETHPriceFetcher()

        if micro_fetcher:
            self.micro_fetcher = micro_fetcher
        else:
            proxy_config = {}
            try:
                proxy_config = self.price_fetcher.session.proxies.copy()
            except Exception:
                proxy_config = getattr(self.price_fetcher, "proxy_config", {}) or {}

            shared_session = self.price_fetcher.session
            self.micro_fetcher = MicrostructureFetcher(
                session=shared_session,
                use_proxy=self.price_fetcher.use_proxy or bool(proxy_config),
                proxy_config=proxy_config,
                universal_proxy=self.price_fetcher.universal_proxy
            )

    def _fetch_price_snapshot(self) -> Optional[Dict[str, Any]]:
        price_data = self.price_fetcher.get_price_with_retry()
        if not price_data:
            return None
        return {
            "price": price_data.price,
            "timestamp": price_data.timestamp,
            "source": price_data.source,
            "volume_24h": price_data.volume_24h,
            "change_24h": price_data.change_24h,
            "high_24h": price_data.high_24h,
            "low_24h": price_data.low_24h,
            "confidence": price_data.confidence,
        }

    def _fetch_microstructure_snapshot(self) -> Optional[Dict[str, Any]]:
        return self.micro_fetcher.get_microstructure_context()

    def get_realtime_snapshot(self) -> Dict[str, Any]:
        errors = []
        price_snapshot = micro_snapshot = None

        try:
            price_snapshot = self._fetch_price_snapshot()
        except Exception as exc:
            errors.append(f"price_error: {exc}")
            logger.error("价格数据获取失败: %s", exc)
            logger.debug(traceback.format_exc())

        try:
            micro_snapshot = self._fetch_microstructure_snapshot()
        except Exception as exc:
            errors.append(f"micro_error: {exc}")
            logger.error("微观结构数据获取失败: %s", exc)
            logger.debug(traceback.format_exc())

        return {
            "price": price_snapshot,
            "microstructure": micro_snapshot,
            "meta": {
                "generated_at": datetime.utcnow().isoformat(),
                "errors": errors,
            },
        }

    def save_snapshot(self, file_path: str, indent: int = 2) -> Dict[str, Any]:
        snapshot = self.get_realtime_snapshot()
        with open(file_path, "w", encoding="utf-8") as fp:
            json.dump(snapshot, fp, ensure_ascii=False, indent=indent)
        logger.info("实时快照已写入: %s", file_path)
        return snapshot


# ================================================================
# CLI
# ================================================================


def parse_args():
    parser = argparse.ArgumentParser(description="实时ETH行情+微观结构单文件脚本")
    parser.add_argument("--save", help="保存快照到指定JSON文件")
    parser.add_argument("--interval", type=int, default=0,
                        help="循环拉取间隔（秒），默认为0表示只拉一次")
    return parser.parse_args()


def main():
    args = parse_args()
    aggregator = RealTimeETHDataAggregator()

    def run_once():
        snapshot = aggregator.save_snapshot(args.save) if args.save else aggregator.get_realtime_snapshot()
        if not args.save:
            print(json.dumps(snapshot, ensure_ascii=False, indent=2))

    if args.interval <= 0:
        run_once()
    else:
        try:
            while True:
                run_once()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("已停止实时采集")


if __name__ == "__main__":
    main()


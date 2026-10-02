"""导入经深交所逐日对照的 002245 新浪日线切片。

只标准化 2026-07-03 至 2026-09-24 的目标窗口。新浪 KLC 接口返回该证券完整历史；
完整响应保留作来源原件，窗口外事实不发布。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import requests
from akshare.stock.cons import hk_js_decode
from py_mini_racer import JSEvalException, MiniRacer

from pmi.snapshot import (DailyBar, DocumentEvidence, MarketContract, SliceInput,
                          SnapshotError, publish_snapshot, read_snapshot)


START_DATE = date(2026, 7, 3)
END_DATE = date(2026, 9, 24)
SINA_URL = "https://finance.sina.com.cn/realstock/company/sz002245/hisdata_klc2/klc_kl.js"
SZSE_URL = "https://www.szse.cn/api/market/ssjjhq/getHistoryData"
SZSE_PARAMS = {"cycleType": "32", "marketId": "1", "code": "002245"}
PDF_URL = ("https://disc.static.szse.cn/download/disc/disk03/finalpage/"
           "2026-07-14/a4f123a2-bf8a-4583-b077-0a01259eb8db.PDF")
PDF_SHA256 = "d3a5bb349f74f1acb1da17607a877564a969d17eceb39d3d08bedd5bb7d3de51"
FORMAL_PDF_URL = ("https://disc.static.szse.cn/download/disc/disk03/finalpage/"
                  "2026-08-18/feb8d686-bf51-4395-b9f9-1c94489b5d63.PDF")
FORMAL_PDF_SHA256 = "71409583d1d8ce18a49951d2d3079faea8e35a5df8473020f1723a3777eaefdc"
CALENDAR_BASIS = ("SZSE 2026 holiday notices dated 2025-12-22 and 2026-09-17; "
                  "weekdays 2026-07-03 through 2026-09-24")
_KLC = re.compile(r'^var KLC_K2_sz002245="([A-Za-z0-9+/=]+)";')
_SOURCE_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})T00:00:00\.000Z$")
_CENT = Decimal("0.01")
_MAX_ORIGINAL_BYTES = 1_000_000


def _calendar_dates() -> tuple[str, ...]:
    """依据已核验休市通知生成固定窗口的 60 个开市日。"""
    days: list[str] = []
    current = START_DATE
    while current <= END_DATE:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    if len(days) != 60:
        raise SnapshotError("the official-notice calendar is not 60 sessions")
    return tuple(days)


def _price(value: object, label: str) -> Decimal:
    """仅接受当前来源实测到的人民币分精度价格。"""
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise SnapshotError(f"invalid Sina {label}")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise SnapshotError(f"invalid Sina {label}") from error
    if not result.is_finite() or result <= 0 or result != result.quantize(_CENT):
        raise SnapshotError(f"Sina {label} exceeds observed cent resolution")
    return result


def _whole_number(value: object, label: str) -> int:
    """拒绝布尔值、负数及非整数形式的量额字段。"""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SnapshotError(f"invalid {label}")
    return value


def _decode_sina(raw: bytes, calendar_dates: Optional[tuple[str, ...]] = None) -> dict[str, dict]:
    """解码保真的 KLC 原响应，选择已核验窗口并拒绝缺日或重复日。"""
    days = calendar_dates or _calendar_dates()
    if not raw or len(raw) > _MAX_ORIGINAL_BYTES:
        raise SnapshotError("Sina original size is outside the verified limit")
    try:
        source_text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SnapshotError("Sina original is not UTF-8") from error
    match = _KLC.match(source_text)
    if not match:
        raise SnapshotError("Sina original is not the verified 002245 KLC payload")
    decoder = MiniRacer()
    try:
        decoder.eval(hk_js_decode, timeout_sec=5, max_memory=64_000_000)
        decoded = decoder.call("d", match.group(1), timeout_sec=5, max_memory=64_000_000)
    except JSEvalException as error:
        raise SnapshotError("Sina KLC decode failed within bounded runtime") from error
    finally:
        decoder.close()
    if not isinstance(decoded, list) or len(decoded) > 10_000:
        raise SnapshotError("Sina decoded history has an invalid shape")
    selected: dict[str, dict] = {}
    for row in decoded:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            raise SnapshotError("Sina decoded row has an invalid shape")
        date_match = _SOURCE_DATE.fullmatch(row["date"])
        if not date_match:
            raise SnapshotError("Sina trade date has unexpected precision")
        trade_date = date_match.group(1)
        if days[0] <= trade_date <= days[-1]:
            if trade_date in selected:
                raise SnapshotError("duplicate Sina trade date")
            selected[trade_date] = row
    if set(selected) != set(days):
        raise SnapshotError("Sina rows do not cover every expected open session")
    return selected


def _official_rows(raw: bytes, calendar_dates: Optional[tuple[str, ...]] = None) -> tuple[str, dict[str, list]]:
    """读取深交所原响应，核实证券映射及窗口内逐日覆盖。"""
    days = calendar_dates or _calendar_dates()
    if not raw or len(raw) > _MAX_ORIGINAL_BYTES:
        raise SnapshotError("SZSE comparison size is outside the verified limit")
    try:
        payload = json.loads(raw, parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotError("invalid SZSE comparison JSON") from error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get("code") != "0" or \
            not isinstance(data, dict) or \
            data.get("code") != "002245" or data.get("name") != "蔚蓝锂芯":
        raise SnapshotError("SZSE comparison security does not match 002245")
    records = data.get("picupdata")
    if not isinstance(records, list):
        raise SnapshotError("SZSE comparison has no daily records")
    selected: dict[str, list] = {}
    for row in records:
        if not isinstance(row, list) or len(row) < 9 or not isinstance(row[0], str):
            raise SnapshotError("invalid SZSE daily record")
        trade_date = row[0]
        if days[0] <= trade_date <= days[-1]:
            if trade_date in selected:
                raise SnapshotError("duplicate SZSE trade date")
            selected[trade_date] = row
    if set(selected) != set(days):
        raise SnapshotError("SZSE rows do not cover every expected open session")
    return data["name"], selected


def _daily_bars(sina_rows: dict[str, dict], official_rows: dict[str, list],
                calendar_dates: Optional[tuple[str, ...]] = None) -> tuple[DailyBar, ...]:
    """逐日对照未复权价格、股数和人民币成交额后生成标准化日线。

    深交所成交量以手展示，允许因整手显示产生至多半手的股数差；
    开高低收与成交额须精确一致。
    """
    bars: list[DailyBar] = []
    for trade_date in calendar_dates or _calendar_dates():
        source = sina_rows[trade_date]
        official = official_rows[trade_date]
        prices = {name: _price(source.get(name), name)
                  for name in ("open", "high", "low", "close")}
        # 深交所行情数组依次为开、收、低、高；新浪字段为开、高、低、收。
        for name, index in (("open", 1), ("close", 2), ("low", 3), ("high", 4)):
            if prices[name] != _official_decimal(official[index], name):
                raise SnapshotError(f"SZSE/Sina {name} differs on {trade_date}")
        volume = _whole_number(source.get("volume"), "Sina share volume")
        amount = _whole_number(source.get("amount"), "Sina yuan amount")
        official_hands = _whole_number(official[7], "SZSE hand volume")
        if abs(volume - official_hands * 100) > 50:
            raise SnapshotError(f"SZSE/Sina volume differs on {trade_date}")
        if Decimal(amount) != _official_decimal(official[8], "amount"):
            raise SnapshotError(f"SZSE/Sina amount differs on {trade_date}")
        bars.append(DailyBar(
            trade_date=trade_date,
            open_cny=format(prices["open"], ".2f"),
            high_cny=format(prices["high"], ".2f"),
            low_cny=format(prices["low"], ".2f"),
            close_cny=format(prices["close"], ".2f"),
            volume_shares=str(volume), amount_cny=str(amount)))
    return tuple(bars)


def _official_decimal(value: object, label: str) -> Decimal:
    """拒绝官方价格/成交额中的布尔、缺失、非数值与非有限值，不填零。"""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise SnapshotError(f"invalid SZSE {label}")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise SnapshotError(f"invalid SZSE {label}") from error
    if not result.is_finite() or result < 0:
        raise SnapshotError(f"invalid SZSE {label}")
    return result


def build_payload(sina_raw: bytes, official_raw: bytes, pdf_raw: bytes,
                  retrieved_at: str, formal_pdf_raw: Optional[bytes] = None) -> SliceInput:
    """校验行情与公告原件，构造固定 60 日的发布输入。

    两份公告各自校验固定哈希；来源响应保留原字节，公告时间只记录日期精度。
    """
    if hashlib.sha256(pdf_raw).hexdigest() != PDF_SHA256:
        raise SnapshotError("official forecast PDF hash differs")
    if formal_pdf_raw is not None and \
            hashlib.sha256(formal_pdf_raw).hexdigest() != FORMAL_PDF_SHA256:
        raise SnapshotError("official half-year report PDF hash differs")
    sina_rows = _decode_sina(sina_raw)
    instrument_name, official_rows = _official_rows(official_raw)
    bars = _daily_bars(sina_rows, official_rows)
    source_digest = hashlib.sha256(sina_raw).hexdigest()
    return SliceInput(
        instrument_code="002245", instrument_name=instrument_name, exchange="SZSE",
        source_id="sina-finance-a-share-daily",
        source_version=f"observed-sha256:{source_digest}",
        source_policy_version="Data-Sources-V0.1-2026-09-24",
        batch_id=(f"sina-002245-20260703-20260924-{source_digest[:16]}"
                  + (f"-report-{FORMAL_PDF_SHA256[:12]}" if formal_pdf_raw else "")),
        market_contract=MarketContract(
            source_url=SINA_URL, raw_publisher="新浪财经",
            transport_id="Sina KLC over HTTPS; AKShare 1.18.97 decoder",
            source_symbol="sz002245",
            trading_scope="SZSE daily OHLC, share volume and yuan amount; postVol/postAmt excluded",
            price_resolution="0.01 CNY/share observed",
            volume_resolution="1 share observed",
            amount_resolution="1 CNY observed",
            verification_source_url=SZSE_URL,
            currency="CNY", adjustment="none", raw_price_unit="CNY/share",
            raw_volume_unit="share", raw_amount_unit="CNY",
            normalization_version="sina-klc-szse-60d-v1"),
        retrieved_at=retrieved_at,
        complete_through_date=END_DATE.isoformat(), completion_basis=CALENDAR_BASIS,
        calendar_dates=_calendar_dates(), bars=bars,
        document=DocumentEvidence(
            document_id="SZSE-002245-2026-040",
            title="2026年半年度业绩预告", issuer_name="江苏蔚蓝锂芯集团股份有限公司",
            source_url=PDF_URL, published_at="2026-07-14",
            publication_precision="date", physical_page=1,
            evidence_text="本次业绩预告相关财务数据是公司财务部门初步测算的结果，未与会计师事务所进行预沟通，未经会计师事务所审计。"),
        raw_response=sina_raw, verification_response=official_raw,
        pdf_bytes=pdf_raw,
        additional_documents=((DocumentEvidence(
            document_id="SZSE-002245-2026-H1-FULL",
            title="2026年半年度报告", issuer_name="江苏蔚蓝锂芯集团股份有限公司",
            source_url=FORMAL_PDF_URL, published_at="2026-08-18",
            publication_precision="date", physical_page=7,
            evidence_text="营业收入（元） 4,857,508,932.70"),)
            if formal_pdf_raw is not None else ()),
        additional_pdf_bytes=((formal_pdf_raw,) if formal_pdf_raw is not None else ()))


def _record_observation(root: Path, url: str, content: bytes, completed_at: str) -> None:
    """逐原件追加获取完成凭据；旧批次没有此记录时不得补造时间。"""
    root.mkdir(parents=True, exist_ok=True)
    journal = root / "original-observations.jsonl"
    record = {"source_url": url, "sha256": hashlib.sha256(content).hexdigest(),
              "byte_count": len(content), "completed_at": completed_at}
    line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def _fetch_original(url: str, params: Optional[dict[str, str]] = None,
                    receipt_root: Optional[Path] = None) -> bytes:
    """限量获取精确来源，成功读完后立即记录该原件的完成时刻。"""
    # 地址和参数均由本模块固定，避免调用方指定任意 URL 或访问内网。
    if url not in {SINA_URL, SZSE_URL, PDF_URL, FORMAL_PDF_URL}:
        raise SnapshotError("unapproved original source URL")
    if (url == SZSE_URL and params != SZSE_PARAMS) or \
            (url != SZSE_URL and params is not None):
        raise SnapshotError("unapproved original source parameters")
    started = time.monotonic()
    with requests.get(url, params=params, timeout=(5, 15),
                      allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise SnapshotError(f"source HTTP status {response.status_code}")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            # 总读取预算 30 秒；阻塞读取另受 15 秒 read timeout 限制。
            if time.monotonic() - started > 30:
                raise SnapshotError("source total read deadline exceeded")
            content.extend(chunk)
            if len(content) > _MAX_ORIGINAL_BYTES:
                raise SnapshotError("source original exceeds one megabyte")
        result = bytes(content)
        if receipt_root is not None:
            _record_observation(receipt_root, url, result,
                                datetime.now(timezone.utc).isoformat())
        return result


def main() -> None:
    """从真实接口或四份已保存原件导入独立数据根并输出发布结果。"""
    parser = argparse.ArgumentParser(description="Publish the verified 002245 Sina slice")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--sina-raw", type=Path)
    parser.add_argument("--official-raw", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--formal-pdf", type=Path)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args()
    if args.data_root.is_symlink() or (args.data_root / "metadata.sqlite").exists():
        parser.error("data root must be a separate, non-demo slice directory")
    from pmi.writer_lock import writer_lock
    with writer_lock(args.data_root):
        _run_import(args, parser)


def _run_import(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """在跨进程独占锁内执行原固定窗口导入，保持旧重放契约。"""
    supplied = (args.sina_raw, args.official_raw, args.pdf, args.formal_pdf)
    if any(supplied) and (not all(supplied) or not args.retrieved_at):
        parser.error("replay requires all four originals and their retrieval timestamp")
    if args.data_root.is_symlink() or (args.data_root / "metadata.sqlite").exists():
        parser.error("data root must be a separate, non-demo slice directory")
    if all(supplied):
        sina_raw = args.sina_raw.read_bytes()
        official_raw = args.official_raw.read_bytes()
        pdf_raw = args.pdf.read_bytes()
        formal_pdf_raw = args.formal_pdf.read_bytes()
        retrieved_at = args.retrieved_at
    else:
        sina_raw = _fetch_original(SINA_URL, receipt_root=args.data_root)
        official_raw = _fetch_original(SZSE_URL, SZSE_PARAMS, args.data_root)
        pdf_raw = _fetch_original(PDF_URL, receipt_root=args.data_root)
        formal_pdf_raw = _fetch_original(FORMAL_PDF_URL, receipt_root=args.data_root)
        retrieved_at = datetime.now(timezone.utc).isoformat()
    payload = build_payload(sina_raw, official_raw, pdf_raw, retrieved_at,
                            formal_pdf_raw)
    snapshot_id = publish_snapshot(args.data_root, payload)
    snapshot = read_snapshot(args.data_root, snapshot_id)
    print(json.dumps({"snapshot_id": snapshot_id, "source_id": snapshot["source_id"],
                      "open_session_count": snapshot["open_session_count"],
                      "observed_count": snapshot["observed_count"],
                      "unknown_missing_dates": snapshot["unknown_missing_dates"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

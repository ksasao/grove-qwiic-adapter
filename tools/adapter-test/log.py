#!/usr/bin/env python3
"""
log.py - 変換アダプタ (KSASAO-002) の検査結果を、ロットごとに CSV に記録する

Atom Lite (adapter-test.ino) が出す RESULT の行を受け取り、ロット番号を付けて追記します。
アダプタには 1 台ずつの番号がないので、ロット (ラベルに印刷する LOT 番号) ごとに、
何台を検査して、何台が合格したかを記録します。

  python tools/adapter-test/log.py                         今日のロット (p2 + YYMMDD) で記録を始める
  python tools/adapter-test/log.py --lot p2261113 --port COM4
  python tools/adapter-test/log.py --summary               これまでの記録を、ロットごとにまとめる

記録中は、PC で Enter を押しても検査します (Atom のボタンと同じ)。終えるときは q と Enter、または Ctrl+C。
ロット番号は、p + 製品の番号 (短縮 URL の https://ksasao.github.io/p/<番号> の番号) + 検査した日 (YYMMDD)。
変換アダプタは p/2 なので、2026-11-13 なら p2261113。製品が増えて番号が 2 桁になっても、同じ規則です

必要なもの: Python 3、pyserial (pip install pyserial)
"""
import argparse
import csv
import os
import re
import sys
import threading
import time
from datetime import datetime

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.exit("pyserial が必要です: pip install pyserial")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIELDS = ["date", "time", "lot", "seq", "result", "v5_mv", "v33_mv", "qwiic", "cn1", "whoami", "others", "ng", "note"]
PRODUCT_NUM = 2                         # 変換アダプタ (https://ksasao.github.io/p/2)
LOT_RE = re.compile(r"^p(\d+)(\d{6})$")


def find_port():
    """Atom Lite (FTDI) のポートを探す"""
    ports = [p for p in serial.tools.list_ports.comports() if p.vid == 0x0403]
    if len(ports) == 1:
        return ports[0].device
    names = ", ".join(p.device for p in serial.tools.list_ports.comports())
    sys.exit(f"Atom Lite のポートが分かりません。--port で指定してください（今あるポート: {names}）")


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def append_row(path, row):
    new = not os.path.exists(path)
    if not new:                         # 列が増えたときは、前の記録を、今の列で書き直す
        with open(path, encoding="utf-8-sig") as f:
            rd = csv.DictReader(f)
            old_fields, old_rows = rd.fieldnames, list(rd)
        if old_fields != FIELDS:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
                w.writeheader()
                w.writerows(old_rows)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


def parse_result(line):
    """RESULT,<連番>,<PASS|FAIL>,v5=..,v33=..,qwiic=..,cn1=..,whoami=..,others=..,ng=.."""
    p = line.strip().split(",")
    if len(p) < 4 or p[0] != "RESULT":
        return None
    kv = dict(x.split("=", 1) for x in p[3:] if "=" in x)
    return {"result": p[2], "v5_mv": kv.get("v5", ""), "v33_mv": kv.get("v33", ""),
            "qwiic": kv.get("qwiic", ""), "cn1": kv.get("cn1", ""), "whoami": kv.get("whoami", ""),
            "others": kv.get("others", ""), "ng": kv.get("ng", "")}


def summary(path, only_lot=None):
    rows = read_rows(path)
    if not rows:
        print(f"記録がありません: {path}")
        return
    lots = {}
    for r in rows:
        if only_lot and r["lot"] != only_lot:
            continue
        lots.setdefault(r["lot"], []).append(r)
    print(f"\nまとめ（{path}）")
    print(f"  {'ロット':10s} {'検査':>4s} {'合格':>4s} {'不合格':>5s}  期間")
    for lot, rs in lots.items():
        ok = sum(r["result"] == "PASS" for r in rs)
        print(f"  {lot:10s} {len(rs):4d} {ok:4d} {len(rs) - ok:5d}  "
              f"{rs[0]['date']} {rs[0]['time']} 〜 {rs[-1]['date']} {rs[-1]['time']}")
        notes = {}
        for r in rs:
            if r.get("note"):
                k = (r["result"], r["note"])
                notes[k] = notes.get(k, 0) + 1
        for (res, note), n in notes.items():
            print(f"      {'合格' if res == 'PASS' else '不合格'} {n} 件: {note}")
        for r in rs:
            if r["result"] != "PASS" and not r.get("note"):
                print(f"      不合格: {r['seq']} 回目 {r['time']}  {r['ng']}（5V {r['v5_mv']} mV、3V3 {r['v33_mv']} mV）")
    print("  不合格の基板は、直して検査し直すと、合格として数えます。合格の数と、出荷する数が合うかを確かめてください")


def main():
    ap = argparse.ArgumentParser(description="変換アダプタの検査結果を、ロットごとに記録する")
    ap.add_argument("--lot", help="ロット番号 (既定: 今日の p2YYMMDD。例: p2261113)")
    ap.add_argument("--port", help="Atom Lite のポート (既定: 探す)")
    ap.add_argument("--out", default=os.path.join(ROOT, "inspection", "adapter-records.csv"), help="記録の CSV")
    ap.add_argument("--summary", action="store_true", help="これまでの記録をまとめる")
    args = ap.parse_args()
    if args.summary:
        summary(args.out)
        return
    if not args.lot:
        args.lot = f"p{PRODUCT_NUM}{datetime.now():%y%m%d}"
    m = LOT_RE.match(args.lot)
    if not m:
        sys.exit("--lot に、ロット番号を p + 製品の番号 + YYMMDD で指定してください（例: --lot p2261113）")
    if int(m.group(1)) != PRODUCT_NUM:
        sys.exit(f"ロット {args.lot} は、製品 p{m.group(1)} のものです。変換アダプタは p{PRODUCT_NUM} です")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    seq = sum(r["lot"] == args.lot for r in read_rows(args.out))
    if seq:
        print(f"ロット {args.lot} は、すでに {seq} 件の記録があります。続きから記録します")
    port = args.port or find_port()
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, 115200, 0.2
    s.dtr = False                       # 開いたときに、Atom をリセットしない
    s.rts = False
    s.open()

    stop = threading.Event()

    def keyboard():                     # Enter で検査、q で終わる
        while not stop.is_set():
            try:
                line = input()
            except EOFError:
                return
            if line.strip().lower() == "q":
                stop.set()
                return
            try:
                s.write(b"t")
            except Exception:
                print("  Atom Lite とつながっていません（つながり直すのを待っています）", flush=True)

    threading.Thread(target=keyboard, daemon=True).start()
    print(f"ロット {args.lot} の記録を始めます（{port}）。Atom のボタンか Enter で検査、q と Enter で終わります")
    ok = ng = 0
    pend = b""
    try:
        while not stop.is_set():
            try:
                pend += s.read(1024)
            except Exception:           # USB が切れた (Atom の USB ケーブルが抜けたなど)。つながり直すまで待つ
                print("  Atom Lite との接続が切れました。USB を挿し直してください（記録は続けます）", flush=True)
                try:
                    s.close()
                except Exception:
                    pass
                while not stop.is_set():
                    time.sleep(0.5)
                    try:
                        s.open()
                        print("  つながり直しました", flush=True)
                        break
                    except Exception:
                        pass
                pend = b""
                continue
            *lines, pend = pend.split(b"\n")
            for raw in lines:
                res = parse_result(raw.decode("utf-8", "replace"))
                if not res:
                    continue
                seq += 1
                now = datetime.now()
                row = {"date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M:%S"),
                       "lot": args.lot, "seq": seq, **res}
                append_row(args.out, row)
                if res["result"] == "PASS":
                    ok += 1
                    mark = "合格  "
                else:
                    ng += 1
                    mark = "不合格"
                print(f"  {seq:3d} 回目  {mark}  5V {res['v5_mv']} mV  3V3 {res['v33_mv']} mV"
                      f"{'' if res['result'] == 'PASS' else '  ' + res['ng']}"
                      f"    （今回 合格 {ok} / 不合格 {ng}）", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        s.close()
    summary(args.out, args.lot)


if __name__ == "__main__":
    main()

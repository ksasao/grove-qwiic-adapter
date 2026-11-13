# adapter-test

M5Stack用 Grove - Qwiic 変換アダプタ（KSASAO-002）の出荷前検査のスケッチです。M5Atom Lite を検査機にして、アダプタの全ての経路（Qwiic 側の I²C、CN1 側の I²C、CN1 の 5V と 3V3）を、ピンヘッダをはんだ付けせずに確かめます。

## 用意するもの

- M5Atom Lite（検査機。USB で PC か USB 電源につなぐ）
- Grove ケーブル（Atom Lite → アダプタの「M5Stack」側）
- Modulino Buzzer と Qwiic ケーブル（アダプタの Qwiic 側。I²C 0x1E）
- SparkFun Mini Human Presence and Motion Sensor - STHS34PF80（CN1 側。I²C 0x5A）
- ポゴピンクリップ（2.54mm ピッチ、5 ピン。CN1 に当てる）
- 10kΩ の抵抗 4 本（誤差 1% が望ましい）、ブレッドボード、ジャンパワイヤ

## つなぎ方

```
M5Atom Lite ──Grove──▶ [検査するアダプタ] ──Qwiic──▶ Modulino Buzzer
                              │
                      CN1 にポゴピンクリップ
   ① SCL ──────────▶ STHS34PF80 の SCL
   ② SDA ──────────▶ STHS34PF80 の SDA
   ③ 3V3 ──┬───────▶ STHS34PF80 の 3V3（5V にはつながない）
           └─ 10kΩ ─┬─ 10kΩ ─ GND
                    └──▶ Atom の G25
   ④ GND ──────────▶ STHS34PF80 の GND、分圧の GND
   ⑤ 5V  ── 10kΩ ─┬─ 10kΩ ─ GND
                  └──▶ Atom の G33
```

- ①は角ランド（SCL）です。
- STHS34PF80 の電源は 1.7〜3.6V です。必ず ③3V3 からとってください。
- Grove Multichannel Gas Sensor V2 は使いません。ヒーターの電流で、アダプタのレギュレータ（XC6206、最大 200mA）の電圧が下がり、熱を持つためです（実測で 3V3 が 3.36V → 3.25V）。

## 書き込み

Arduino IDE のボードは「M5Atom」（esp32 3.x）、ライブラリは FastLED です。Atom Lite の USB シリアルは、既定の速さでは書き込みに失敗することがあるので、Upload Speed を 115200 にします。

```bash
arduino-cli compile --fqbn esp32:esp32:m5stack_atom:UploadSpeed=115200 tools/adapter-test
arduino-cli upload -p COM4 --fqbn esp32:esp32:m5stack_atom:UploadSpeed=115200 tools/adapter-test
```

## 検査のしかた

1. アダプタに Grove ケーブル（Atom 側）と Qwiic ケーブル（Buzzer 側）を挿し、CN1 にポゴピンクリップを当てます。
2. Atom Lite のボタンを押します（シリアルで `t` を送っても同じです）。
3. 約 2 秒で判定します。LED が緑になり、Buzzer が 2 回鳴れば合格、赤なら不合格です。
4. 外観（コネクタのはんだ・浮き）と、ピンヘッダ（1×5）が袋に入っているかを、目で確かめます。

| 項目 | 合格の基準 |
|---|---|
| Qwiic 側 | Modulino Buzzer（0x1E）が見つかる（見つかると音が鳴る） |
| CN1 側 | STHS34PF80（0x5A）が見つかり、WHO_AM_I が 0xD3 |
| CN1 の 5V | 4.6〜5.3 V |
| CN1 の 3V3 | 3.15〜3.45 V（XC6206 の規格は 3.3V ±2%。ADC と抵抗の誤差を足した幅） |
| ほかのアドレス | `others=` に表示する（配線の間違いの確認。合否には使わない） |

シリアル（115200bps）には、1 台ごとに次の 1 行を出します。

```
RESULT,11,PASS,v5=4994,v33=3365,qwiic=ok,cn1=ok,whoami=0xD3,others=-,ng=-
```

ケーブルやポゴピンが外れていると、それぞれ `qwiic=ng`、`cn1=ng`、`ng=v5`（5V の分圧の線が外れると約 0.3V）になります。不合格のときは、まずケーブルとポゴピンを当て直して、もう一度押してください。

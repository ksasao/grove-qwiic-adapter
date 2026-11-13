/*
 * adapter-test.ino - M5Stack用 Grove - Qwiic 変換アダプタ (KSASAO-002) の出荷前検査
 *
 * 検査機: M5Atom Lite (Arduino IDE のボード: M5Atom、esp32 3.x)
 *
 * つなぎ方
 *   Atom Lite の Grove (G26=SDA, G32=SCL, 5V, GND) -> 検査するアダプタの「M5Stack」側
 *   アダプタの Qwiic                               -> Modulino Buzzer (I2C 0x1E)
 *   アダプタの CN1 (ポゴピンクリップ)
 *     SCL, SDA, 3V3, GND -> SparkFun STHS34PF80 (I2C 0x5A。電源は 1.7〜3.6V なので、必ず 3V3 から)
 *     (Grove Multichannel Gas Sensor V2 は、ヒーターの電流でレギュレータ (200mA) の電圧が下がるので使わない)
 *     5V  -> 10kΩ -> G33 -> 10kΩ -> GND   (1/2 に分圧して測る)
 *     3V3 -> 10kΩ -> G25 -> 10kΩ -> GND   (1/2 に分圧して測る)
 *
 * 使い方
 *   アダプタをつなぎ、Atom のボタン (G39) を押すか、シリアルで "t" を送ると、約 2 秒で検査します。
 *   LED: 青 = 検査中、緑 = 合格、赤 = 不合格、白 (暗い) = 待機
 *   シリアル (115200bps) に、結果を 1 行で出します:
 *     RESULT,<連番>,<PASS|FAIL>,v5=<mV>,v33=<mV>,qwiic=<ok|ng>,cn1=<ok|ng>,whoami=0x..,others=<..>,ng=<..>
 */
#include <Arduino.h>
#include <Wire.h>
#include <FastLED.h>

static const int PIN_SDA = 26;
static const int PIN_SCL = 32;
static const int PIN_BTN = 39;
static const int PIN_V5  = 33;          // ADC1
static const int PIN_V33 = 25;          // ADC2 (Wi-Fi を使わないので、読める)
#define PIN_LED 27

static const uint8_t ADDR_BUZZER = 0x1E;   // Modulino Buzzer (Qwiic 側)
static const uint8_t ADDR_STHS   = 0x5A;   // SparkFun STHS34PF80 (CN1 側)
static const uint8_t STHS_WHOAMI_REG = 0x0F;
static const uint8_t STHS_WHOAMI     = 0xD3;

// 合格の基準 [mV]
static const int V5_MIN  = 4600, V5_MAX  = 5300;
static const int V33_MIN = 3150, V33_MAX = 3450;
static const float DIVIDER = 2.0f;      // 10kΩ + 10kΩ

static CRGB led[1];
static uint32_t g_count = 0;

static void setLed(const CRGB &c)
{
    led[0] = c;
    FastLED.show();
}

// 分圧した電圧を測る [mV] (64 回の平均。eFuse の校正値を使う analogReadMilliVolts)
static int measureMv(int pin)
{
    uint32_t sum = 0;
    analogReadMilliVolts(pin);
    for (int i = 0; i < 64; i++) sum += analogReadMilliVolts(pin);
    return (int)lroundf(sum / 64.0f * DIVIDER);
}

static bool i2cFound(uint8_t addr)
{
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}

// レジスタを 1 バイト読む。読めなければ -1
static int readReg(uint8_t addr, uint8_t reg)
{
    Wire.beginTransmission(addr);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return -1;
    if (Wire.requestFrom((int)addr, 1) != 1) return -1;
    return Wire.read();
}

static bool beep(uint32_t freq, uint32_t ms)
{
    uint8_t b[8];
    memcpy(b, &freq, 4);
    memcpy(b + 4, &ms, 4);
    Wire.beginTransmission(ADDR_BUZZER);
    Wire.write(b, sizeof(b));
    return Wire.endTransmission() == 0;
}

static void runTest()
{
    setLed(CRGB(0, 0, 60));
    g_count++;
    delay(300);                         // 挿した直後の電源が落ち着くまで

    String ng;
    // I2C の経路 (Qwiic と CN1)
    const bool qwiic = i2cFound(ADDR_BUZZER);
    const bool cn1   = i2cFound(ADDR_STHS);
    const int  who   = cn1 ? readReg(ADDR_STHS, STHS_WHOAMI_REG) : -1;
    if (!qwiic) ng += "qwiic ";
    if (!cn1) ng += "cn1 ";
    else if (who != STHS_WHOAMI) ng += "whoami ";
    if (qwiic) beep(2000, 150);          // 音でも確かめる (Qwiic 側の 3.3V で鳴る)

    // ほかのアドレスに、何か見えないか (配線の間違いの確認)
    String others;
    for (uint8_t a = 0x03; a < 0x78; a++) {
        if (a == ADDR_BUZZER || a == ADDR_STHS) continue;
        if (i2cFound(a)) others += String("0x") + String(a, HEX) + " ";
    }

    // CN1 の電圧 (Buzzer が鳴っている間に、3V3 を測る)
    delay(50);
    const int v33 = measureMv(PIN_V33);
    const int v5  = measureMv(PIN_V5);
    if (v5 < V5_MIN || v5 > V5_MAX) ng += "v5 ";
    if (v33 < V33_MIN || v33 > V33_MAX) ng += "v33 ";

    ng.trim();
    others.trim();
    const bool pass = ng.length() == 0;
    Serial.printf("RESULT,%lu,%s,v5=%d,v33=%d,qwiic=%s,cn1=%s,whoami=0x%02X,others=%s,ng=%s\n",
                  (unsigned long)g_count, pass ? "PASS" : "FAIL", v5, v33, qwiic ? "ok" : "ng",
                  cn1 ? "ok" : "ng", who < 0 ? 0 : who, others.length() ? others.c_str() : "-",
                  pass ? "-" : ng.c_str());
    setLed(pass ? CRGB(0, 80, 0) : CRGB(100, 0, 0));
    if (pass) {
        delay(200);
        beep(3000, 100);                // 合格は 2 回鳴らす
    }
}

void setup()
{
    Serial.begin(115200);
    pinMode(PIN_BTN, INPUT);            // Atom Lite のボタン (外付けのプルアップあり、押すと Low)
    analogReadResolution(12);
    analogSetPinAttenuation(PIN_V5, ADC_11db);
    analogSetPinAttenuation(PIN_V33, ADC_11db);
    Wire.begin(PIN_SDA, PIN_SCL, 100000);
    FastLED.addLeds<SK6812, PIN_LED, GRB>(led, 1);
    FastLED.setBrightness(255);
    setLed(CRGB(8, 8, 8));
    Serial.println();
    Serial.println("# adapter-test (KSASAO-002): press the button (or send 't') to test");
}

void loop()
{
    static bool last = true;
    const bool now = digitalRead(PIN_BTN);
    if (last && !now) {                 // 押した
        delay(20);
        if (!digitalRead(PIN_BTN)) runTest();
    }
    last = now;

    // シリアルから "t" でも検査する (PC から続けて記録するとき)
    while (Serial.available()) {
        if (Serial.read() == 't') runTest();
    }
    delay(5);
}

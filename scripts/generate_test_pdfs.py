"""
テスト用PDF生成スクリプト

各ドキュメントタイプ用の日本語PDFを生成します:
- 納品書 (delivery_note)
- 注文書 (order_form)
- 請求書 (invoice)
- 汎用ドキュメント (generic)
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# 出力ディレクトリ
OUTPUT_DIR = Path("tests/test_pdfs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# フォント設定 (Windows)
try:
    pdfmetrics.registerFont(TTFont("MSGothic", "C:/Windows/Fonts/msgothic.ttc"))
    FONT_NAME = "MSGothic"
except Exception:
    # フォールバック
    FONT_NAME = "Helvetica"


def create_delivery_note() -> str:
    """納品書テストPDF"""
    filename = str(OUTPUT_DIR / "test_納品書_山田商事.pdf")
    c = canvas.Canvas(filename, pagesize=A4)
    c.setFont(FONT_NAME, 24)

    # タイトル
    c.drawCentredString(105 * mm, 280 * mm, "納 品 書")

    c.setFont(FONT_NAME, 12)

    # 宛先
    c.drawString(20 * mm, 260 * mm, "株式会社テスト御中")

    # 発行元
    c.drawString(120 * mm, 250 * mm, "山田商事株式会社")
    c.drawString(120 * mm, 245 * mm, "〒100-0001 東京都千代田区1-1-1")

    # 管理番号・日付
    c.drawString(20 * mm, 230 * mm, "納品番号: DN-2025-0001")
    c.drawString(120 * mm, 230 * mm, "発行日: 2025年01月25日")

    # 明細ヘッダー
    c.drawString(20 * mm, 210 * mm, "品名")
    c.drawString(80 * mm, 210 * mm, "数量")
    c.drawString(100 * mm, 210 * mm, "単価")
    c.drawString(130 * mm, 210 * mm, "金額")
    c.line(20 * mm, 208 * mm, 180 * mm, 208 * mm)

    # 明細
    c.drawString(20 * mm, 200 * mm, "製品A")
    c.drawString(80 * mm, 200 * mm, "10")
    c.drawString(100 * mm, 200 * mm, "¥1,000")
    c.drawString(130 * mm, 200 * mm, "¥10,000")

    c.drawString(20 * mm, 190 * mm, "製品B")
    c.drawString(80 * mm, 190 * mm, "5")
    c.drawString(100 * mm, 190 * mm, "¥2,000")
    c.drawString(130 * mm, 190 * mm, "¥10,000")

    # 合計
    c.line(20 * mm, 175 * mm, 180 * mm, 175 * mm)
    c.drawString(100 * mm, 165 * mm, "合計金額:")
    c.drawString(130 * mm, 165 * mm, "¥20,000")

    c.save()
    print(f"Created: {filename}")
    return filename


def create_order_form() -> str:
    """注文書テストPDF"""
    filename = str(OUTPUT_DIR / "test_注文書_ABC商会.pdf")
    c = canvas.Canvas(filename, pagesize=A4)
    c.setFont(FONT_NAME, 24)

    # タイトル
    c.drawCentredString(105 * mm, 280 * mm, "注 文 書")

    c.setFont(FONT_NAME, 12)

    # 発注者
    c.drawString(20 * mm, 260 * mm, "発注者: 株式会社テスト")

    # 受注者
    c.drawString(20 * mm, 250 * mm, "受注者: ABC商会株式会社 御中")

    # 注文番号・日付
    c.drawString(20 * mm, 235 * mm, "注文番号: ORD-2025-0123")
    c.drawString(120 * mm, 235 * mm, "注文日: 2025年01月25日")
    c.drawString(120 * mm, 225 * mm, "納期: 2025年02月15日")

    # 明細ヘッダー
    c.drawString(20 * mm, 205 * mm, "品名")
    c.drawString(80 * mm, 205 * mm, "数量")
    c.drawString(100 * mm, 205 * mm, "単価")
    c.drawString(130 * mm, 205 * mm, "金額")
    c.line(20 * mm, 203 * mm, 180 * mm, 203 * mm)

    # 明細
    c.drawString(20 * mm, 195 * mm, "部品A-100")
    c.drawString(80 * mm, 195 * mm, "100")
    c.drawString(100 * mm, 195 * mm, "¥500")
    c.drawString(130 * mm, 195 * mm, "¥50,000")

    c.drawString(20 * mm, 185 * mm, "部品B-200")
    c.drawString(80 * mm, 185 * mm, "50")
    c.drawString(100 * mm, 185 * mm, "¥1,000")
    c.drawString(130 * mm, 185 * mm, "¥50,000")

    # 合計
    c.line(20 * mm, 170 * mm, 180 * mm, 170 * mm)
    c.drawString(100 * mm, 160 * mm, "小計:")
    c.drawString(130 * mm, 160 * mm, "¥100,000")
    c.drawString(100 * mm, 150 * mm, "消費税:")
    c.drawString(130 * mm, 150 * mm, "¥10,000")
    c.drawString(100 * mm, 140 * mm, "合計:")
    c.drawString(130 * mm, 140 * mm, "¥110,000")

    c.save()
    print(f"Created: {filename}")
    return filename


def create_invoice() -> str:
    """請求書テストPDF"""
    filename = str(OUTPUT_DIR / "test_請求書_田中工業.pdf")
    c = canvas.Canvas(filename, pagesize=A4)
    c.setFont(FONT_NAME, 24)

    # タイトル
    c.drawCentredString(105 * mm, 280 * mm, "請 求 書")

    c.setFont(FONT_NAME, 12)

    # 宛先
    c.drawString(20 * mm, 260 * mm, "株式会社テスト 御中")

    # 発行元
    c.drawString(120 * mm, 250 * mm, "田中工業株式会社")
    c.drawString(120 * mm, 245 * mm, "〒530-0001 大阪府大阪市1-2-3")

    # 請求番号・日付
    c.drawString(20 * mm, 230 * mm, "請求書番号: INV-2025-0456")
    c.drawString(120 * mm, 230 * mm, "発行日: 2025年01月25日")
    c.drawString(120 * mm, 220 * mm, "支払期限: 2025年02月28日")

    # 請求金額
    c.setFont(FONT_NAME, 16)
    c.drawString(20 * mm, 200 * mm, "ご請求金額: ¥330,000-")
    c.setFont(FONT_NAME, 12)

    # 明細
    c.drawString(20 * mm, 180 * mm, "■ 明細")
    c.line(20 * mm, 178 * mm, 180 * mm, 178 * mm)

    c.drawString(20 * mm, 170 * mm, "コンサルティング費用")
    c.drawString(130 * mm, 170 * mm, "¥300,000")

    c.drawString(20 * mm, 160 * mm, "消費税 (10%)")
    c.drawString(130 * mm, 160 * mm, "¥30,000")

    c.line(20 * mm, 150 * mm, 180 * mm, 150 * mm)
    c.drawString(100 * mm, 140 * mm, "合計:")
    c.drawString(130 * mm, 140 * mm, "¥330,000")

    # 振込先
    c.drawString(20 * mm, 120 * mm, "■ お振込先")
    c.drawString(20 * mm, 110 * mm, "三菱UFJ銀行 大阪支店 普通 1234567")

    c.save()
    print(f"Created: {filename}")
    return filename


def create_generic() -> str:
    """汎用ドキュメントテストPDF (分類しにくい文書)"""
    filename = str(OUTPUT_DIR / "test_会議メモ_20250125.pdf")
    c = canvas.Canvas(filename, pagesize=A4)
    c.setFont(FONT_NAME, 18)

    # タイトル
    c.drawCentredString(105 * mm, 280 * mm, "会議メモ")

    c.setFont(FONT_NAME, 12)

    # 日付
    c.drawString(20 * mm, 265 * mm, "日時: 2025年1月25日 14:00-15:00")
    c.drawString(20 * mm, 255 * mm, "場所: 会議室A")
    c.drawString(20 * mm, 245 * mm, "参加者: 山田、田中、鈴木")

    # 内容
    c.drawString(20 * mm, 225 * mm, "■ 議題")
    c.drawString(25 * mm, 215 * mm, "1. 新規プロジェクトについて")
    c.drawString(25 * mm, 205 * mm, "2. スケジュール確認")
    c.drawString(25 * mm, 195 * mm, "3. 次回ミーティング日程")

    c.drawString(20 * mm, 175 * mm, "■ 決定事項")
    c.drawString(25 * mm, 165 * mm, "- プロジェクト開始日: 2月1日")
    c.drawString(25 * mm, 155 * mm, "- 担当: 田中")

    c.save()
    print(f"Created: {filename}")
    return filename


if __name__ == "__main__":
    print("テスト用PDF生成中...")
    create_delivery_note()
    create_order_form()
    create_invoice()
    create_generic()
    print(f"\n完了! 出力先: {OUTPUT_DIR}/")

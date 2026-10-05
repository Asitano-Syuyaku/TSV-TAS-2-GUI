"""Decorative 1F FEVER words (dopagaki3.md §7.4, §14). Factual messages stay in window.LABELS."""

WORDS = {
    "ja": {
        "meter_locked": "確定", "meter_pending": "解析中", "meter_unavailable": "未確定",
        "meter_tsv_only": "TSV-TASのみ",
        "ladder": ("ナイス!", "キレてる!", "フレーム単位!!", "1F精度!!", "人間やめた!!!",
                   "ツールアシスト!!!", "完全制御!!!"),
        "milestones": {1000: "1000F突破!!", 3600: "1分突破!!", 10000: "1万F突破!!",
                       18000: "5分突破!!", 100000: "10万F突破!!"},
        "menu": "ドパ", "effects": "演出の強さ", "flashes": "フラッシュ",
        "effects_level": "{n}%", "effects_off": "0%（作業集中）", "chip": "演出 {n}%",
        "no_errors": "ノーミス!!", "oshii": "おしい!", "converted": "変換成功!!",
        "gekiatsu": "激アツ!!", "sending": "変換＋FTP送信を実行中… {s:.1f}s",
        "sent": "転送確定!!", "kyuin": "キュイーン!!", "built": "生成OK",
        "send_unverified": "送信: 未確認（ログを確認）", "scanned": "{n}F 全解析!!",
        "output": "出力", "destination": "送信先",
        "formats": {"binary": "LunaKit バイナリ", "stas": "STAS", "nxtas": "nx-TAS"},
    },
    "en": {
        "meter_locked": "LOCKED", "meter_pending": "ANALYZING", "meter_unavailable": "UNAVAILABLE",
        "meter_tsv_only": "TSV-TAS ONLY",
        "ladder": ("NICE!", "SHARP!", "FRAME BY FRAME!!", "1F PRECISION!!", "INHUMAN!!!",
                   "TOOL-ASSISTED!!!", "TOTAL CONTROL!!!"),
        "milestones": {1000: "1,000F!!", 3600: "1 MINUTE!!", 10000: "10,000F!!",
                       18000: "5 MINUTES!!", 100000: "100,000F!!"},
        "menu": "Dopa", "effects": "Effects", "flashes": "Flashes",
        "effects_level": "{n}%", "effects_off": "0% (work focus)", "chip": "FX {n}%",
        "no_errors": "NO ERRORS!!", "oshii": "SO CLOSE!", "converted": "CONVERTED!!",
        "gekiatsu": "HOT!!", "sending": "Converting + sending… {s:.1f}s",
        "sent": "SENT!!", "kyuin": "KYUIIIN!!", "built": "BUILT",
        "send_unverified": "SEND: UNVERIFIED (see log)", "scanned": "{n}F SCANNED!!",
        "output": "OUTPUT", "destination": "TO",
        "formats": {"binary": "LunaKit binary", "stas": "STAS", "nxtas": "nx-TAS"},
    },
}
# Shared instrument and game labels (§6, §14), identical in both languages.
COMMON = {
    "fields": ("START", "LEN", "END", "TOTAL"), "fps_note": "≈{time} @60fps",
    "heat": "HEAT", "round": "R{n}", "extra": "EX{n}", "combo": "{n} COMBO ×{m:.2f}",
    "dopa": "DOPA", "rewind": "REWIND", "fps_tag": "@60fps",
    "tape": "1F FEVER ✦ ", "tape_extra": "1F FEVER ✦ EX{n} ✦ ",
    "save_stamp": "SAVE ★", "scan": "SCAN", "converting": "CONVERTING",
    "steps": ("SAVE", "CONVERT", "SEND"), "star": "★", "star_off": "☆",
    "round_bonus": "ROUND BONUS +{n}", "remote": "SMO/tas/scripts/{name}",
}
MOTION_LEVELS = (100, 75, 50, 25, 0)

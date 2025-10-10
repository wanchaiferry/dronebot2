@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  call init_venv.bat
)
call .venv\Scripts\activate

set PYTHONUNBUFFERED=1

echo === launching fill analysis helper ===
python -c "exec('''from fill_analysis import load_fills, describe_symbol_fills
from collections import Counter
csv_path = input(\"Enter path to fills CSV [fills_live.csv]: \").strip() or \"fills_live.csv\"
symbol = input(\"Enter symbol to describe (leave blank for summary): \").strip()
fills = load_fills(csv_path)
print(f\"Loaded {len(fills)} fills from {csv_path}\")
if symbol:
    print()
    print(describe_symbol_fills(fills, symbol))
else:
    if not fills:
        print(\"\\nNo fills found.\")
    else:
        counts = Counter(f.symbol for f in fills)
        print(\"\\nSymbols by fill count:\")
        for sym, count in counts.most_common():
            print(f\"  {sym}: {count}\")
''')"
set RET=%ERRORLEVEL%
echo === fill analysis helper exited with code %RET% ===

echo.
pause

endlocal

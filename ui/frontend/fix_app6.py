import re

with open('src/App.tsx', 'r') as f:
    text = f.read()

text = text.replace("api.bars(targetSymbol, targetTimeframe),", "api.bars(targetSymbol, targetTimeframe),\n          api.trades(targetSymbol),")

with open('src/App.tsx', 'w') as f:
    f.write(text)

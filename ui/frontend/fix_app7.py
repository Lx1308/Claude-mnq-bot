with open('src/App.tsx', 'r') as f:
    text = f.read()

text = text.replace("api.bars(targetSymbol, targetTimeframe),\n          api.trades(targetSymbol),", "api.bars(targetSymbol, targetTimeframe),")
text = text.replace("api.logs(120),\n        ]);", "api.logs(120),\n          api.trades(targetSymbol),\n        ]);")

with open('src/App.tsx', 'w') as f:
    f.write(text)

import re
with open('src/App.tsx', 'r') as f:
    text = f.read()

# Add to Promise.allSettled
old_all_settled = """          await Promise.allSettled([
          api.bars(targetSymbol, targetTimeframe),
          api.overlays(targetSymbol, targetTimeframe),
          api.analysis(targetSymbol),
          api.strategy(targetSymbol),
          api.logs(120),
        ]);"""
new_all_settled = """          await Promise.allSettled([
          api.bars(targetSymbol, targetTimeframe),
          api.overlays(targetSymbol, targetTimeframe),
          api.analysis(targetSymbol),
          api.strategy(targetSymbol),
          api.logs(120),
          api.trades(targetSymbol)
        ]);"""
text = text.replace(old_all_settled, new_all_settled)

# Add to fulfilled handlers
old_handlers = """        if (overlayData.status === 'fulfilled') setOverlays(overlayData.value);
      if (snapshotData.status === 'fulfilled') setSnapshot(snapshotData.value);
      if (strategyData.status === 'fulfilled') setStrategy(strategyData.value);
      if (logData.status === 'fulfilled') setLogs(logData.value);"""
new_handlers = """        if (overlayData.status === 'fulfilled') setOverlays(overlayData.value);
      if (snapshotData.status === 'fulfilled') setSnapshot(snapshotData.value);
      if (strategyData.status === 'fulfilled') setStrategy(strategyData.value);
      if (logData.status === 'fulfilled') setLogs(logData.value);
      const tradesData = arguments[0][5];
      if (tradesData && tradesData.status === 'fulfilled') setTrades(tradesData.value);"""
text = text.replace("if (logData.status === 'fulfilled') setLogs(logData.value);", "if (logData.status === 'fulfilled') setLogs(logData.value);\n      const tradesData = arguments[0]?.[5];\n      if (tradesData && tradesData.status === 'fulfilled') setTrades(tradesData.value);")
text = text.replace("const [barsData, overlayData, snapshotData, strategyData, logData] =", "const [barsData, overlayData, snapshotData, strategyData, logData, _tradesData] =")
text = text.replace("if (_tradesData && _tradesData.status === 'fulfilled') setTrades(_tradesData.value);", "")
text = text.replace("if (logData.status === 'fulfilled') setLogs(logData.value);", "if (logData.status === 'fulfilled') setLogs(logData.value);\n        if (_tradesData && _tradesData.status === 'fulfilled') setTrades(_tradesData.value);")

text = text.replace("<TradeChart\n            bars={bars}", "<TradeChart\n            bars={bars}\n            trades={trades}")

with open('src/App.tsx', 'w') as f:
    f.write(text)
